# If-None-Match cho GET và phản hồi 304 Not Modified

## 1. Conditional GET là gì?

Khi client gọi GET để đọc một resource, server thường trả 200 OK cùng representation và các response header. Nếu client đã lưu bản representation đó, việc tải lại toàn bộ body trong mỗi lần refresh có thể lãng phí băng thông, thời gian và pin thiết bị.

HTTP hỗ trợ **conditional GET** để client hỏi server xem representation đã lưu có còn mới không. Với ETag, client gửi giá trị đã nhận trước đó trong request header **If-None-Match**.

- Nếu representation hiện tại vẫn khớp ETag đã gửi, server trả **304 Not Modified**, không gửi lại body.
- Nếu representation đã thay đổi, server trả **200 OK**, body mới và ETag mới.

Client dùng body đã lưu khi nhận 304. Đây là cơ chế revalidation của HTTP cache, không phải một kiểu response chứa dữ liệu rút gọn.

Spring Data REST hỗ trợ kiểm tra If-None-Match khi xử lý GET. Nếu giá trị header khớp ETag hiện tại của resource, Spring Data REST trả 304 Not Modified thay cho representation đầy đủ.

## 2. ETag là gì?

ETag (entity tag) là validator do server cung cấp để nhận diện một phiên bản representation của resource. Giá trị này là opaque đối với client: client lưu và gửi lại nguyên văn, không tự phân tích hoặc tự tạo giá trị.

Ví dụ response:

~~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "7"

{
  "id": 42,
  "name": "Alice"
}
~~~~

Trong ví dụ, "7" là ETag do server phát ra. Client không được tự bỏ dấu ngoặc kép hoặc thay đổi định dạng khi gửi lại.

ETag có thể được tạo từ version, hash hoặc một cơ chế nội bộ khác. Theo HTTP, client chỉ cần so sánh validator do server cung cấp; không nên giả định ETag luôn là hash của JSON hoặc luôn bằng một số version database.

ETag thường có một trong hai dạng:

- **Strong ETag:** ví dụ "abc123", biểu thị validator mạnh cho representation.
- **Weak ETag:** ví dụ W/"abc123", cho phép so sánh yếu khi mục tiêu là cache validation và không yêu cầu byte-for-byte identity.

If-None-Match sử dụng weak comparison theo HTTP Semantics. Vì vậy, client nên giữ nguyên giá trị header thay vì tự xử lý tiền tố W/.

## 3. Tạo ETag trong Spring Data REST bằng @Version

Spring Data REST có thể tạo ETag từ version property của domain object. Tài liệu Spring Data REST hiện hành mô tả:

- Với Spring Data JPA, dùng annotation @Version của JPA.
- Với các Spring Data module khác, dùng org.springframework.data.annotation.Version.

Ví dụ entity JPA:

~~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @jakarta.persistence.Version
    private Long version;

    private String name;

    // getters/setters
}
~~~~

Khi Person được phục vụ như REST resource, Spring Data REST có thể đưa version value vào response header ETag. Ví dụ resource có version 7 có thể trả:

~~~~http
ETag: "7"
~~~~

Khi entity được cập nhật thành công, persistence provider/store quản lý version theo cơ chế của nó. Lần GET tiếp theo sẽ nhận ETag mới nếu version đã thay đổi.

Với module không dùng JPA, ví dụ khai báo version theo Spring Data Commons:

~~~~java
public class Person {

    @Id
    private String id;

    @org.springframework.data.annotation.Version
    private Long version;

    private String name;
}
~~~~

Cách đánh dấu version và ý nghĩa version có thể khác nhau theo store. Spring Data REST dựa vào metadata của store để nhận biết thuộc tính version. Hãy dùng đúng annotation cho module đang triển khai và kiểm tra response thực tế để xác nhận ETag được phát ra.

@Version cũng có thể hỗ trợ optimistic locking. Tuy nhiên, mục đích của bài này là dùng version làm validator cho GET; thao tác ghi có điều kiện bằng If-Match là một cơ chế liên quan nhưng khác mục đích.

## 4. Gửi GET lần đầu để lấy ETag

Client bắt đầu bằng request GET bình thường:

~~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/people/42
~~~~

Response minh họa:

~~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "7"
Cache-Control: no-cache

{
  "id": 42,
  "name": "Alice"
}
~~~~

Client cần lưu:

- URI chính xác đã gọi.
- Query parameter, nếu có.
- Representation hoặc body đã nhận.
- ETag nguyên văn.
- Các metadata cache cần thiết như Cache-Control, Date, Expires và Vary.

Không lưu riêng ETag mà bỏ body. Nếu lần tiếp theo server trả 304, client cần representation đã cache để tiếp tục hiển thị dữ liệu.

## 5. Gửi If-None-Match trong lần GET tiếp theo

Khi cần kiểm tra resource có thay đổi hay không, client gửi lại ETag trong header:

~~~~bash
curl -i -H "Accept: application/hal+json" -H 'If-None-Match: "7"' http://localhost:8080/people/42
~~~~

Nếu representation vẫn có ETag tương ứng, Spring Data REST trả response:

~~~~http
HTTP/1.1 304 Not Modified
ETag: "7"
Cache-Control: no-cache
~~~~

Response 304 không có body. Client dùng body đã lưu từ response 200 trước đó.

Nếu resource đã thay đổi và ETag hiện tại khác "7", server trả representation mới:

~~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "8"

{
  "id": 42,
  "name": "Alice Smith"
}
~~~~

Client thay thế body cache cũ và lưu ETag mới "8" cho lần revalidation sau.

## 6. Quy tắc đánh giá If-None-Match theo HTTP

RFC 9110 định nghĩa If-None-Match là request precondition. Header có thể chứa một ETag, danh sách ETag hoặc ký tự *.

### Một ETag

~~~~http
If-None-Match: "7"
~~~~

Với GET, nếu ETag của representation được chọn khớp giá trị đã gửi theo weak comparison, server trả 304. Nếu không khớp, server tiếp tục xử lý GET và trả representation, thường là 200.

### Danh sách ETag

~~~~http
If-None-Match: "5", "7", W/"9"
~~~~

Server kiểm tra xem ETag của representation hiện tại có khớp bất kỳ tag nào trong danh sách không. Nếu có match cho GET, trả 304.

### Wildcard

~~~~http
If-None-Match: *
~~~~

Với GET, wildcard khớp khi resource có một current representation. Nếu resource tồn tại, server trả 304; nếu không có representation hiện tại, request được xử lý theo luồng GET bình thường, thường trả 404 khi item không tồn tại.

### Phân biệt với If-Match

If-None-Match thường dùng để revalidate cache. If-Match thường dùng để bảo vệ thao tác ghi khỏi cập nhật trên phiên bản cũ.

- GET + If-None-Match trùng ETag: 304 Not Modified.
- PUT/PATCH/DELETE + If-Match không khớp: 412 Precondition Failed.
- Với method không an toàn, If-None-Match có semantics khác: nếu điều kiện không thỏa, server trả 412 thay vì 304.

Không dùng If-None-Match thay cho If-Match khi mục tiêu là ngăn lost update.

## 7. 304 Not Modified có ý nghĩa gì?

304 Not Modified là response cho conditional GET hoặc HEAD mà server xác định client đã có representation còn hợp lệ. Server không gửi lại body để giảm lượng dữ liệu truyền tải.

Các điểm quan trọng:

- 304 không phải redirect đến một URL khác.
- 304 không có response body.
- Client phải có representation cache trước đó để dùng lại.
- Server có thể gửi lại ETag và các cache metadata cần thiết để client cập nhật entry cache.
- Nếu client không có body cache, chỉ nhận 304 sẽ không đủ để dựng nội dung resource.

Theo RFC 9110, response 304 phải mang các header tương ứng mà response 200 cho cùng request sẽ gửi, trong phạm vi quy định như ETag, Date, Vary, Cache-Control, Expires và Content-Location khi các header đó áp dụng.

Ví dụ kiểm tra response:

~~~~bash
curl -i -H 'If-None-Match: "7"' http://localhost:8080/people/42
~~~~

Nếu kết quả là 304, không nên chờ JSON body trong response.

## 8. ETag và Cache-Control phối hợp với nhau

ETag là validator để kiểm tra representation có thay đổi hay không. Cache-Control quy định client và intermediary cache được lưu, dùng lại và revalidate response như thế nào.

Một số directive thường gặp:

| Directive | Ý nghĩa |
|---|---|
| max-age=60 | Cache có thể dùng response trong 60 giây mà chưa cần hỏi lại server |
| no-cache | Có thể lưu response nhưng phải revalidate trước khi dùng lại |
| no-store | Không lưu response trong cache |
| private | Chỉ private cache của client được lưu response; shared cache không được dùng response đó |
| public | Cho phép shared cache lưu response nếu các điều kiện cache khác cũng thỏa |

Ví dụ:

~~~~http
Cache-Control: private, no-cache
ETag: "7"
~~~~

Client có thể lưu response trong private cache, nhưng cần hỏi server trước khi dùng lại. Nếu ETag vẫn khớp, server trả 304 và client dùng body đã lưu.

Ví dụ khác:

~~~~http
Cache-Control: public, max-age=60
ETag: "7"
~~~~

Trong 60 giây, cache có thể dùng response còn fresh mà không cần gửi request. Sau khi response hết freshness, cache có thể gửi conditional GET với If-None-Match để revalidate.

no-cache không có nghĩa là “không được lưu”; directive cấm dùng lại mà chưa revalidate. no-store mới là directive yêu cầu không lưu response.

Với dữ liệu cá nhân hoặc representation phụ thuộc user hiện tại, hãy cấu hình cache policy phù hợp, thường là private hoặc no-store tùy yêu cầu bảo mật. Không để shared cache dùng lại representation của người dùng này cho người dùng khác.

Spring Data REST phát ETag không đồng nghĩa ứng dụng đã có chính sách Cache-Control đúng. Cần cấu hình header cache ở application, filter, gateway hoặc reverse proxy theo đặc tính dữ liệu.

## 9. Không dùng nhầm ETag giữa các request khác nhau

ETag xác định validator của selected representation. Representation có thể phụ thuộc vào URI, query parameter và content negotiation.

Ví dụ:

~~~~text
GET /people?active=true
GET /people?active=false
GET /people/42
~~~~

Không lấy ETag của request thứ nhất rồi gửi cho request thứ hai. Các request trên chọn resource/representation khác nhau.

Spring Data REST cũng lưu ý không trộn lẫn giá trị validator giữa các query. Hãy dùng ETag cho đúng URI và cùng query parameter đã tạo ra nó.

Nếu API hỗ trợ nhiều representation qua Accept, ví dụ HAL JSON và JSON, hãy lưu cache entry và validator theo representation tương ứng. Header Vary giúp cache biết request header nào ảnh hưởng đến representation được chọn. Không giả định một ETag có thể dùng chung cho mọi media type.

Đối với collection resource có paging hoặc filtering, mỗi URI với page, size, sort và filter khác nhau cần được xem là một cache key riêng.

## 10. If-Modified-Since là lựa chọn theo thời gian

Spring Data REST cũng hỗ trợ conditional GET theo thời gian thông qua Last-Modified và If-Modified-Since.

Một domain type có thể dùng Spring Data auditing:

~~~~java
@Document
public class Receipt {

    @Id
    private String id;

    @Version
    private Long version;

    @LastModifiedDate
    private Instant lastModifiedDate;

    private String saleItem;
}
~~~~

Khi auditing được cấu hình và trường last-modified được cập nhật, Spring Data REST có thể trả:

~~~~http
Last-Modified: Wed, 24 Jun 2026 20:28:15 GMT
~~~~

Client gửi lại ngày đã nhận:

~~~~bash
curl -i -H 'If-Modified-Since: Wed, 24 Jun 2026 20:28:15 GMT' http://localhost:8080/receipts/42
~~~~

Nếu resource không được sửa sau thời điểm đó, server có thể trả 304. Nếu đã thay đổi, server trả 200 cùng representation mới và Last-Modified mới.

ETag thường chính xác hơn date validator vì Last-Modified có độ phân giải theo giây và có thể không phân biệt được nhiều thay đổi xảy ra trong cùng một giây.

Nếu request có cả If-None-Match và If-Modified-Since, RFC 9110 yêu cầu server ưu tiên If-None-Match và bỏ qua If-Modified-Since. Nên ưu tiên ETag cho cache validation khi API cung cấp nó.

## 11. Quy trình cache revalidation phía client

Một client có thể triển khai quy trình sau:

1. Gửi GET với URI và Accept phù hợp.
2. Khi nhận 200, lưu body, ETag và cache metadata.
3. Khi response còn fresh theo Cache-Control, dùng lại body cache mà chưa cần request.
4. Khi cần revalidate, gửi GET cùng URI/query/representation và thêm If-None-Match với ETag đã lưu.
5. Nếu nhận 304, giữ nguyên body và cập nhật cache metadata theo response.
6. Nếu nhận 200, thay body và ETag bằng giá trị mới.
7. Nếu nhận 404, xử lý resource đã bị xóa hoặc không còn tồn tại theo contract API.
8. Nếu request lỗi mạng, quyết định dùng stale cache hay báo lỗi theo chính sách ứng dụng.

Pseudo-code:

~~~~java
CachedResponse cached = cache.get(cacheKey);

HttpRequest.Builder request = HttpRequest.newBuilder(uri)
        .header("Accept", "application/hal+json")
        .GET();

if (cached != null && cached.etag() != null) {
    request.header("If-None-Match", cached.etag());
}

HttpResponse<String> response = client.send(
        request.build(),
        HttpResponse.BodyHandlers.ofString()
);

if (response.statusCode() == 304 && cached != null) {
    return cached.body();
}

if (response.statusCode() == 200) {
    String etag = response.headers()
            .firstValue("ETag")
            .orElse(null);

    cache.put(cacheKey, new CachedResponse(
            response.body(),
            etag,
            response.headers()
    ));

    return response.body();
}

throw new IllegalStateException(
        "Unexpected HTTP status: " + response.statusCode()
);
~~~~

Đây là pseudo-code minh họa. Một HTTP client hoặc cache library thực tế có thể tự quản lý cache, freshness và revalidation. Nếu tự triển khai, cần xử lý thêm redirect, authorization, Vary, lỗi mạng, response body và các status khác.

## 12. Kiểm thử If-None-Match với Spring Data REST

Nên kiểm tra qua HTTP endpoint thực tế thay vì chỉ unit test một hàm so sánh version.

### Kiểm thử thủ công bằng curl

Lần đầu:

~~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/people/42
~~~~

Ghi lại ETag từ response 200. Sau đó gửi lại đúng URI:

~~~~bash
curl -i -H "Accept: application/hal+json" -H 'If-None-Match: "7"' http://localhost:8080/people/42
~~~~

Khi resource chưa đổi, xác nhận:

- Status là 304.
- Response không có body.
- ETag/cache metadata được trả phù hợp.
- Client có thể dùng body cache từ lần GET đầu.

Thay đổi entity qua một request cập nhật hợp lệ, rồi gửi lại ETag cũ. Server cần trả representation mới bằng 200 nếu version/ETag đã đổi.

### Kiểm thử tích hợp bằng MockMvc

Ví dụ:

~~~~java
MvcResult firstResponse = mockMvc.perform(
        get("/people/{id}", 42L)
            .accept(MediaType.parseMediaType("application/hal+json"))
    )
    .andExpect(status().isOk())
    .andReturn();

String etag = firstResponse.getResponse()
        .getHeader(HttpHeaders.ETAG);

assertThat(etag).isNotNull();

mockMvc.perform(
        get("/people/{id}", 42L)
            .accept(MediaType.parseMediaType("application/hal+json"))
            .header(HttpHeaders.IF_NONE_MATCH, etag)
    )
    .andExpect(status().isNotModified())
    .andExpect(content().string(""));
~~~~

Test này cần repository resource có version metadata phù hợp và ETag được Spring Data REST phát ra. Nếu không có ETag, kiểm tra annotation version, store module, persistence mapping và cấu hình endpoint trước khi kết luận conditional GET không hoạt động.

Nên bổ sung test cho các trường hợp:

- ETag trùng: trả 304.
- ETag cũ sau khi cập nhật: trả 200 và ETag mới.
- Danh sách ETag có một giá trị trùng: trả 304.
- Wildcard với resource đang tồn tại: kiểm tra semantics theo HTTP.
- URI hoặc query parameter khác: không dùng lại ETag của request trước.
- Representation khác do Accept: kiểm tra cache key và Vary.
- Resource không tồn tại: xử lý 404 theo contract.
- Response 304 không chứa body.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| GET luôn trả 200 dù ETag không đổi | Request không gửi If-None-Match, endpoint chưa hỗ trợ validator hoặc ETag không được tạo | Kiểm tra header request và version metadata |
| Response không có ETag | Domain type thiếu version field hoặc store không nhận diện version metadata | Dùng annotation @Version đúng module và kiểm tra response |
| Gửi ETag nhưng nhận 200 | ETag không khớp selected representation, resource đã đổi hoặc gửi sai URI/query | Lưu nguyên văn ETag và dùng đúng request key |
| Nhận 304 nhưng UI không có dữ liệu | Client không lưu body từ response 200 trước | Lưu body cùng ETag |
| Dùng ETag của collection cho item | Cache key/validator bị trộn giữa URI khác nhau | Lưu validator theo URI và query cụ thể |
| Response 304 vẫn có body | Proxy, custom handler hoặc test setup không tuân thủ response contract | Kiểm tra response ở origin và intermediary |
| Cache hiển thị dữ liệu user khác | Cache-Control/Vary không phù hợp với dữ liệu phụ thuộc user | Dùng private/no-store và cấu hình cache an toàn |
| Last-Modified không phát hiện một số thay đổi nhanh | Độ phân giải timestamp theo giây | Ưu tiên ETag |
| ETag không đổi sau khi cập nhật association | Version metadata không phản ánh mọi thay đổi của representation | Kiểm tra aggregate/version strategy hoặc dùng validator phù hợp representation |

## 14. Kết luận

If-None-Match cho phép client thực hiện conditional GET bằng cách gửi ETag đã nhận trước đó. Nếu ETag khớp representation hiện tại, Spring Data REST trả 304 Not Modified và không gửi lại body; nếu resource đã đổi, server trả 200 OK, representation mới và ETag mới.

Trong Spring Data REST, field @Version phù hợp với store có thể được dùng để tạo ETag. Client phải lưu ETag cùng body, tái sử dụng nó cho đúng URI và query, hiểu rằng 304 không có body và cập nhật cache metadata theo response. Cache-Control quyết định response được lưu và dùng lại ra sao; If-Modified-Since là lựa chọn dựa trên thời gian khi có Last-Modified. Hãy kiểm thử cả lần GET đầu, lần revalidation không đổi và lần resource đã thay đổi.

## Tài liệu tham khảo

- [Spring Data REST — Conditional Operations with Headers](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html)
- [RFC 9110 — HTTP Semantics, If-None-Match](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.2)
- [RFC 9110 — HTTP Semantics, 304 Not Modified](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.4.5)
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html)
- [MDN — If-None-Match](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/If-None-Match)
- [MDN — 304 Not Modified](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/304)
