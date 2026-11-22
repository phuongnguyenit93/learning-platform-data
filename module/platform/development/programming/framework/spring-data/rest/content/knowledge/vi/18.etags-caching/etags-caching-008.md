# Lưu ETag theo đúng URI, tham số và biểu diễn đã yêu cầu

ETag là validator do server trả về để nhận diện một phiên bản của representation. Client có thể lưu ETag cùng dữ liệu đã nhận, gửi lại validator trong request tiếp theo để kiểm tra dữ liệu có thay đổi hay chưa, hoặc dùng nó để bảo vệ thao tác cập nhật khỏi ghi đè thay đổi của client khác.

Với Spring Data REST, ETag thường gắn với thuộc tính phiên bản của entity. Tuy nhiên, một ETag nhận được từ một URI hoặc truy vấn cụ thể chỉ nên được dùng lại trong đúng ngữ cảnh request đó. Không lưu ETag chỉ theo entity id rồi dùng chung cho mọi projection, bộ lọc, trang hoặc media type.

## 1. ETag đại diện cho điều gì?

Server gửi ETag trong response header:

~~~http
HTTP/1.1 200 OK
ETag: "7"
Content-Type: application/hal+json
Cache-Control: private, no-cache
~~~

Giá trị ETag là một validator opaque: client lưu và gửi lại nguyên văn, không cần biết server tạo nó từ số phiên bản, hash nội dung hay một cơ chế nội bộ khác. ETag có thể là strong tag như "7" hoặc weak tag như W/"abc". Dấu ngoặc kép và tiền tố W/ là một phần của giá trị.

Trong Spring Data REST, một entity có trường phiên bản được đánh dấu bằng @Version có thể xuất ra ETag mang giá trị của trường đó. Với Spring Data JPA, dùng jakarta.persistence.Version; với các Spring Data module khác, dùng org.springframework.data.annotation.Version.

Ví dụ entity JPA:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
class Order {

    @Id
    private Long id;

    private String status;

    @Version
    private Long version;

    protected Order() {
    }
}
~~~

Khi repository xuất bản entity này thành REST resource, Spring Data REST có thể dùng trường version làm ETag. Sau khi một cập nhật thành công, phiên bản thay đổi và ETag mới được trả về. Nếu entity không có version metadata phù hợp, không được giả định mọi endpoint đều có ETag; hãy kiểm tra response thực tế.

ETag phục vụ hai mục tiêu liên quan nhưng khác nhau:

- Cache validation: xác định representation đã lưu còn mới hay cần tải lại.
- Optimistic locking: xác định client đang cập nhật dựa trên phiên bản mới nhất hay đang dùng dữ liệu cũ.

## 2. Khóa cache phải chứa đúng URI và tham số

Một resource id không đủ để định danh một bản representation trong cache. Cùng một entity có thể được truy vấn theo nhiều URI hoặc query khác nhau, và mỗi kết quả có thể có nội dung khác nhau.

Ví dụ:

| Request | Ngữ cảnh representation |
|---|---|
| GET /orders/42 | Resource mặc định |
| GET /orders/42?projection=summary | Projection tóm tắt |
| GET /orders/42?projection=detail | Projection chi tiết |
| GET /orders?status=OPEN&page=0&size=20 | Trang đầu của tập đơn hàng đang mở |
| GET /orders?status=CLOSED&page=0&size=20 | Trang đầu của tập đơn hàng đã đóng |
| GET /orders?status=OPEN&page=1&size=20 | Trang tiếp theo của cùng tập kết quả |

Không dùng chung ETag giữa các request này. Một thay đổi trong bộ lọc, projection, phân trang, sắp xếp hoặc tham số khác có thể làm thay đổi representation được chọn. Spring Data REST yêu cầu chỉ sử dụng ETag cho đúng URI và tham số đã tạo ra ETag đó.

**Cache key tối thiểu** cần phân biệt:

1. HTTP method phù hợp, thông thường là GET hoặc HEAD.
2. URI đầy đủ, bao gồm path và toàn bộ query string.
3. Media type client yêu cầu qua Accept.
4. Các request header được server liệt kê trong Vary.
5. Phạm vi người dùng hoặc tenant nếu dữ liệu phụ thuộc vào danh tính truy cập.

Không xóa query string khỏi cache key. Không bỏ các tham số có giá trị mặc định, không gộp các tham số trùng lặp và không tự sắp xếp query parameters để tạo một key chung, trừ khi hợp đồng API xác định rõ các URI đó tương đương. Hãy giữ đúng URL mà client thực sự gửi.

## 3. Representation cũng là một phần của cache key

Cùng một URI có thể trả về các representation khác nhau tùy theo content negotiation. Ví dụ:

~~~http
GET /orders/42
Accept: application/hal+json
~~~

và:

~~~http
GET /orders/42
Accept: application/json
~~~

Client đang yêu cầu hai định dạng khác nhau. Khi lưu ETag, hãy lưu nó cùng giá trị Accept tương ứng. Nếu server trả header Vary, phải phân biệt các giá trị của những request header được liệt kê trong Vary.

Ví dụ response:

~~~http
Vary: Accept, Accept-Language
ETag: "7"
~~~

Khi đó, hai request chỉ có thể dùng chung cache entry nếu URI, query parameters, Accept và Accept-Language tương ứng. Nếu response có Vary: *, không dùng entry đó để đáp ứng request khác.

Trong Spring Data REST, projection qua query parameter như projection=summary cũng phải nằm trong key. Không dựa vào việc hai representation cùng trỏ tới một entity để tái sử dụng validator.

Nếu response phụ thuộc vào người dùng đăng nhập, tenant, quyền truy cập hoặc cookie, cache phải được phân vùng theo đúng phạm vi đó. Không chia sẻ body hoặc ETag của người dùng này cho người dùng khác. Tôn trọng Cache-Control của server; đặc biệt không lưu response có no-store.

## 4. Lưu ETag cùng response body

ETag không thay thế dữ liệu đã tải. Khi server trả 304 Not Modified, response thường không có body; client phải lấy body từ cache entry tương ứng với request đang kiểm tra.

Vì vậy, mỗi entry cần giữ tối thiểu:

- Cache key của request.
- ETag nguyên văn nhận được.
- Response body đã nhận.
- Các metadata cache cần thiết như Cache-Control, Vary và thời điểm nhận response.

Quy trình:

1. Gửi GET với URI, query parameters và representation mong muốn.
2. Khi nhận 200 OK, lưu body và ETag cùng một cache key.
3. Khi gọi lại đúng request, gửi If-None-Match với ETag đã lưu.
4. Nếu nhận 304 Not Modified, dùng lại body trong đúng cache entry; cập nhật metadata response nếu có.
5. Nếu nhận 200 OK, thay body và ETag cũ bằng dữ liệu mới.
6. Nếu response mới không còn ETag, không tiếp tục dùng validator cũ như thể nó vẫn còn hiệu lực cho body mới.

Ví dụ cấu trúc cache trong JavaScript:

~~~javascript
const responseCache = new Map();

function makeCacheKey(url, accept, acceptLanguage = "") {
    const fullUrl = new URL(url, window.location.href).href;

    return JSON.stringify({
        method: "GET",
        url: fullUrl,
        accept,
        acceptLanguage
    });
}

async function getOrder(url) {
    const accept = "application/hal+json";
    const acceptLanguage = "vi";
    const key = makeCacheKey(url, accept, acceptLanguage);
    const cached = responseCache.get(key);

    const headers = new Headers({
        Accept: accept,
        "Accept-Language": acceptLanguage
    });

    if (cached?.etag) {
        headers.set("If-None-Match", cached.etag);
    }

    const response = await fetch(url, {
        method: "GET",
        headers,
        credentials: "same-origin"
    });

    if (response.status === 304) {
        if (!cached) {
            throw new Error("304 received without a matching cached body");
        }

        return cached.body;
    }

    if (!response.ok) {
        throw new Error("GET failed: " + response.status);
    }

    const body = await response.json();
    const etag = response.headers.get("ETag");
    const cacheControl = response.headers.get("Cache-Control") || "";

    if (cacheControl.toLowerCase().includes("no-store")) {
        responseCache.delete(key);
    } else if (etag) {
        responseCache.set(key, {
            etag,
            body,
            cacheControl,
            vary: response.headers.get("Vary")
        });
    } else {
        responseCache.delete(key);
    }

    return body;
}
~~~

Ví dụ này dùng cache trong bộ nhớ và phân biệt URI đầy đủ, Accept cùng Accept-Language. Nếu endpoint có thêm header ảnh hưởng representation, phải đưa giá trị của các header đó vào key theo Vary của response. Nếu ứng dụng có nhiều người dùng hoặc tenant, hãy dùng cache riêng theo phiên/danh tính; không đưa access token thô vào key.

Đoạn code luôn gửi validator khi có entry nên phù hợp để minh họa revalidation. Một cache production còn cần xử lý freshness theo max-age, expiry, invalidation sau thao tác ghi và các chính sách riêng của ứng dụng. Với no-cache, có thể lưu response nhưng phải revalidate trước khi dùng lại; với no-store, không lưu body hoặc validator.

## 5. If-None-Match: kiểm tra cache khi đọc

If-None-Match dùng chủ yếu với GET hoặc HEAD. Client gửi ETag đã lưu cho đúng request:

~~~http
GET /orders/42?projection=detail
Accept: application/hal+json
If-None-Match: "7"
~~~

Nếu representation được chọn vẫn khớp validator, server trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "7"
~~~

304 cho biết client có thể dùng representation đã lưu; không có body mới để thay thế body cũ. Nếu representation đã thay đổi, server trả 200 OK với body và ETag mới.

Không xử lý 304 như một response JSON thông thường. Nếu không có body cache tương ứng với đúng URI, tham số và representation, client không có dữ liệu để tái sử dụng. Hãy thực hiện GET không điều kiện để tải representation đầy đủ.

If-None-Match hỗ trợ weak comparison theo HTTP semantics. Do đó, client không nên tự so sánh chuỗi ETag bằng cách loại bỏ tiền tố W/ hoặc bỏ dấu ngoặc kép.

## 6. If-Match: bảo vệ thao tác cập nhật

Khi client đọc một entity rồi muốn cập nhật, có thể gửi ETag của đúng resource trong If-Match:

~~~http
PATCH /orders/42
Content-Type: application/json
Accept: application/hal+json
If-Match: "7"

{"status":"SHIPPED"}
~~~

Spring Data REST chỉ thực hiện thao tác khi ETag hiện tại của resource khớp với validator được gửi. Nếu một client khác đã cập nhật resource và làm thay đổi version, ETag cũ không còn khớp; server trả HTTP 412 Precondition Failed.

Tình huống:

1. Client A đọc Order 42 và nhận ETag "7".
2. Client B cập nhật Order 42; server phát hành ETag mới, ví dụ "8".
3. Client A gửi PATCH với If-Match: "7".
4. Server từ chối thao tác với 412 vì dữ liệu của A đã cũ.

Khi gặp 412:

- Không tự động gửi lại nội dung PATCH/PUT với ETag mới mà chưa đọc dữ liệu hiện tại.
- GET lại đúng resource để lấy trạng thái mới nhất.
- So sánh thay đổi của client với dữ liệu hiện tại.
- Giải quyết xung đột theo nghiệp vụ rồi mới gửi thao tác cập nhật tiếp theo.

If-Match dùng strong comparison. Một weak ETag có tiền tố W/ không phù hợp làm validator cho điều kiện này. Hãy dùng chính xác ETag server trả về và kiểm tra response thực tế.

Đối với thao tác cập nhật, nên lấy validator từ URI resource mà client sẽ cập nhật. Nếu trước đó chỉ đọc một projection hoặc truy vấn khác, không tự chuyển ETag đó sang URI ghi. Hãy GET đúng resource URI theo hợp đồng API để lấy validator phù hợp.

## 7. Cache-Control quyết định có được lưu hay không

ETag chỉ cung cấp validator. Nó không tự cấp quyền lưu response và cũng không xác định response được dùng lại trong bao lâu. Hãy đọc Cache-Control:

| Directive | Ý nghĩa với client cache |
|---|---|
| max-age=N | Response có thể được dùng lại trong N giây khi còn fresh |
| no-cache | Có thể lưu, nhưng phải kiểm tra lại với server trước khi tái sử dụng |
| no-store | Không lưu response hoặc validator vào cache |
| private | Chỉ cache riêng của client; shared cache không được tái sử dụng theo chính sách này |
| public | Cho phép shared cache lưu khi các điều kiện HTTP khác được đáp ứng |

Ví dụ:

~~~http
Cache-Control: private, no-cache
ETag: "7"
~~~

Client có thể giữ body và ETag trong cache riêng nhưng phải revalidate trước khi dùng lại.

~~~http
Cache-Control: no-store
~~~

Không lưu body hoặc ETag. Không vì thấy có ETag mà bỏ qua no-store.

Khi nhận 304, hãy cập nhật metadata của cache entry theo các header có trong response, đồng thời giữ body cũ. Khi nhận 200, thay thế body và validator bằng cặp mới. Khi response có no-store, xóa entry tương ứng.

## 8. Ví dụ kiểm tra bằng curl

**Đọc đúng một representation:**

~~~bash
curl -i -H "Accept: application/hal+json" "http://localhost:8080/orders/42?projection=detail"
~~~

Lấy giá trị ETag nguyên văn từ response header.

**Kiểm tra lại đúng URI và query parameters:**

~~~bash
curl -i -H "Accept: application/hal+json" -H 'If-None-Match: "7"' "http://localhost:8080/orders/42?projection=detail"
~~~

Nếu dữ liệu không đổi, server có thể trả 304. Không thay URI hoặc projection trong request này.

**Thử một projection khác:**

~~~bash
curl -i -H "Accept: application/hal+json" "http://localhost:8080/orders/42?projection=summary"
~~~

Đây là cache entry khác với projection detail. Không lấy ETag của projection detail để gửi cho request summary.

**Cập nhật có điều kiện:**

~~~bash
curl -i -X PATCH "http://localhost:8080/orders/42" -H "Content-Type: application/json" -H "Accept: application/hal+json" -H 'If-Match: "7"' -d '{"status":"SHIPPED"}'
~~~

Nếu ETag hiện tại vẫn là "7", thao tác có thể thành công và response trả ETag mới. Nếu version đã đổi, xử lý HTTP 412 bằng cách đọc lại và giải quyết xung đột.

Các URI, entity và giá trị ETag trong ví dụ là minh họa. Hãy dùng endpoint và validator thực tế từ response của ứng dụng.

## 9. Lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Dùng ETag của /orders/42 cho /orders/42?projection=detail | Hai URI chọn representation khác nhau | Lưu ETag theo từng URI và query string |
| Dùng ETag của trang 0 cho trang 1 | Kết quả phân trang khác nhau | Bao gồm page, size, sort và filter trong key |
| Dùng ETag HAL JSON cho representation JSON khác | Accept khác nhau | Tách cache theo media type và Vary |
| Chỉ lưu ETag, không lưu body | 304 không chứa representation mới | Lưu body và validator thành một entry |
| Nhận 304 nhưng cache entry đã mất | Validator không còn gắn với body tương ứng | GET không điều kiện để lấy body mới |
| Gặp 412 khi PATCH/PUT | ETag cũ do client khác đã cập nhật | GET lại, đối chiếu và giải quyết xung đột |
| ETag không xuất hiện trong JavaScript | CORS không expose response header | Cấu hình Access-Control-Expose-Headers: ETag |
| Request có If-None-Match hoặc If-Match bị CORS chặn | Server chưa cho phép request header tùy chỉnh | Cho phép các header này trong Access-Control-Allow-Headers |
| Dùng cache của người dùng khác | Cache không phân vùng theo danh tính hoặc tenant | Dùng private cache theo phiên và tuân thủ Cache-Control |

Với ứng dụng gọi API khác origin, JavaScript chỉ đọc được ETag khi server expose header đó qua CORS. Nếu gửi If-None-Match hoặc If-Match, cấu hình CORS cần cho phép các request header tương ứng. Việc expose ETag không thay thế kiểm tra quyền truy cập hoặc chính sách cache.

## 10. Checklist triển khai

- [ ] Xác nhận endpoint thực sự trả ETag.
- [ ] Nếu dùng Spring Data REST optimistic locking, đánh dấu thuộc tính version bằng @Version đúng loại persistence.
- [ ] Lưu ETag cùng response body.
- [ ] Cache key giữ nguyên URI đầy đủ và toàn bộ query parameters.
- [ ] Phân biệt Accept và mọi request header có trong Vary.
- [ ] Phân vùng cache theo người dùng/tenant khi dữ liệu có phạm vi riêng.
- [ ] Tôn trọng Cache-Control, đặc biệt no-store và no-cache.
- [ ] Gửi If-None-Match chỉ với validator của đúng request representation.
- [ ] Dùng If-Match cho thao tác ghi khi API hỗ trợ optimistic locking.
- [ ] Xử lý 304 bằng body đã lưu và xử lý 412 bằng quy trình đọc lại, đối chiếu.
- [ ] Thay body và ETag sau response 200 mới; xóa entry khi response không còn validator phù hợp hoặc yêu cầu no-store.

## Tài liệu tham khảo

- [Spring Data REST — Conditional Operations with Headers](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html): @Version, ETag, If-Match, If-None-Match, HTTP 304/412 và quy tắc chỉ tái sử dụng ETag cho đúng URI cùng tham số.
- [RFC 9110 — HTTP Semantics, ETag](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.8.3): ETag là opaque validator cho selected representation; weak và strong entity tags.
- [RFC 9110 — If-None-Match](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.2): điều kiện GET/HEAD và weak comparison.
- [RFC 9110 — Vary](https://www.rfc-editor.org/rfc/rfc9110.html#section-12.5.5): các request header cần phân biệt trong cache key.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html): freshness, validation và cách cache tái sử dụng response.
- [Spring Framework — HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): Cache-Control, ETag và response 304 trong Spring.
