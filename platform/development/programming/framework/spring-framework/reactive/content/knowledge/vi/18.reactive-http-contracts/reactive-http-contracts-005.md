# ETag, Last-Modified và yêu cầu có điều kiện

**Ngữ cảnh:** Spring Framework Reactive → **Hợp đồng HTTP**.

Một response HTTP có thể mang dữ liệu cùng các validator mô tả phiên bản của representation. Khi client lưu bản sao, nó gửi validator trở lại ở request sau để hỏi server xem bản sao còn dùng được hay không. Khi client cập nhật resource, nó có thể gửi validator như một điều kiện để tránh ghi đè thay đổi của người khác.

Ba khái niệm cần nắm:

- `ETag` là entity tag nhận diện một phiên bản representation. Server thường tạo nó từ hash nội dung hoặc version ổn định của resource.
- `Last-Modified` là thời điểm representation được sửa lần cuối, được gửi dưới dạng HTTP-date.
- **Conditional request** là request có điều kiện như `If-None-Match`, `If-Modified-Since` hoặc `If-Match`. Server đánh giá điều kiện trước khi gửi representation hoặc thực hiện thay đổi.

Với GET/HEAD, validator cho phép server trả `304 Not Modified` và bỏ qua body khi bản sao phía client vẫn hợp lệ. Với thao tác ghi, `If-Match` giúp phát hiện bản resource đã thay đổi và có thể ngăn cập nhật cũ bằng `412 Precondition Failed`.

## 1. Vì sao HTTP cần validator?

Giả sử một ứng dụng đọc hồ sơ sách qua `GET /books/42`. Lần đầu, server trả:

```http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "book-v17"
Last-Modified: Tue, 15 Apr 2025 10:15:30 GMT
Cache-Control: private, max-age=60

{"id":42,"title":"Reactive HTTP"}
```

Client có thể lưu representation này cùng các header. Nếu sau đó client cần kiểm tra xem dữ liệu đã đổi chưa, nó không cần tải lại toàn bộ JSON ngay. Nó gửi validator:

```http
GET /books/42 HTTP/1.1
If-None-Match: "book-v17"
```

Nếu representation hiện tại vẫn có ETag tương ứng, server trả:

```http
HTTP/1.1 304 Not Modified
ETag: "book-v17"
Last-Modified: Tue, 15 Apr 2025 10:15:30 GMT
Cache-Control: private, max-age=60
```

`304` không phải lỗi và không có response body. Client dùng representation đã lưu trước đó như thể vừa nhận response thành công. Nhờ vậy, request vẫn có thể tới server để kiểm tra tính hợp lệ, nhưng server không cần gửi lại toàn bộ payload.

Nếu resource đã thay đổi, server trả `200 OK` với representation mới và validator mới, ví dụ `ETag: "book-v18"`.

**Freshness và validation là hai cơ chế liên quan nhưng khác nhau:**

- Khi response còn fresh theo `Cache-Control: max-age`, cache có thể dùng lại response mà chưa cần hỏi origin.
- Khi response stale, cache có thể gửi conditional request với `ETag` hoặc `Last-Modified`.
- `no-cache` cho phép lưu nhưng yêu cầu revalidate trước khi dùng lại.
- `no-store` chỉ thị không lưu response trong cache.
- `private` giới hạn cache ở private cache như browser; `public` cho phép shared cache lưu nếu các điều kiện khác cho phép.

Validator không tự quyết định thời gian cache được dùng. `Cache-Control` quy định chính sách freshness; validator hỗ trợ kiểm tra khi cần revalidation.

## 2. ETag là gì?

`ETag` (entity tag) là một giá trị opaque do server tạo để nhận diện một phiên bản của representation. Client không cần hiểu nội dung tag; nó chỉ gửi lại giá trị đó cho server so sánh.

Ví dụ:

```http
ETag: "book-v17"
```

Một ETag có thể được tạo từ:

- **Version của database:** ví dụ cột optimistic-lock version tăng sau mỗi lần cập nhật.
- **Hash nội dung:** ví dụ SHA-256 của representation bytes được chọn.
- **Revision ID:** mã phiên bản do hệ thống lưu trữ hoặc content management system cấp.

### 2.1. Strong ETag và weak ETag

Strong ETag có dạng:

```http
ETag: "book-v17"
```

Weak ETag có tiền tố `W/`:

```http
ETag: W/"book-v17"
```

Hai loại có ngữ nghĩa khác nhau:

| Loại | Ý nghĩa | Dùng phù hợp |
|---|---|---|
| **Strong validator** | Đại diện cho representation data giống hệt theo yêu cầu strong comparison | Kiểm tra cache chính xác, range và tránh lost update bằng `If-Match` |
| **Weak validator** | Hai representation được xem là tương đương về mặt ngữ nghĩa dù bytes có thể khác | Cache validation khi khác biệt nhỏ không làm thay đổi ý nghĩa nội dung |

Strong ETag phù hợp khi server có thể bảo đảm mọi thay đổi representation bytes đều tạo tag khác. Hash trên chính bytes đã mã hóa là một cách làm phổ biến. Version database cũng có thể dùng làm strong validator nếu mọi thay đổi ảnh hưởng representation đều làm version tăng và cùng một version luôn tạo ra representation nhất quán.

Weak ETag hữu ích khi server chỉ muốn nói rằng hai representation tương đương về nội dung, chẳng hạn khác biệt định dạng hoặc một số chi tiết không quan trọng đối với client. Weak ETag không thể dùng cho strong comparison của `If-Match`.

### 2.2. ETag phải nhận diện representation được chọn

Một resource có thể có nhiều representation:

- JSON và XML.
- Ngôn ngữ tiếng Việt và tiếng Anh.
- Dữ liệu đã nén gzip và dữ liệu chưa nén.
- Response khác nhau theo quyền hoặc cấu hình người dùng.

Nếu các representation khác nhau về bytes nhưng cùng được gán một strong ETag, validator có thể khẳng định sai rằng chúng giống hệt nhau. Hãy tạo tag theo representation được chọn hoặc dùng weak validator nếu chỉ muốn xác nhận tương đương về ngữ nghĩa.

Khi response phụ thuộc header như `Accept` hoặc `Accept-Language`, dùng `Vary` thích hợp để cache biết các biến thể khác nhau. Với dữ liệu cá nhân, cần chính sách cache như `private` hoặc `no-store` phù hợp; ETag không thay thế authorization.

### 2.3. Không nhầm ETag với checksum bảo mật

ETag chủ yếu là validator của HTTP, không phải chữ ký số hay cơ chế xác thực dữ liệu. Client không được coi ETag là bằng chứng response đến từ server đáng tin cậy. Nếu cần integrity hoặc authenticity, dùng cơ chế mật mã phù hợp, chẳng hạn TLS và chữ ký theo hợp đồng riêng.

## 3. Last-Modified là gì?

`Last-Modified` cho biết thời điểm representation được sửa lần cuối:

```http
Last-Modified: Tue, 15 Apr 2025 10:15:30 GMT
```

Giá trị là HTTP-date theo UTC/GMT. Server thường lấy từ trường cập nhật của resource, rồi chuẩn hóa theo độ chính xác của HTTP-date.

Client gửi lại:

```http
If-Modified-Since: Tue, 15 Apr 2025 10:15:30 GMT
```

Nếu representation không mới hơn mốc thời gian này, server có thể trả `304 Not Modified`.

### 3.1. Hạn chế độ phân giải một giây

HTTP-date có độ phân giải theo giây. Nếu resource được sửa hai lần trong cùng một giây, hai phiên bản có thể có cùng `Last-Modified`. Vì vậy, Last-Modified có thể không đủ chính xác để phân biệt mọi phiên bản.

Ví dụ:

- Phiên bản A được sửa lúc 10:15:30.100.
- Phiên bản B được sửa lúc 10:15:30.800.
- Cả hai có thể được biểu diễn thành `10:15:30 GMT`.

Một client có thể giữ bản A nhưng gửi `If-Modified-Since: 10:15:30 GMT`; chỉ so sánh timestamp không đủ để nhận ra thay đổi B trong cùng giây.

Các vấn đề khác gồm clock skew giữa máy chủ, timestamp bị cập nhật sai, hệ thống lưu trữ có độ chính xác thấp và việc representation được tạo từ nhiều nguồn dữ liệu.

**Thực hành tốt:** gửi cả ETag và Last-Modified nếu có thể. ETag thường là validator chính xác hơn; Last-Modified hữu ích cho client hoặc cache không lưu ETag và dễ đọc khi chẩn đoán.

## 4. Các conditional request headers quan trọng

### 4.1. If-None-Match: kiểm tra representation chưa thay đổi

`If-None-Match` chứa một hoặc nhiều entity tag, hoặc ký tự `*`:

```http
If-None-Match: "book-v17"
If-None-Match: "book-v16", "book-v17"
If-None-Match: *
```

Với GET/HEAD:

- Nếu một tag khớp representation hiện tại, server trả `304 Not Modified`.
- Nếu không tag nào khớp, server xử lý request bình thường và có thể trả `200` cùng representation.

`If-None-Match` dùng **weak comparison**. Vì vậy `W/"book-v17"` có thể khớp `"book-v17"` trong ngữ cảnh cache validation.

Với method không an toàn như PUT, POST hoặc DELETE, nếu điều kiện `If-None-Match` thất bại, server trả `412 Precondition Failed` và không thực hiện thay đổi. Trường hợp `If-None-Match: *` thường được dùng để chỉ tạo resource nếu resource chưa tồn tại.

### 4.2. If-Modified-Since: kiểm tra theo thời gian

`If-Modified-Since` được dùng với GET/HEAD:

```http
If-Modified-Since: Tue, 15 Apr 2025 10:15:30 GMT
```

Nếu Last-Modified của representation hiện tại sớm hơn hoặc bằng ngày được gửi, server có thể trả `304`. Nếu resource mới hơn, server trả representation bình thường.

Nếu request có cả `If-None-Match` và `If-Modified-Since`, server **bỏ qua If-Modified-Since**. ETag là validator chính xác hơn và có độ ưu tiên cao hơn.

### 4.3. If-Match: chỉ thực hiện nếu version hiện tại khớp

`If-Match` thường được dùng khi cập nhật hoặc xóa resource:

```http
PUT /books/42 HTTP/1.1
If-Match: "book-v17"
Content-Type: application/json

{"title":"Reactive HTTP in Practice"}
```

Server chỉ thực hiện thay đổi nếu representation hiện tại có strong ETag khớp với một tag trong header. Nếu không khớp, server trả `412 Precondition Failed`.

`If-Match: *` có nghĩa là chỉ tiếp tục nếu resource hiện tồn tại. Điều này hữu ích khi client muốn cập nhật một resource có sẵn và không muốn vô tình tạo mới.

`If-Match` sử dụng **strong comparison**. Weak ETag không phù hợp cho mục đích ngăn lost update vì nó không bảo đảm representation data giống hệt.

### 4.4. If-Unmodified-Since: điều kiện cập nhật theo ngày

Đây là lựa chọn dựa trên timestamp khi client không có ETag:

```http
If-Unmodified-Since: Tue, 15 Apr 2025 10:15:30 GMT
```

Nếu resource đã được sửa sau thời điểm đó, server không nên thực hiện thao tác và có thể trả `412`. Nếu không có thay đổi mới hơn, request tiếp tục.

Nếu request có `If-Match`, server bỏ qua `If-Unmodified-Since` vì ETag là điều kiện chính xác hơn.

### 4.5. If-Range

`If-Range` kết hợp với `Range` khi tải một phần nội dung. Client gửi validator mà nó đã lưu; nếu representation vẫn phù hợp, server trả `206 Partial Content` cho đoạn byte yêu cầu. Nếu validator không còn phù hợp, server bỏ qua Range và trả toàn bộ representation như `200 OK`.

Đây là cơ chế hữu ích cho download có resume. ETag strong thường phù hợp hơn để xác nhận nội dung của các byte range không bị thay đổi.

## 5. 304 và 412 khác nhau như thế nào?

| Status | Ý nghĩa | Trường hợp điển hình |
|---|---|---|
| **200 OK** | Request được xử lý và representation được gửi | Resource mới hơn hoặc không có điều kiện ngăn gửi |
| **304 Not Modified** | GET/HEAD có representation đã cache vẫn hợp lệ | `If-None-Match` khớp hoặc `If-Modified-Since` cho biết chưa thay đổi |
| **412 Precondition Failed** | Điều kiện request không đạt; thao tác không được thực hiện | `If-Match` không khớp hoặc `If-None-Match` thất bại với unsafe method |
| **428 Precondition Required** | Server yêu cầu client gửi precondition | API bắt buộc `If-Match` để ngăn lost update |

`304` là phản hồi cache validation, không mang body. Client giữ representation đã có. Server nên gửi các metadata liên quan để cache cập nhật hoặc nhận diện representation, chẳng hạn ETag, Vary, Cache-Control hoặc Expires khi thích hợp.

`412` là kết quả của một precondition không đạt. Client thường cần đọc lại resource, giải quyết xung đột rồi gửi một request mới với validator mới. Server không được thực hiện side effect của thao tác đã bị từ chối.

`428` không tự động được phát ra bởi mọi cấu hình Spring. Đây là lựa chọn API khi server muốn bắt buộc client cung cấp điều kiện như `If-Match`.

## 6. Thứ tự ưu tiên khi có nhiều điều kiện

HTTP không đánh giá các conditional headers theo thứ tự tùy ý. RFC 9110 định nghĩa thứ tự để các precondition không mâu thuẫn:

1. Nếu có `If-Match`, đánh giá nó trước. Nếu không đạt, trả `412` (trừ trường hợp server xác định thay đổi đã được áp dụng).
2. Nếu không có `If-Match` nhưng có `If-Unmodified-Since`, đánh giá điều kiện này. Nếu không đạt, trả `412`.
3. Nếu có `If-None-Match`, đánh giá nó. Nếu không đạt với GET/HEAD, trả `304`; với method khác, trả `412`.
4. Nếu method là GET/HEAD, không có `If-None-Match` và có `If-Modified-Since`, đánh giá ngày. Nếu representation chưa thay đổi, trả `304`.
5. Nếu GET có `Range` và `If-Range`, đánh giá xem có thể trả partial content hay phải gửi lại toàn bộ.
6. Nếu không có precondition nào ngăn request, xử lý method bình thường.

Điểm thực tế cần nhớ: **If-None-Match có độ ưu tiên cao hơn If-Modified-Since; If-Match cao hơn If-Unmodified-Since.** Không nên tự viết một chuỗi if/else theo thứ tự tùy ý vì có thể trả sai status hoặc thực hiện update dù precondition đã thất bại.

## 7. Spring WebFlux: tạo response kèm validator

Trong functional endpoint, `ServerResponse` có builder để thêm ETag, Last-Modified và cache policy.

Ví dụ trả resource:

```java
public Mono<ServerResponse> getBook(ServerRequest request) {
    int id = Integer.parseInt(request.pathVariable("id"));

    return repository.findById(id)
            .flatMap(book -> {
                String etag = "\"" + book.version() + "\"";
                Instant modified = book.updatedAt()
                        .truncatedTo(ChronoUnit.SECONDS);

                return ServerResponse.ok()
                        .eTag(etag)
                        .lastModified(modified)
                        .cacheControl(CacheControl.maxAge(
                                60, TimeUnit.SECONDS).cachePrivate())
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(book);
            })
            .switchIfEmpty(ServerResponse.notFound().build());
}
```

Đây là snippet cần `Book`, repository, imports và route tương ứng. `version()` phải thay đổi mỗi khi representation tương ứng thay đổi. `updatedAt()` là timestamp có ý nghĩa đối với representation; code chuẩn hóa theo giây để phù hợp HTTP-date.

`eTag` và `lastModified` ở response builder **đặt header validator**. Muốn thực hiện conditional evaluation, handler còn phải dùng helper phù hợp hoặc để cơ chế framework được hỗ trợ thực hiện so sánh.

### 7.1. Dùng ServerWebExchange.checkNotModified

Spring WebFlux cung cấp `ServerWebExchange.checkNotModified` để so sánh validator của resource với conditional headers của request. Method này có overload nhận ETag, Last-Modified hoặc cả hai. Nó chuẩn bị status và response headers khi điều kiện cho biết không cần tiếp tục.

Trong WebFlux.fn, `ServerRequest.exchange()` cung cấp exchange gắn với request:

```java
public Mono<ServerResponse> getBook(ServerRequest request) {
    int id = Integer.parseInt(request.pathVariable("id"));

    return repository.findById(id)
            .flatMap(book -> {
                String etag = "\"" + book.version() + "\"";
                Instant modified = book.updatedAt()
                        .truncatedTo(ChronoUnit.SECONDS);

                if (request.exchange()
                        .checkNotModified(etag, modified)) {
                    return ServerResponse
                            .status(HttpStatus.NOT_MODIFIED)
                            .eTag(etag)
                            .lastModified(modified)
                            .build();
                }

                return ServerResponse.ok()
                        .eTag(etag)
                        .lastModified(modified)
                        .cacheControl(CacheControl.maxAge(
                                60, TimeUnit.SECONDS).cachePrivate())
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(book);
            })
            .switchIfEmpty(ServerResponse.notFound().build());
}
```

Đây là ví dụ cho GET. Khi điều kiện cache đã đạt, helper trả về true và handler tạo response 304 không body. Nếu không đạt điều kiện not-modified, handler tạo response 200 với body.

`ServerRequest.exchange()` là lối truy cập tầng thấp; Javadoc cảnh báo thao tác exchange trực tiếp ngoài các API request/response thông thường có thể tạo hành vi không nhất quán. Ở đây chỉ dùng helper conditional được Spring cung cấp, không tự sửa request/response hoặc ghi body trực tiếp qua exchange.

### 7.2. Conditional update để ngăn lost update

Giả sử hai client cùng đọc `book-v17`:

- Client A cập nhật trước, resource chuyển thành `book-v18`.
- Client B vẫn giữ `book-v17` và gửi PUT với `If-Match: "book-v17"`.
- Server so sánh với version hiện tại và từ chối request của B bằng `412`.

Trong WebFlux, helper `checkNotModified` cũng hỗ trợ precondition cho POST/PUT/DELETE. Ví dụ khái niệm:

```java
public Mono<ServerResponse> updateBook(ServerRequest request) {
    int id = Integer.parseInt(request.pathVariable("id"));

    return repository.findById(id)
            .flatMap(current -> {
                String currentTag = "\"" + current.version() + "\"";
                Instant modified = current.updatedAt()
                        .truncatedTo(ChronoUnit.SECONDS);

                if (request.exchange()
                        .checkNotModified(currentTag, modified)) {
                    return ServerResponse
                            .status(HttpStatus.PRECONDITION_FAILED)
                            .build();
                }

                return request.bodyToMono(UpdateBook.class)
                        .flatMap(command ->
                                repository.updateIfVersion(
                                        id, current.version(), command))
                        .flatMap(updated ->
                                ServerResponse.ok()
                                        .eTag("\"" + updated.version() + "\"")
                                        .lastModified(updated.updatedAt()
                                                .truncatedTo(ChronoUnit.SECONDS))
                                        .bodyValue(updated));
            })
            .switchIfEmpty(ServerResponse.notFound().build());
}
```

Đây là snippet cần repository, DTO và imports. `updateIfVersion` là phần quan trọng: thao tác lưu phải kiểm tra version trong cùng câu lệnh cập nhật hoặc transaction nguyên tử. Chỉ đọc version, kiểm tra ETag trong Java rồi cập nhật sau đó **chưa đủ** nếu một request khác có thể chen vào giữa hai bước.

Ví dụ SQL theo optimistic locking:

```sql
UPDATE books
SET title = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP
WHERE id = ? AND version = ?;
```

Nếu số row được cập nhật là 0, version đã đổi hoặc resource không còn tồn tại. Repository cần phân biệt hai trường hợp theo hợp đồng ứng dụng và trả lỗi/status thích hợp. ETag bảo vệ giao thức HTTP; điều kiện version ở database bảo vệ tính nguyên tử thực tế.

## 8. ETag nên được tạo như thế nào?

### 8.1. Dựa trên revision/version

Nếu database có cột version tăng mỗi lần representation thay đổi:

```java
static String etagFor(Book book) {
    return "\"" + book.version() + "\"";
}
```

Cách này rẻ vì không cần serialize và hash toàn bộ body. Tuy nhiên, chỉ đúng nếu version thay đổi với mọi thay đổi có thể ảnh hưởng representation đã chọn. Nếu DTO ghép dữ liệu từ nhiều bảng, version của một bảng riêng có thể không đủ.

### 8.2. Dựa trên hash representation

Nếu cần tag gắn với bytes thực tế, có thể hash representation đã serialize:

```java
static String strongEtag(byte[] representation)
        throws NoSuchAlgorithmException {
    byte[] digest = MessageDigest.getInstance("SHA-256")
            .digest(representation);

    return "\"" + HexFormat.of().formatHex(digest) + "\"";
}
```

Đây là snippet Java 17+ cần imports. Hash phải được tính trên đúng representation mà server chọn gửi. Nếu response được nén hoặc biến đổi sau khi tính hash, cần bảo đảm validator vẫn đúng theo định nghĩa strong validator và content coding.

Hash body có thể tốn CPU và yêu cầu serialize trước khi quyết định 304. Nếu version hoặc metadata có sẵn, kiểm tra validator bằng metadata có thể tiết kiệm công việc hơn. Tuy nhiên, server vẫn cần truy xuất đủ trạng thái để biết representation hiện tại là gì; 304 không có nghĩa request không tốn bất kỳ chi phí xử lý nào.

### 8.3. Khi nào dùng weak ETag?

Nếu server có thể thay đổi cách serialize hoặc thứ tự field nhưng nội dung vẫn tương đương về mặt ứng dụng, có thể cân nhắc weak ETag:

```http
ETag: W/"catalog-revision-17"
```

Weak tag phù hợp cho cache validation bằng `If-None-Match`, nhưng không dùng nó để bảo đảm optimistic locking với `If-Match`. Khi cần ngăn lost update, dùng strong ETag hoặc version token có ngữ nghĩa strong.

## 9. Chương trình Java 17+ chạy độc lập: độ chính xác của hai validator

Ví dụ sau không dựng HTTP server. Nó minh họa cách tạo ETag từ version ổn định và chuẩn hóa Last-Modified theo giây. Các so sánh conditional thực tế nên giao cho HTTP framework hoặc một implementation tuân thủ RFC 9110.

Cấu trúc:

```text
http-validator-demo/
└── src/demo/ValidatorDemo.java
```

Tệp `src/demo/ValidatorDemo.java`:

```java
package demo;

import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;

public class ValidatorDemo {

    private static String etagForVersion(long version) {
        return "\"book-v" + version + "\"";
    }

    public static void main(String[] args) {
        Instant firstUpdate =
                Instant.parse("2025-04-15T10:15:30.100Z");
        Instant secondUpdate =
                Instant.parse("2025-04-15T10:15:30.800Z");

        Instant firstHttpDate =
                firstUpdate.truncatedTo(ChronoUnit.SECONDS);
        Instant secondHttpDate =
                secondUpdate.truncatedTo(ChronoUnit.SECONDS);

        String lastModified = DateTimeFormatter.RFC_1123_DATE_TIME
                .format(firstHttpDate.atZone(ZoneOffset.UTC));

        String oldTag = etagForVersion(17);
        String newTag = etagForVersion(18);

        System.out.println("old ETag: " + oldTag);
        System.out.println("new ETag: " + newTag);
        System.out.println("Last-Modified: " + lastModified);
        System.out.println("same-second dates equal: "
                + firstHttpDate.equals(secondHttpDate));
        System.out.println("version tags differ: "
                + !oldTag.equals(newTag));
    }
}
```

Biên dịch và chạy bằng JDK 17+ từ thư mục chứa `src`:

```bash
javac -d out src/demo/ValidatorDemo.java
java -cp out demo.ValidatorDemo
```

**Standard output chính xác:**

```text
old ETag: "book-v17"
new ETag: "book-v18"
Last-Modified: Tue, 15 Apr 2025 10:15:30 GMT
same-second dates equal: true
version tags differ: true
```

Giải thích:

1. Hai lần cập nhật xảy ra ở hai thời điểm khác nhau nhưng cùng một giây.
2. Khi chuyển sang HTTP-date, cả hai timestamp đều thành `10:15:30 GMT`.
3. ETag dựa trên version thay đổi từ 17 sang 18, vì vậy vẫn phân biệt được hai phiên bản.
4. Chương trình chỉ minh họa việc tạo validator; nó không tự parse `If-None-Match` hoặc triển khai thuật toán precondition. Không dùng phép so sánh chuỗi đơn giản trong demo để thay thế RFC logic.

## 10. Kiểm thử conditional request

Một endpoint có validator nên được kiểm thử ở cả response đầu tiên và request có điều kiện.

### 10.1. GET lần đầu

Dùng `curl`:

```bash
curl -i http://localhost:8080/books/42
```

Kiểm tra:

- Status `200 OK`.
- Có `ETag` và/hoặc `Last-Modified`.
- `Content-Type` đúng.
- `Cache-Control` phù hợp dữ liệu công khai hay riêng tư.
- Body là representation mong đợi.

### 10.2. GET với ETag hiện tại

```bash
curl -i \
  -H 'If-None-Match: "book-v17"' \
  http://localhost:8080/books/42
```

Nếu ETag vẫn là `"book-v17"`, kỳ vọng `304 Not Modified` và không có body. Nếu resource đã chuyển sang version 18, kỳ vọng `200` với representation và ETag mới.

### 10.3. GET với Last-Modified

```bash
curl -i \
  -H 'If-Modified-Since: Tue, 15 Apr 2025 10:15:30 GMT' \
  http://localhost:8080/books/42
```

Nếu không có thay đổi mới hơn mốc thời gian và request không chứa If-None-Match, server có thể trả 304. Hãy nhớ độ chính xác theo giây.

### 10.4. PUT với If-Match

```bash
curl -i -X PUT \
  -H 'If-Match: "book-v17"' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Reactive HTTP in Practice"}' \
  http://localhost:8080/books/42
```

Nếu version hiện tại là 17 và update hợp lệ, request có thể thành công, resource chuyển version. Nếu version hiện tại đã là 18, kỳ vọng `412 Precondition Failed` và không ghi đè dữ liệu mới.

### 10.5. WebTestClient

Trong test Spring WebFlux, `WebTestClient` có thể xác nhận status và headers:

```java
webTestClient.get()
        .uri("/books/42")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().exists("ETag")
        .expectHeader().exists("Last-Modified");

webTestClient.get()
        .uri("/books/42")
        .header("If-None-Match", "\"book-v17\"")
        .exchange()
        .expectStatus().isNotModified()
        .expectBody().isEmpty();
```

Đây là snippet cần WebTestClient đã bind với router/controller và fixture có version tương ứng. Trong test thực tế, nên lấy ETag từ response đầu tiên rồi dùng lại, thay vì hardcode tag nếu fixture thay đổi.

Test thêm:

- ETag không khớp phải trả body mới và status 200.
- If-Modified-Since được bỏ qua khi If-None-Match có mặt.
- If-Match không khớp trả 412 và không gọi repository update.
- Weak ETag không thỏa strong comparison của If-Match.
- Update đồng thời không thể vượt qua optimistic locking ở database.
- 304 không có body nhưng vẫn có metadata cần thiết.
- Representation biến thể có ETag và Vary đúng.
- Response chứa dữ liệu cá nhân không bị shared cache lưu ngoài ý muốn.

## 11. Lỗi thường gặp

1. **Coi ETag là ID resource.** ETag đại diện một phiên bản representation, không nhất thiết là ID của bản ghi.
2. **Dùng cùng strong ETag cho representation khác nhau.** Nếu JSON, XML, ngôn ngữ hoặc content coding tạo bytes khác, tag phải phù hợp representation hoặc phải dùng weak validator theo ngữ nghĩa.
3. **Dùng weak ETag cho If-Match.** If-Match cần strong comparison; weak tag không bảo vệ lost update.
4. **Tự so sánh ETag bằng equals.** If-None-Match hỗ trợ list, wildcard và weak comparison. Dùng helper framework hoặc implementation đúng RFC.
5. **Chỉ gửi Last-Modified dù resource đổi nhiều lần trong một giây.** HTTP-date có độ phân giải giây; cân nhắc ETag.
6. **Không chuẩn hóa timestamp.** So sánh sub-second timestamp trực tiếp với HTTP-date có thể gây kết quả sai; chuẩn hóa về giây khi tạo validator.
7. **Không cập nhật ETag khi representation đổi.** Client có thể nhận 304 sai và tiếp tục dùng dữ liệu cũ.
8. **Tạo ETag từ một cột version không bao phủ toàn representation.** DTO có thể ghép dữ liệu từ nhiều nguồn; mọi thay đổi ảnh hưởng body phải đổi validator.
9. **Coi 304 là response có body rỗng kiểu 200.** 304 có semantics riêng; client tái sử dụng representation đã lưu.
10. **Trả 304 cho PUT khi If-Match thất bại.** Unsafe method có precondition thất bại thường nhận 412.
11. **Bỏ qua precedence giữa If-None-Match và If-Modified-Since.** Khi có If-None-Match, bỏ qua If-Modified-Since.
12. **Kiểm tra version rồi update không nguyên tử.** Request khác có thể cập nhật chen giữa; dùng optimistic locking hoặc câu lệnh update có điều kiện version.
13. **Dùng ETag như authorization.** Biết tag không chứng minh caller có quyền đọc hoặc sửa resource.
14. **Dùng max-age quá dài cho dữ liệu thay đổi nhanh.** Cache có thể dùng response fresh mà chưa revalidate; chọn freshness theo yêu cầu nghiệp vụ.
15. **Nhầm no-cache và no-store.** no-cache cho phép lưu nhưng yêu cầu kiểm tra lại; no-store chỉ thị không lưu.
16. **Đặt public cache cho response cá nhân.** Dữ liệu theo user/tenant cần cache policy và Vary phù hợp.
17. **Tạo hash body tốn kém ở mọi request.** Nếu có version metadata tin cậy, dùng metadata để tránh serialize/hash lại toàn bộ payload.
18. **Cho rằng Spring tự tạo ETag cho mọi response.** Ứng dụng cần cung cấp validator hoặc cấu hình cơ chế phù hợp; không mặc định mọi WebFlux endpoint đã có ETag.
19. **Dùng Last-Modified của file nhưng quên nội dung được tạo từ nhiều file.** Timestamp của một file không đại diện đầy đủ cho representation tổng hợp.
20. **Bỏ qua lỗi đồng hồ và nguồn timestamp.** Đồng hồ lệch hoặc timestamp sai có thể làm cache nhận dữ liệu cũ; ETag thường ổn định hơn khi có version chính xác.

## 12. Checklist review API

Trước khi bật conditional request cho một resource, xác nhận:

- **Representation:** ETag đang đại diện đúng biến thể nào? Có content negotiation, compression hoặc user-specific content không?
- **Validator strength:** cần strong hay weak? Có đảm bảo cùng strong tag nghĩa là representation data tương đương chính xác không?
- **ETag generation:** tag lấy từ version, revision hay hash? Mọi thay đổi ảnh hưởng body có làm tag đổi không?
- **Last-Modified:** timestamp có nguồn đáng tin không? Đã chuẩn hóa độ phân giải giây chưa?
- **Cache policy:** max-age, private/public, no-cache/no-store có đúng yêu cầu dữ liệu không?
- **GET/HEAD:** If-None-Match và If-Modified-Since có trả 304 đúng không?
- **Update/delete:** If-Match và If-Unmodified-Since có ngăn lost update không?
- **Precedence:** If-None-Match có ưu tiên hơn If-Modified-Since? If-Match có ưu tiên hơn If-Unmodified-Since?
- **Atomicity:** database update có kiểm tra version nguyên tử không?
- **Status:** 304, 412 và 428 có được phân biệt đúng theo API contract không?
- **Headers:** 304 có metadata phù hợp? Response có Vary khi cần không?
- **Security:** cache có vô tình chia sẻ dữ liệu riêng tư giữa user hoặc tenant không?
- **Tests:** đã test tag khớp/không khớp, weak/strong, cùng giây, update đồng thời và representation variants chưa?
- **Observability:** có thể log status 304/412 và tỷ lệ cache revalidation mà không ghi lộ dữ liệu không?

**Ghi nhớ:** `ETag` nhận diện phiên bản representation; `Last-Modified` mô tả thời điểm sửa với độ chính xác theo giây. `If-None-Match` và `If-Modified-Since` giúp cache tránh tải lại body; `If-Match` và `If-Unmodified-Since` giúp client bảo vệ cập nhật khỏi ghi đè thay đổi mới. Dùng đúng strong/weak comparison, đúng thứ tự precondition và optimistic locking nguyên tử ở database. Trong Spring WebFlux, có thể đặt validator bằng `ServerResponse`/`ResponseEntity` và dùng `ServerWebExchange.checkNotModified` để xử lý conditional request theo semantics của HTTP.

## Tài liệu tham khảo

- Spring Framework — [HTTP Caching in WebFlux: ETag, Last-Modified and Cache-Control](https://docs.spring.io/spring-framework/reference/web/webflux/caching.html).
- Spring Framework — [ServerWebExchange Javadoc: checkNotModified](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html).
- Spring Framework — [ServerRequest Javadoc: exchange()](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/ServerRequest.html).
- Spring Framework — [ServerResponse.HeadersBuilder Javadoc: eTag, lastModified and cacheControl](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.HeadersBuilder.html).
- Spring Framework — [Functional Endpoints in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html).
- IETF — [RFC 9110: HTTP Semantics, Entity Tags and Conditional Requests](https://www.rfc-editor.org/rfc/rfc9110.html).
