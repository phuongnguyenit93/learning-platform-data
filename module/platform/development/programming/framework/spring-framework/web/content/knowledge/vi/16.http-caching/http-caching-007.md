# If-Match, precondition và kiểm soát cập nhật đồng thời trong Spring MVC

> **Phạm vi:** HTTP conditional requests theo RFC 9110, Spring Web MVC trên Servlet stack, Java 17+ và Spring Boot 3.x/Spring Framework 6.x. Chủ đề giải thích cách dùng **`ETag` + `If-Match`** để tránh **lost update**, phân biệt `412 Precondition Failed` và `428 Precondition Required`, so sánh mạnh/yếu, các header điều kiện khác và **tính nguyên tử của bước kiểm tra–ghi**. Bài có một ví dụ REST Java chạy được, lệnh cURL tái hiện hai người chỉnh cùng tài nguyên, kiểm thử MockMvc, chiến lược DB optimistic locking và lưu ý bảo mật.

## 1. Bài toán: hai người ghi đè thay đổi của nhau

Giả sử một API lưu tài liệu chung. Ban đầu tài liệu có:

```json
{
  "id": "1",
  "content": "Bản đầu",
  "revision": 1
}
```

Alice và Bob đồng thời mở tài liệu. Alice sửa thành `"Nội dung của Alice"` và lưu thành công. Bob vẫn đang xem bản revision 1 rồi nhấn Save với `"Nội dung của Bob"`.

Nếu API chỉ dùng PUT thông thường và ghi đè không kiểm tra phiên bản:

```text
T0: server revision 1: "Bản đầu"
T1: Alice GET -> revision 1
T2: Bob   GET -> revision 1
T3: Alice PUT "Nội dung của Alice" -> revision 2
T4: Bob   PUT "Nội dung của Bob"   -> revision 3
                                               |
                                        Mất thay đổi của Alice
```

Đây là **lost update**: bản cập nhật sau ghi đè bản cập nhật trước dù người dùng thứ hai chưa hề thấy thay đổi mới.

Để tránh, server xuất một **validator** cho phiên bản biểu diễn hiện tại, chẳng hạn:

```http
HTTP/1.1 200 OK
ETag: "rev-1"
Content-Type: application/json

{"id":"1","content":"Bản đầu","revision":1}
```

Khi PUT, client gửi ETag mà mình đã quan sát:

```http
PUT /api/docs/1 HTTP/1.1
Content-Type: application/json
If-Match: "rev-1"

{"content":"Nội dung của Alice"}
```

Server chỉ cập nhật nếu representation hiện tại vẫn có ETag tương ứng. Alice cập nhật thành công thì server cấp ETag mới `"rev-2"`. Bob gửi `If-Match: "rev-1"` đã cũ: server **không ghi đè** và trả `412 Precondition Failed`.

**Ghi nhớ:** `If-Match` không phải lệnh khóa tài liệu trong thời gian người dùng mở form. Nó là **điều kiện kiểm tra tại thời điểm server xử lý request**. Để thật sự chống lost update, bước so sánh điều kiện và ghi dữ liệu phải diễn ra **nguyên tử** so với các writer khác.

## 2. Khái niệm: representation, validator và ETag

### 2.1. ETag là gì?

`ETag` (entity tag) là metadata phản hồi HTTP cho biết phiên bản của **selected representation**. Ví dụ:

```http
ETag: "rev-42"
```

Về mặt cú pháp, entity tag là một giá trị được đặt trong dấu nháy kép; nó **không nhất thiết là hash** và client nên coi phần bên trong là **opaque identifier**. Server quyết định cách cấp, so sánh và thay đổi tag.

Các chiến lược thường thấy:
- Revision number của bản ghi, ví dụ `"rev-42"`.
- Hash của bytes biểu diễn, khi chi phí tính hash và encoding phù hợp.
- Opaque random token được đổi mỗi khi representation thay đổi.
- Token tổng hợp từ version và variant metadata.

**Không được kết luận rằng hai ETag giống nhau luôn chứng minh người dùng có quyền truy cập.** ETag chỉ phục vụ validation/conditional requests, không thay authentication và authorization.

### 2.2. Strong và weak ETag

Ví dụ:

```http
ETag: "abc123"
ETag: W/"abc123"
```

- `"abc123"`: **strong validator**.
- `W/"abc123"`: **weak validator** (tiền tố `W/`), có thể xem hai representations tương đương theo nghĩa yếu dù bytes khác.
- `If-Match` **bắt buộc dùng strong comparison**. Một weak tag **không khớp** với strong tag cùng phần chữ, và hai weak tags cũng **không** được coi là match mạnh.

Bảng:

| ETag hiện tại | If-Match client | Kết quả điều kiện |
| --- | --- | --- |
| `"rev-7"` | `"rev-7"` | Khớp mạnh |
| `"rev-7"` | `"rev-6"` | Không khớp |
| `"rev-7"` | `W/"rev-7"` | Không khớp mạnh |
| `W/"rev-7"` | `W/"rev-7"` | Không khớp mạnh |
| `"rev-7"` | `"rev-5", "rev-7"` | Có một tag khớp, điều kiện đúng |
| Tài nguyên hiện tồn tại | `*` | Điều kiện tồn tại đúng |
| Tài nguyên chưa tồn tại | `*` | Điều kiện tồn tại sai |

Một số converter, content encoding như gzip và các representation variants có thể thay đổi bytes được gửi. Strong validator phải tuân theo yêu cầu của **representation được chọn**; đừng dùng một strong ETag giống hệt cho hai encoded representations khác nhau nếu điều đó làm vi phạm strong validation. Một version database có thể là cơ sở để dựng strong ETag khi policy đảm bảo nó thay đổi với mọi thay đổi có liên quan tới representation.

### 2.3. Nếu ETag chứa hash thì có an toàn hơn không?

Hash không tự đồng nghĩa với bảo mật:
- Hash không kiểm tra quyền.
- Hash của nội dung bí mật nếu lộ qua ETag có thể tiết lộ thông tin về trạng thái hoặc cấu trúc dữ liệu trong một số mô hình.
- Hash tính trên nội dung JSON phụ thuộc chính sách serialize: thứ tự fields, bỏ null, encoding, content coding, locale hoặc projection.
- Hash yếu/không quản lý variant có thể va chạm hoặc đánh đồng các representations khác nhau.

Với REST CRUD thông thường, revision monotonically increasing được bảo vệ trong database thường đơn giản hơn hashing toàn bộ body trong mỗi lần PUT.

## 3. Header If-Match thực sự yêu cầu điều gì?

Theo RFC 9110 §13.1.1, `If-Match` khiến request phụ thuộc vào một trong hai điều kiện:
1. Nếu giá trị là `*`, target resource có **ít nhất một current representation**.
2. Nếu là danh sách ETag, tồn tại **một strong ETag match** giữa validator client đưa ra và current selected representation.

Ví dụ:

```http
If-Match: "rev-7"
```

```http
If-Match: "rev-6", "rev-7"
```

```http
If-Match: *
```

Một server thực thi điều kiện thành công mới được tiếp tục đến phép ghi; khi điều kiện không thỏa, thông thường trả **412 Precondition Failed**, không áp dụng PUT/DELETE gây thay đổi. RFC cho phép một ngoại lệ giới hạn khi server chứng minh được thao tác thay đổi state đã **thực sự xảy ra trước đó** (ví dụ retry mất response), nhưng không nên tùy tiện trả 2xx khi điều kiện không khớp.

### 3.1. Dấu `*` không giúp phát hiện stale edit

`If-Match: *` chỉ yêu cầu resource **tồn tại**. Nếu Alice vừa đổi revision từ 1 sang 2, Bob gửi `If-Match: *` vẫn có thể được chấp nhận, và việc ghi đè Alice có thể xảy ra.

Do đó:
- Trong API thực thi đầy đủ semantics HTTP, `*` là một giá trị hợp lệ khi target tồn tại.
- Nếu sản phẩm **bắt buộc chống lost update cho mọi chỉnh sửa**, có thể áp một **application contract mạnh hơn**, chẳng hạn chỉ chấp nhận **concrete strong version tag** cho route cập nhật; cần document rõ policy và status cho yêu cầu không phù hợp.
- Trong ví dụ runnable dưới đây, để minh họa RFC, `*` được chấp nhận khi resource tồn tại nhưng bài học **nói rõ nó không bảo vệ chống stale overwrite**.

### 3.2. Precondition được đánh giá khi nào?

HTTP preconditions **không** phải biện pháp bỏ qua quyền truy cập. Server cần thực thi authentication/authorization, kiểm tra target resource và các điều kiện xử lý request hợp lệ trước khi tiến hành phép ghi. RFC 9110 chỉ yêu cầu đánh giá preconditions trong bối cảnh mà đáp ứng không điều kiện (bỏ qua preconditions) lẽ ra là thành công hoặc một số trường hợp lỗi phù hợp.

Không trả ETag hoặc thông tin existence nhạy cảm cho người không được phép chỉ vì họ gửi `If-Match`. Ví dụ một API có quyền người dùng không đủ vẫn nên trả 401/403/404 theo hợp đồng bảo mật, không tự động để 412 làm lộ resource/version.

### 3.3. Ưu tiên giữa các header điều kiện

RFC 9110 quy định thứ tự xử lý preconditions khi nhiều header cùng có mặt:

1. `If-Match`, nếu có, được xét trước.
2. `If-Unmodified-Since` chỉ được xét khi không có `If-Match`.
3. `If-None-Match` được xét tiếp theo; với GET/HEAD khi nó không thỏa có thể trả 304, với phương thức thay đổi state thì 412.
4. `If-Modified-Since` áp cho GET/HEAD khi không có `If-None-Match`; `If-Range` có quy tắc riêng cho Range request.

**Đừng viết code chỉ đọc `If-Unmodified-Since` dù đã có `If-Match` rồi cộng hai điều kiện bằng phép AND tùy ý.** Nếu triển khai HTTP conditional requests tổng quát, cần tuân RFC và sử dụng framework/container API đúng phiên bản.

## 4. Phân biệt 200, 204, 304, 409, 412 và 428

| HTTP status | Khi nào thường phù hợp? | Có cập nhật không? |
| --- | --- | --- |
| `200 OK` | PUT thành công và trả representation mới | Có |
| `204 No Content` | PUT/DELETE thành công, không gửi body | Có, hoặc xóa thành công |
| `304 Not Modified` | GET/HEAD với `If-None-Match` hoặc cache validator tương thích | **Không phải cập nhật** |
| `409 Conflict` | Xung đột domain/state không thuần do precondition header sai | Thường không |
| `412 Precondition Failed` | `If-Match` không khớp current representation; hoặc precondition khác không thỏa | **Không được áp dụng** phép ghi |
| `428 Precondition Required` | API yêu cầu điều kiện, client **không gửi** điều kiện bắt buộc | Không |
| `400 Bad Request` | Cú pháp If-Match/request body không hợp lệ theo contract | Không |
| `404 Not Found` | Target resource không tồn tại hoặc bị ẩn theo ACL | Không |
| `401/403` | Chưa xác thực/không đủ quyền | Không |

**Không nhầm 304 và 412:**
- `If-None-Match` trên GET giúp **cache revalidation**: dữ liệu chưa đổi thì trả `304` để tránh gửi lại body.
- `If-Match` trên PUT/PATCH/DELETE giúp **kiểm soát ghi**: version đã đổi thì `412`.

**Không nhầm 409 và 412:** Nếu đối tượng ở đúng revision nhưng domain state không cho phép thao tác (ví dụ đơn hàng đã giao không được sửa địa chỉ), `409` có thể phù hợp. Nếu validator client không còn trùng revision hiện hành, `412` diễn đạt chính xác lý do hơn.

### 4.1. Ví dụ tuần tự đầy đủ

```http
GET /api/docs/1
→ 200 OK
ETag: "rev-1"

{"id":"1","content":"Bản đầu","revision":1}
```

Alice gửi:

```http
PUT /api/docs/1
If-Match: "rev-1"
Content-Type: application/json

{"content":"Alice đã sửa"}
```

Server trả:

```http
HTTP/1.1 200 OK
ETag: "rev-2"

{"id":"1","content":"Alice đã sửa","revision":2}
```

Bob gửi lại tag cũ:

```http
PUT /api/docs/1
If-Match: "rev-1"
Content-Type: application/json

{"content":"Bob đã sửa trên bản cũ"}
```

Server trả:

```http
HTTP/1.1 412 Precondition Failed
```

**Không thay đổi** giá trị Alice vừa lưu. Bob cần GET bản mới, hiển thị chênh lệch hoặc gộp nội dung theo UX rồi thử lại bằng tag hiện hành. Không tự động retry PUT bằng ETag mới trên dữ liệu Bob viết từ bản cũ, vì làm vậy phá mục tiêu optimistic concurrency.

## 5. If-Match khác If-None-Match thế nào?

| Header | Semantics cốt lõi | Mẫu sử dụng |
| --- | --- | --- |
| `If-Match: "tag"` | Chỉ thực hiện nếu **có strong match** với current selected representation | PUT/PATCH/DELETE tránh lost update |
| `If-Match: *` | Chỉ thực hiện khi resource hiện tồn tại | Tránh ghi vào resource chưa tồn tại, **không kiểm soát revision** |
| `If-None-Match: "tag"` | Chỉ thực hiện khi **không có weak match** theo RFC; với GET/HEAD phù hợp có thể trả 304 | Cache revalidation |
| `If-None-Match: *` | Chỉ thực hiện khi target **chưa tồn tại** | Conditional create (PUT/POST phù hợp) |
| `If-Unmodified-Since: <date>` | Không cập nhật nếu tài nguyên đã thay đổi sau thời điểm đó | Phương án thay thế khi không có ETag |
| `If-Modified-Since: <date>` | GET/HEAD nếu tài nguyên đã thay đổi sau mốc đó | Cache revalidation dựa trên Last-Modified |

Ngày giờ HTTP thường chỉ có độ phân giải giây; nhiều cập nhật liên tiếp trong một giây có thể không được phân biệt tốt. Với tài nguyên thay đổi nhanh, concrete strong ETag dựa trên version nguyên tử thường an toàn hơn `If-Unmodified-Since`.

### 5.1. Conditional create

Giả sử client muốn tạo resource ở URI do client chọn, nhưng không muốn ghi đè bản đã có:

```http
PUT /api/configs/app-A
If-None-Match: *
Content-Type: application/json

{"mode":"safe"}
```

Nếu resource **đã tồn tại**, điều kiện sai: trả `412`. Nếu chưa tồn tại và caller đủ quyền, server có thể tạo mới. Kiểm tra tồn tại và insert cần là một thao tác nguyên tử như UNIQUE constraint/transaction; nếu hai request tạo đồng thời thì chỉ một được phép thắng theo policy.

Đây là **một tình huống khác** với `If-Match` dùng cho update.

## 6. Spring MVC: ResponseEntity, ETag và WebRequest

### 6.1. Trả ETag qua ResponseEntity

```java
@GetMapping("/{id}")
public ResponseEntity<DocumentDto> get(@PathVariable String id) {
    DocumentDto dto = service.find(id);
    return ResponseEntity.ok()
            .eTag("\"rev-" + dto.revision() + "\"")
            .body(dto);
}
```

Đây là **snippet minh họa**, cần `DocumentDto` và `service` phù hợp. Phương thức `ResponseEntity.BodyBuilder#eTag(String)` đặt ETag header. Đảm bảo chuỗi tag biểu diễn strong tag đúng; nhiều version của Spring tự bổ sung dấu nháy kép khi cần, nhưng cung cấp chuỗi đã quote giúp hợp đồng rõ ràng.

Không gắn `"rev-7"` cho representation đã đổi nội dung mà revision chưa tăng. Không đưa ETag dựa trên secret raw vào output nếu tạo rủi ro disclosure.

### 6.2. Đọc If-Match trong controller

```java
@PutMapping("/{id}")
public ResponseEntity<?> put(
        @PathVariable String id,
        @RequestHeader HttpHeaders headers,
        @RequestBody UpdateDocument request) {

    List<String> validators = headers.getIfMatch();
    // Phải kiểm tra thiếu header, so sánh MẠNH và thực hiện update nguyên tử.
    return ResponseEntity.noContent().build();
}
```

Đây là **snippet, không phải implementation an toàn**. `HttpHeaders#getIfMatch()` là API Spring để đọc danh sách validator, có thể ném `IllegalArgumentException` nếu parse lỗi. Việc đọc thành công không có nghĩa server đã thỏa precondition; dịch vụ cập nhật phải so ETag hiện tại với validators.

Một cách khác là `@RequestHeader(value="If-Match", required=false) String header`, nhưng code production phải xử lý đúng HTTP entity-tag list, cú pháp quote/comma, weak tags và wildcard. Không dùng `String.contains(currentTag)` hay chia `split(",")` bất chấp dấu nháy; đó không phải strong ETag comparison theo RFC.

### 6.3. WebRequest#checkNotModified

Spring có:

```java
@GetMapping("/{id}")
public ResponseEntity<DocumentDto> get(
        @PathVariable String id, WebRequest webRequest) {

    DocumentDto dto = service.find(id);
    String currentETag = "\"rev-" + dto.revision() + "\"";

    if (webRequest.checkNotModified(currentETag)) {
        return null; // Handler return type cần thiết kế phù hợp.
    }

    return ResponseEntity.ok().eTag(currentETag).body(dto);
}
```

Đây là **minh họa ý tưởng**, nhưng việc return `null` không hợp lý trong method được khai báo `ResponseEntity<DocumentDto>` trong mọi thiết kế; với một số signatures Spring MVC xử lý null đặc biệt, cần kiểm thử cụ thể. Pattern phổ biến trong tài liệu Spring là method trả `String` tên view, `void` hoặc loại phù hợp, khi `checkNotModified(...)` trả true thì kết thúc xử lý.

API `WebRequest#checkNotModified(etag)`/`ServletWebRequest` hỗ trợ GET/HEAD conditional cache và cũng nhận biết conditional POST/PUT/DELETE ở một số đường xử lý. **Tuy nhiên:** nó không thay trách nhiệm **atomic compare-and-set ở storage layer**. Nếu check ETag ở controller rồi người khác ghi trước khi service update, vẫn có thể lost update.

Ví dụ phương thức GET view theo tài liệu:

```java
@GetMapping("/pages/{id}")
public String page(@PathVariable String id,
                   WebRequest webRequest,
                   Model model) {
    Article article = articleService.find(id);
    if (webRequest.checkNotModified(article.etag())) {
        return null;
    }
    model.addAttribute("article", article);
    return "article";
}
```

Snippet cần `Article`, `articleService` và view resolver, chỉ để minh họa conditional GET. Nếu ứng dụng dùng `ResponseEntity.eTag(...)`, hãy xác minh behavior của Spring MVC return-value handlers với `If-None-Match` và không gọi `checkNotModified` trùng lặp không cần thiết.

### 6.4. Vì sao không chỉ check ở controller?

**Code lỗi race:**

```java
// ANTI-PATTERN: check và write là hai hành động không khóa cùng nhau.
if (ifMatch.equals(repo.findById(id).etag())) {
    repo.save(newContent);
}
```

Hai request có thể cùng đọc revision 1, cùng thấy điều kiện đúng, rồi lần lượt ghi đè nhau. Header HTTP là bước giao tiếp; **backend transaction/lock/CAS mới là nơi bảo đảm kết quả cuối cùng**.

## 7. Ví dụ chạy được: Spring Boot 3.x + Java 17, synchronized CAS

Ví dụ dùng duy nhất dependency **Spring Web**, dữ liệu ở RAM và lock `synchronized`. Mục tiêu là chứng minh **một request PUT stale bị từ chối** và phép so sánh–ghi **nguyên tử trong một JVM**.

**Quan trọng:** `synchronized` trong demo chỉ bảo vệ một instance của `DocumentStore` trong **một JVM**. Nếu triển khai 2 pods/instances hoặc có database, cần **database optimistic locking/atomic UPDATE** như mục 10. Dữ liệu in-memory mất khi restart và ví dụ không có authentication, authorization, database hay CSRF.

### 7.1. Khởi tạo project

Tạo Maven project tại [Spring Initializr](https://start.spring.io/), Java 17+, Spring Boot 3.x, dependency **Spring Web**:

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

Đây là phần dependency của POM do Initializr chuẩn bị. Tạo một file Java độc lập dưới `src/main/java/com/example/demo/DemoApplication.java`.

### 7.2. Toàn bộ mã Java

```java
package com.example.demo;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

// Value objects bất biến, an toàn khi rời vùng synchronized.
record DocumentView(String id, String content, long revision) {
    String strongETag() {
        return "\"rev-" + revision + "\"";
    }
}

record ReplaceDocument(String content) {
}

@Service
class DocumentStore {

    private String content = "Ban dau";
    private long revision = 1L;

    private static void requireExistingId(String id) {
        if (!"1".equals(id)) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Document not found");
        }
    }

    // Snapshot đọc không xen vào một update chưa hoàn tất.
    public synchronized DocumentView get(String id) {
        requireExistingId(id);
        return new DocumentView(id, content, revision);
    }

    // So sánh If-Match và cập nhật bên trong CÙNG khóa.
    public synchronized DocumentView replace(
            String id,
            List<String> requestedValidators,
            ReplaceDocument command) {

        requireExistingId(id);

        if (command == null
                || command.content() == null
                || command.content().isBlank()
                || command.content().length() > 200) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid content");
        }

        String currentETag = "\"rev-" + revision + "\"";

        // RFC: * đúng khi target đã tồn tại.
        // * KHÔNG bảo vệ khỏi stale overwrite.
        boolean matches = requestedValidators.contains("*");

        if (!matches) {
            for (String requested : requestedValidators) {
                // So sánh bằng equality với STRONG tag.
                // W/"rev-N" khác "rev-N" và sẽ không match.
                if (currentETag.equals(requested)) {
                    matches = true;
                    break;
                }
            }
        }

        if (!matches) {
            throw new ResponseStatusException(
                    HttpStatus.PRECONDITION_FAILED,
                    "If-Match does not match current revision");
        }

        // Khi đã giữ lock, không writer nào xen giữa check và write.
        content = command.content();
        revision++;
        return new DocumentView(id, content, revision);
    }
}

@RestController
@RequestMapping("/api/docs")
class DocumentController {

    private final DocumentStore store;

    DocumentController(DocumentStore store) {
        this.store = store;
    }

    @GetMapping("/{id}")
    public ResponseEntity<DocumentView> get(
            @PathVariable("id") String id) {

        DocumentView current = store.get(id);

        return ResponseEntity.ok()
                .eTag(current.strongETag())
                .cacheControl(CacheControl.noStore())
                .body(current);
    }

    @PutMapping(
            path = "/{id}",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<DocumentView> replace(
            @PathVariable("id") String id,
            @RequestHeader HttpHeaders headers,
            @RequestBody ReplaceDocument command) {

        if (!headers.containsKey(HttpHeaders.IF_MATCH)) {
            throw new ResponseStatusException(
                    HttpStatus.PRECONDITION_REQUIRED,
                    "Send If-Match from a prior GET");
        }

        List<String> validators;
        try {
            validators = headers.getIfMatch();
        } catch (IllegalArgumentException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Malformed If-Match");
        }

        if (validators.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Empty If-Match");
        }

        // Atomic compare and write nằm trong store.
        DocumentView updated =
                store.replace(id, validators, command);

        return ResponseEntity.ok()
                .eTag(updated.strongETag())
                .cacheControl(CacheControl.noStore())
                .body(updated);
    }
}
```

### 7.3. Những bảo đảm và giới hạn của code

- `DocumentView` là record bất biến; GET đọc snapshot và gắn ETag của **chính revision snapshot đó**.
- `@RequestHeader HttpHeaders` dùng parser chính thức `getIfMatch()`, không kiểm tra một string bằng `contains()`.
- Không có If-Match trả `428`; validator không match trả `412`.
- Nếu client gửi `W/"rev-1"`, chuỗi weak khác `"rev-1"`; kết quả precondition thất bại.
- Nếu client gửi nhiều strong tags, có ít nhất một token trùng current tag thì điều kiện đúng.
- `If-Match: *` được chấp nhận khi document có ID `1`, **đúng semantics tồn tại**, nhưng không đảm bảo chống ghi đè stale. API muốn bảo đảm mỗi cập nhật có version phải đặt rule từ chối wildcard.
- `synchronized` bảo đảm hai threads không thể cùng kiểm tra và thay đổi một instance `DocumentStore` ở cùng thời điểm. Hai request cùng `If-Match: "rev-1"` đến gần như đồng thời: một request đổi revision thành 2, request còn lại nhận 412.
- `CacheControl.noStore()` ở đây là chính sách tránh caching tài liệu; vẫn hoàn toàn có thể cung cấp ETag làm version validator. Nếu dữ liệu cần cache trong môi trường khác, có thể chọn cache policy phù hợp quyền/vary/visibility.
- Code không xử lý HTTP authentication/authorization. Ứng dụng thật phải kiểm tra user/tenant/ACL **trước khi tiết lộ current ETag hoặc ghi tài nguyên**.
- Mã không hỗ trợ create, delete, patch, variants, persistence hoặc automatic merge; không được coi là một HTTP resource server tổng quát.
- Phương thức GET có `ResponseEntity.eTag(...)`; Spring MVC có thể tự xử lý conditional GET/HEAD với ETag theo cơ chế return value của framework. Các kiểm thử bên dưới tập trung vào PUT và version.

### 7.4. Chạy server

```bash
# Linux/macOS
./mvnw spring-boot:run

# Windows PowerShell / CMD
mvnw.cmd spring-boot:run
```

Mặc định app nghe ở `http://localhost:8080` nếu không cấu hình `server.port`/context path.

### 7.5. Bước 1: GET và ghi nhớ ETag

```bash
curl -i http://localhost:8080/api/docs/1
```

Các phần quan trọng:

```http
HTTP/1.1 200
ETag: "rev-1"
Cache-Control: no-store
Content-Type: application/json

{"id":"1","content":"Ban dau","revision":1}
```

Các header khác (Date, Connection, Transfer-Encoding/Content-Length) và thứ tự JSON fields phụ thuộc container/converter, nên không so nguyên văn toàn response.

### 7.6. Bước 2: Alice PUT với revision đang có

```bash
curl -i -X PUT http://localhost:8080/api/docs/1 \
  -H 'Content-Type: application/json' \
  -H 'If-Match: "rev-1"' \
  -d '{"content":"Alice edit"}'
```

Dự kiến status **200 OK**, ETag mới `"rev-2"`, body:

```json
{"id":"1","content":"Alice edit","revision":2}
```

### 7.7. Bước 3: Bob gửi tag cũ

```bash
curl -i -X PUT http://localhost:8080/api/docs/1 \
  -H 'Content-Type: application/json' \
  -H 'If-Match: "rev-1"' \
  -d '{"content":"Bob stale edit"}'
```

Dự kiến status **412 Precondition Failed**; không có cập nhật nào. Gọi GET lại:

```bash
curl -sS http://localhost:8080/api/docs/1
```

Body vẫn là:

```json
{"id":"1","content":"Alice edit","revision":2}
```

Đây là kết quả bảo vệ chống lost update. API có thể kèm current ETag hoặc một error DTO cho 412 tùy hợp đồng và quyền; không tự động trả toàn nội dung tài liệu nếu caller không được phép.

### 7.8. Bước 4: Bob gửi lại đúng ETag mới

```bash
curl -i -X PUT http://localhost:8080/api/docs/1 \
  -H 'Content-Type: application/json' \
  -H 'If-Match: "rev-2"' \
  -d '{"content":"Bob accepted after review"}'
```

Dự kiến **200**, ETag `"rev-3"` và revision 3. Đây là ví dụ giả định Bob đã **xem và chấp nhận** nội dung mới; nếu client tự retry mà không cho người dùng xem conflict, có thể ghi đè thay đổi trước đó.

### 7.9. Bước 5: không gửi If-Match

```bash
curl -i -X PUT http://localhost:8080/api/docs/1 \
  -H 'Content-Type: application/json' \
  -d '{"content":"Unsafe update without validator"}'
```

Dự kiến **428 Precondition Required**. Khi 428, response nên hướng dẫn client GET rồi gửi ETag. RFC 6585 yêu cầu response 428 **không được cache**.

### 7.10. Bước 6: weak ETag không hợp lệ cho If-Match

```bash
curl -i -X PUT http://localhost:8080/api/docs/1 \
  -H 'Content-Type: application/json' \
  -H 'If-Match: W/"rev-3"' \
  -d '{"content":"Weak validator"}'
```

Dự kiến **412**, vì `If-Match` đòi strong comparison, current `"rev-3"` không khớp `W/"rev-3"`.

### 7.11. Bước 7: wildcard và rủi ro ghi đè

```bash
curl -i -X PUT http://localhost:8080/api/docs/1 \
  -H 'Content-Type: application/json' \
  -H 'If-Match: *' \
  -d '{"content":"Wildcard overwrites current value"}'
```

Tài liệu tồn tại nên demo trả **200** và revision tăng lên 4. **Không dùng cách này** khi UX yêu cầu ngăn stale edit: dấu `*` không mang thông tin revision. Chính sách app có thể yêu cầu một tag cụ thể, ví dụ `"rev-3"`.

### 7.12. Windows PowerShell

PowerShell có thể có alias `curl`; dùng `curl.exe` một dòng:

```powershell
curl.exe -i -X PUT "http://localhost:8080/api/docs/1" -H "Content-Type: application/json" -H 'If-Match: "rev-1"' --data-raw '{"content":"Alice edit"}'
```

**Lưu ý:** cách truyền dấu quote của JSON đối với `curl.exe` trên Windows có thể khác Bash tùy PowerShell phiên bản và native-argument quoting. Nếu request nhận 400 do JSON malformed, dùng file `payload.json` và `--data-binary "@payload.json"`, hoặc dùng `Invoke-RestMethod` với `ConvertTo-Json`. Không nhầm lỗi quote của shell với lỗi `If-Match`.

## 8. Kiểm thử Spring MVC bằng MockMvc

Thêm dependency test `spring-boot-starter-test` (scope test) rồi tạo `src/test/java/com/example/demo/ConditionalUpdateTest.java`.

### 8.1. Test tích hợp

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ConditionalUpdateTest {

    @Autowired
    MockMvc mvc;

    @Test
    void staleIfMatchMustNotOverwriteSuccessfulUpdate()
            throws Exception {

        String initial = mvc.perform(get("/api/docs/1"))
                .andExpect(status().isOk())
                .andExpect(header().string("ETag", "\"rev-1\""))
                .andReturn()
                .getResponse()
                .getHeader("ETag");

        mvc.perform(put("/api/docs/1")
                        .contentType("application/json")
                        .header("If-Match", initial)
                        .content("{\"content\":\"Alice edit\"}"))
                .andExpect(status().isOk())
                .andExpect(header().string("ETag", "\"rev-2\""))
                .andExpect(jsonPath("$.revision").value(2));

        mvc.perform(put("/api/docs/1")
                        .contentType("application/json")
                        .header("If-Match", initial)
                        .content("{\"content\":\"Bob stale edit\"}"))
                .andExpect(status().isPreconditionFailed());

        mvc.perform(get("/api/docs/1"))
                .andExpect(status().isOk())
                .andExpect(header().string("ETag", "\"rev-2\""))
                .andExpect(jsonPath("$.content").value("Alice edit"));
    }
}
```

Mỗi lần chạy test trong **một context mới** như trên, store khởi tạo `revision=1`. Nếu test suite tái sử dụng application context và có thêm test sửa shared `DocumentStore`, các tests phụ thuộc revision cứng có thể chạy không ổn định. Tốt hơn là tạo store mới/clear state qua fixture/test-specific configuration, hoặc đọc tag hiện hành rồi assert tăng revision tương đối. Test trên minh họa một phương pháp dễ đọc và cần chạy cô lập khỏi các tests thay state khác.

### 8.2. Thêm test cho missing/weak/wildcard

Các case cần assert:
- PUT thiếu header => 428.
- PUT với weak ETag => 412.
- PUT với list có strong current tag => thành công.
- PUT với `*` vào resource đang tồn tại => thành công nhưng **không chống lost update**.
- PUT vào ID không tồn tại => 404 theo contract.
- PUT dữ liệu sai validation => 400, không tăng revision.
- Hai PUT đồng thời với cùng revision => **chỉ một thắng** và request còn lại 412 trong demo synchronized.

### 8.3. Kiểm thử concurrency bằng service không phụ thuộc HTTP

Đây là class test riêng minh họa hai thread dùng cùng ETag:

```java
package com.example.demo;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DocumentStoreConcurrencyTest {

    @Test
    void onlyOneUpdateForSameVersionWins() throws Exception {
        DocumentStore store = new DocumentStore();
        String initial = store.get("1").strongETag();

        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger success = new AtomicInteger();
        AtomicInteger failed = new AtomicInteger();

        Runnable action = () -> {
            try {
                start.await();
                store.replace(
                        "1", List.of(initial),
                        new ReplaceDocument(Thread.currentThread().getName()));
                success.incrementAndGet();
            } catch (ResponseStatusException ex) {
                failed.incrementAndGet();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(action, "Alice");
        Thread b = new Thread(action, "Bob");
        a.start();
        b.start();
        start.countDown();
        a.join();
        b.join();

        assertEquals(1, success.get());
        assertEquals(1, failed.get());
        assertEquals(2, store.get("1").revision());
    }
}
```

Test này chứng minh compare-and-update nguyên tử trong **một DocumentStore/JVM**. Nó không chứng minh an toàn khi có nhiều application replicas, database transactions hoặc distributed caches.

## 9. Những lỗi dễ mắc khi triển khai If-Match

### 9.1. Kiểm tra ETag ở controller rồi gọi repository.save

```java
// ANTI-PATTERN
Document d = repository.findById(id).orElseThrow();
if (d.etag().equals(ifMatch)) {
    d.setContent(newContent);
    repository.save(d);
}
```

Giữa `findById` và `save` có một cửa sổ race. Transaction thông thường không mặc định ngăn lost update nếu isolation/locking không tương thích với phép ghi; yêu cầu **version CAS** hoặc optimistic locking có hỗ trợ từ DB.

### 9.2. Dùng If-None-Match trên PUT để chống lost update

`If-None-Match` là điều kiện **không trùng**; nó không thay cho “chỉ ghi khi tôi đang có đúng revision”. Với update có hiện trạng cụ thể, `If-Match` là công cụ phù hợp hơn.

### 9.3. So tag bằng contains hoặc bỏ dấu nháy không nhất quán

```java
// ANTI-PATTERN: không xử lý cú pháp list/weak/wildcard.
if (header.contains(currentETag)) {
    update();
}
```

Ví dụ header `W/"rev-5"` chứa substring `"rev-5"` nhưng **không** strong-match. Phải parse theo HTTP syntax và so sánh đúng semantics; dùng `HttpHeaders#getIfMatch()`/framework utilities khi phù hợp.

### 9.4. Chấp nhận wildcard mà tưởng đã giải quyết lost update

`If-Match: *` chỉ bảo đảm tồn tại. Nếu API cho phép wildcard update, client không có revision vẫn có thể ghi đè. Thiết kế một policy yêu cầu concrete strong tag nếu nghiệp vụ cần optimistic concurrency bắt buộc.

### 9.5. Sử dụng timestamp có độ chính xác thấp

Last-Modified thường chỉ đến giây; cập nhật liên tiếp nhanh có thể cùng timestamp. Nếu đồng thời dùng ETag và Last-Modified, quy tắc ưu tiên đúng là If-Match trước If-Unmodified-Since, và If-None-Match trước If-Modified-Since. Tránh kết luận bản ghi không đổi chỉ vì timestamp làm tròn giống nhau.

### 9.6. Tag bị reset sau khi restart hoặc deploy

Nếu backend restart làm revision trở về 1 trong khi dữ liệu persistent đã khác, strong ETag `"rev-1"` có thể được tái sử dụng không phù hợp. Dùng database version bền vững/opaque token mới khi representation thay đổi; với nhiều nodes phải thống nhất tag generation. Ví dụ RAM ở mục 7 **không** đáp ứng yêu cầu production persistence.

### 9.7. Cập nhật một phần nhưng tăng version sai

Với `PATCH`, nếu chỉnh một field làm thay đổi representation, phải tăng revision. Nếu JPA bulk update bỏ qua optimistic versioning mặc định hoặc job nền thay dữ liệu mà không bump version, stale tag có thể vẫn được chấp nhận. Mọi writer phải tham gia chung chiến lược version.

### 9.8. Tiết lộ body phiên bản mới cho người không có quyền

Khi trả 412, server không bắt buộc gửi toàn bộ representation hiện tại. Chỉ cung cấp current version/body nếu caller có quyền đọc. Ẩn 404/403 cho resource nhạy cảm theo policy thay vì để ETag báo lộ tồn tại.

## 10. Database: atomic compare-and-swap và optimistic locking

Để triển khai trên nhiều instances, phải để **nguồn dữ liệu có tính nguyên tử chung** quyết định phép ghi.

### 10.1. SQL CAS trực tiếp

Giả sử bảng:

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    content TEXT NOT NULL,
    version BIGINT NOT NULL
);
```

Khi client đã được xác thực, server đã xác minh quyền và `If-Match: "rev-12"`, có thể dùng update điều kiện:

```sql
UPDATE documents
SET content = :new_content,
    version = version + 1
WHERE id = :id
  AND owner_id = :authenticated_owner_id
  AND version = :expected_version;
```

Kết quả:
- **1 row affected:** thao tác thắng CAS; version tăng.
- **0 rows affected:** không có row phù hợp, do stale version, không có tài nguyên hoặc không được phép. Phân loại 404/403/412 theo chính sách mà **không làm lộ quyền**.
- **Nhiều hơn 1 row affected:** không nên xảy ra nếu ID là primary key và điều kiện đúng; là dấu hiệu dữ liệu/schema có vấn đề.

Một câu UPDATE có điều kiện version được DB thực hiện nguyên tử theo semantics giao dịch của DB. Hai writers kỳ vọng cùng version 12 không cùng được phép cập nhật một record lên version 13. Nếu cần trả representation mới, đọc lại row hoặc dùng `RETURNING` nơi DB hỗ trợ; bảo đảm transaction/response hợp đồng nhất quán.

**Không lấy `expected_version` trực tiếp từ body `{"version":...}` rồi bỏ qua If-Match nếu API contract đã yêu cầu HTTP precondition.** Nếu API dùng một cơ chế version field thay thế, cần document hợp đồng đó rõ. Ở đây client gửi strong ETag, server parse/validate rồi xác định version expected.

### 10.2. Spring Data JPA @Version

JPA hỗ trợ optimistic locking:

```java
@Entity
class DocumentEntity {

    @Id
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false)
    private String content;

    // constructors/getters/setters...
}
```

Đây là snippet entity, thiếu imports/constructors và không phải file chạy độc lập. `@Version` giúp persistence provider phát hiện concurrent writes trên entity đang được quản lý. Nếu một transaction stale cố flush/commit, có thể phát sinh `OptimisticLockException` hoặc exception được Spring dịch thành `ObjectOptimisticLockingFailureException` / tương đương.

Những lưu ý:
- Dùng transaction boundary rõ, đừng trả **200 trước khi flush/commit thành công**.
- Nếu đã kiểm tra If-Match trong service trước khi sửa entity, vẫn phải xử lý **version conflict xảy ra sau check**.
- Bulk JPQL/SQL updates có thể bỏ qua cơ chế automatic version increment/check nếu không được viết đúng; cần kiểm soát mọi đường ghi.
- Nếu thao tác đổi nhiều bảng/aggregate, transaction và concurrency model phải bao quát các invariant nghiệp vụ.
- Exception optimistic lock phát sinh lúc flush/commit có thể cần được map thành 412 khi liên hệ với precondition HTTP, nhưng không map bừa mọi `DataAccessException` thành 412. Lỗi dữ liệu khác có thể là 409/500 tùy nguyên nhân.
- Một transaction đã rollback do optimistic conflict không nên tiếp tục dùng entity manager đó để gửi lại update trong cùng transaction.

### 10.3. Pessimistic locking có thay If-Match không?

Pessimistic lock (ví dụ SELECT FOR UPDATE) tuần tự hóa những writers theo cơ chế DB nhưng **không tự biết client đã đọc revision nào**. Nếu Bob đã nhìn revision 1, lock ở lúc lưu chỉ ngăn writes đồng thời, nhưng vẫn có thể cho Bob ghi đè revision 2 sau khi Alice commit.

Cần kiểm tra **client expected revision** trong critical section/transaction hoặc optimistic versioning, không chỉ lock.

### 10.4. Multi-resource updates và transactions

Nếu PUT phải đổi một tài liệu đồng thời cập nhật số dư/quota hoặc audit log, đơn lẻ CAS trên row tài liệu chưa đủ để bảo vệ toàn bộ invariant. Sử dụng database transaction, outbox pattern khi event publishing cần nhất quán, idempotency keys với retries nếu cần, và thiết kế xử lý conflict rõ.

ETag/If-Match chủ yếu bảo vệ **representation/version của target resource**; nó không tự cung cấp distributed transaction giữa nhiều dịch vụ.

## 11. Các preconditions trong HTTP và cache

### 11.1. GET với If-None-Match

Client đã cache representation `"rev-5"`:

```http
GET /api/docs/1
If-None-Match: "rev-5"
```

Nếu server còn xem representation tương đương theo quy tắc weak comparison của `If-None-Match`, có thể trả:

```http
HTTP/1.1 304 Not Modified
ETag: "rev-5"
```

Response 304 không mang response body theo semantics. Điều này tiết kiệm bandwidth cho cache revalidation nhưng **không phải lệnh PUT** và không kiểm soát ghi.

### 11.2. PUT với If-Match

```http
PUT /api/docs/1
If-Match: "rev-5"
```

Server cần current selected representation có strong tag khớp. Nếu version đã là 6, trả 412, không ghi. `If-Match` thường được dùng trên PUT/PATCH/DELETE; nó cũng có semantics trên các HTTP methods khác trong điều kiện RFC cho phép.

### 11.3. Cache-Control và quyền riêng tư

Một response có ETag **không đồng nghĩa** trình duyệt/proxy được phép cache mọi nội dung. Với resource theo người dùng/tenant, cấu hình:
- `Cache-Control: private` hoặc `no-store` tùy chính sách.
- `Vary` cho variants phụ thuộc request headers nếu HTTP caching được sử dụng.
- Authorization và cache key isolation để tránh chia nhầm representation giữa users.

Nếu dùng `no-store` như demo, client vẫn có thể chủ động ghi nhớ ETag trong trạng thái ứng dụng để làm optimistic concurrency, nhưng shared HTTP caches không được giữ response theo cơ chế thông thường.

### 11.4. Strong vs weak ETag với gzip và biến thể

Nếu cùng URL trả khác bytes tùy encoding, language, negotiated media type hoặc permission projection:
- Strong tags không được đánh đồng những representation data thực sự khác theo cách vi phạm RFC.
- Weak tags thường phù hợp cache equivalence nhưng không thể dùng để so khớp `If-Match`.
- Version để cập nhật domain entity và HTTP representation ETag có thể là hai khái niệm liên quan nhưng không hoàn toàn giống. Nếu bạn cần một revision token ổn định cho mọi client representation variants, cân nhắc API contract riêng hoặc strategy phát strong tags cho từng selected representation được kiểm soát, đồng thời map về một expected domain version nhất quán.

## 12. Bảo mật và vận hành

### 12.1. Authorization luôn đứng trước cập nhật

Không viết:

```java
// ANTI-PATTERN: tag đúng không chứng minh owner.
if (ifMatch.equals(doc.etag())) {
    save(doc);
}
```

Bắt buộc kiểm tra principal/tenant/ACL và capability trên target resource. ETag có thể đoán được (nhất là `rev-1`), nên tuyệt đối không dùng validator như secret hoặc bearer token.

### 12.2. CSRF không được giải quyết bởi If-Match

Nếu app dùng session cookie và API chấp nhận PUT/PATCH/DELETE từ browser, phải thiết kế CSRF protection cùng SameSite/session policy phù hợp. If-Match không chứng minh request do người dùng chủ động tạo; nó chỉ chứng minh client có một validator, và token có thể lộ hoặc đoán được.

### 12.3. DoS và header sizes

Một client có thể gửi If-Match list rất dài. Servlet container/reverse proxy cần giới hạn request header size, số lượng headers, overall request body size và rate limits. Không triển khai parser regex với backtracking cực đoan hoặc tự lưu hàng triệu ETags vào một cấu trúc chưa giới hạn.

### 12.4. CORS và conditional requests

Khi browser gọi API cross-origin, `If-Match` không phải một CORS-safelisted request header. Ứng dụng/gateway cần cho phép header khi API hợp lệ, ví dụ trong allowedHeaders, và làm cho response header `ETag` có thể được JavaScript đọc qua `Access-Control-Expose-Headers: ETag` nếu cần. Đây là **CORS policy**, không thay authentication hoặc CSRF.

### 12.5. Retry và idempotency

PUT về lý thuyết là **idempotent** về intended effect khi lặp cùng request trong bối cảnh phù hợp, nhưng khi có If-Match:
- Lần đầu PUT với `"rev-1"` thành công, đổi tag thành `"rev-2"`.
- Retry y hệt với `"rev-1"` có thể nhận `412` vì precondition giờ sai.
- Đây không phải bằng chứng PUT đã chạy hai lần; có thể request đầu đã thành công và client mất response.

RFC 9110 có ngoại lệ cho server trả thành công khi chứng minh state-changing request trước đó đã được áp dụng. Trong thiết kế API thực tế, có thể dùng request id/idempotency key và kết quả đã lưu để phân biệt retry sau timeout với một stale edit khác. Không tự “fix” 412 bằng cách bỏ check ETag.

### 12.6. Monitoring

Nên ghi log:
- request method/path template/resource id (đã lọc dữ liệu nhạy cảm);
- principal/tenant identifier được kiểm soát;
- expected revision/token dạng safe metadata;
- current revision, status 412/428, concurrency conflict rate;
- thời gian DB transaction/CAS và số rows affected.

Không log raw Authorization, cookies, nội dung tài liệu nhạy cảm hoặc toàn body theo mặc định. Metric 412 tăng bất thường có thể chỉ ra UX quá nhiều xung đột hoặc retry sai.

## 13. Troubleshooting: lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Sửa |
| --- | --- | --- |
| Bob ghi đè Alice dù có If-Match | Check và write không atomic | DB version CAS / @Version với transaction |
| Tất cả PUT đều trả 412 | ETag client thiếu dấu quote hoặc representation tag khác | GET/inspect ETag thực, dùng exact strong tag |
| Weak tag `W/"x"` không match `"x"` | Đúng semantics If-Match mạnh | Dùng strong ETag cho concurrency |
| PUT thiếu If-Match vẫn thành công | API không yêu cầu precondition | Enforce 428 hoặc contract tương ứng |
| `If-Match: *` vẫn ghi đè | Wildcard chỉ yêu cầu tồn tại | Require concrete strong ETag nếu muốn lost-update prevention |
| Client hiểu 412 là dữ liệu hỏng | Stale version bình thường | GET latest, hiển thị diff/conflict/merge workflow |
| 304 xuất hiện khi GET | Conditional cache revalidation | Phân biệt GET If-None-Match với PUT If-Match |
| 428 bị cache | Cache/proxy config vi phạm yêu cầu | `Cache-Control: no-store` cho response 428 |
| Conflict khi triển khai nhiều pods | Lock chỉ nằm trong JVM | Đưa CAS/optimistic lock vào shared DB |
| JPA optimistic conflict thành 500 | Chưa map exception phù hợp | Map đúng concurrency conflict trong transaction boundary |
| Bản ghi thay đổi mà ETag không đổi | Writer khác không bump version | Quy định mọi writer update revision |
| ETag đổi khi JSON format không đổi | Algorithm gắn timestamp vô nghĩa hoặc biến thể | Chọn validator theo representation semantics |
| Cross-origin client không đọc ETag | Chưa expose header trong CORS | Expose `ETag` trên response theo allowed origin |
| Version token bị suy ra thành quyền | Thiếu authorization | Check ACL trên mỗi request |
| Client auto retry sau 412 gây mất dữ liệu | Gửi lại body cũ với tag mới không review | Cho user merge/xác nhận |
| HTTP 412 và 409 dùng tùy hứng | Không phân loại precondition/domain | Dùng 412 cho failed precondition, 409 cho domain conflict |

### 13.1. Checklist khi debug

1. GET hiện tại trả ETag mạnh nào, với đúng auth user và representation variant?
2. PUT/PATCH/DELETE gửi **header thật** nào? Đã giữ dấu `"` chưa?
3. Header có weak `W/`, nhiều tags hoặc `*` không?
4. Thiếu header có được 428 như contract không?
5. Bước so sánh ETag có diễn ra nguyên tử cùng DB write không?
6. Có background job, bulk update, import script hay node khác thay dữ liệu mà không tăng version?
7. Transaction rollback/flush exceptions có được phân biệt với 412 hợp lệ?
8. Sau conflict, client có GET lại và hiển thị thay đổi mới không?
9. CORS có cho phép `If-Match` và expose `ETag` không?
10. Có test request đồng thời, stale token, wildcard, 404, 401/403, timeout/retry và multi-instance chưa?

## 14. Tự kiểm tra kiến thức

**Câu 1.** Hai người cùng GET revision 3. Alice PUT với `If-Match: "rev-3"` thành công và tạo revision 4. Bob PUT với `"rev-3"` nên nhận gì?

**Đáp án:** `412 Precondition Failed` và không được ghi đè.

**Câu 2.** PUT không có If-Match trong API đã quy định bắt buộc có precondition nên trả gì?

**Đáp án:** `428 Precondition Required` là status chuyên biệt, response hướng dẫn client GET để lấy ETag.

**Câu 3.** `If-Match: W/"rev-3"` có khớp `ETag: "rev-3"` không?

**Đáp án:** Không. If-Match dùng **strong comparison**, weak tag không thể match mạnh.

**Câu 4.** `If-Match: *` có ngăn lost update không?

**Đáp án:** Không. Nó chỉ yêu cầu target resource tồn tại; không mang revision cụ thể.

**Câu 5.** Dùng `@Synchronized` hoặc `synchronized` trên controller/service JVM đã đủ cho nhiều replica không?

**Đáp án:** Không. Lock JVM chỉ bảo vệ một instance; nhiều replicas cần shared database atomic CAS/optimistic locking.

**Câu 6.** GET có `If-None-Match` trùng tag thường trả status gì?

**Đáp án:** `304 Not Modified` cho conditional GET/HEAD phù hợp, không phải 412 của PUT stale.

**Câu 7.** Một JPA entity có `@Version`, nhưng bulk SQL job update content mà không bump version. Có nguy cơ gì?

**Đáp án:** Old ETag vẫn có thể được chấp nhận dù representation đã thay đổi; mọi writer phải tuân cùng version contract.

**Câu 8.** API auth hợp lệ nhưng user không có quyền sửa document; user đưa ETag đúng. Có cho update không?

**Đáp án:** Không. If-Match là validator, **không** là giấy phép; authorization là điều kiện riêng.

**Câu 9.** Client có nên tự động GET tag mới và retry body cũ sau 412?

**Đáp án:** Không mặc định. Làm vậy có thể xóa thay đổi của người khác; cần UX so sánh, merge hoặc xác nhận.

## 15. Tài liệu chính thức

- [RFC 9110 — HTTP Semantics, §13.1.1 If-Match](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1): If-Match, strong comparison, wildcard và xử lý failed precondition.
- [RFC 9110 — §13.2 Evaluating Preconditions](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.2): thứ tự If-Match, If-Unmodified-Since, If-None-Match, If-Modified-Since.
- [RFC 9110 — §8.8.3 Entity Tags](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.8.3): ETag, strong/weak validator, representation semantics.
- [RFC 6585 — §3 428 Precondition Required](https://www.rfc-editor.org/rfc/rfc6585.html#section-3): yêu cầu conditional request để ngăn lost update.
- [Spring Framework 6.2 — HttpHeaders Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/http/HttpHeaders.html): `getIfMatch()`, `setIfMatch()` và ETag header methods.
- [Spring Framework 6.2 — ServletWebRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/web/context/request/ServletWebRequest.html): `checkNotModified()` cho conditional GET và state-changing requests.
- [Spring Framework — HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): HTTP caching và validators trong Spring MVC.
- [Spring Framework — ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html): response status, headers và body.
- [Jakarta Persistence — Version](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/version): optimistic versioning trong entity persistence.
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): xác thực, ủy quyền và HTTP API safety.

**Kết luận:** một client an toàn **GET → giữ strong ETag → PUT/PATCH/DELETE với If-Match**. Server yêu cầu điều kiện khi cần (428), từ chối validator không còn phù hợp (412), và **atomic compare-and-update** cùng tăng version dưới transaction/lock phù hợp; thiếu tính nguyên tử thì vẫn có lost update. Nếu muốn bảo vệ mọi chỉnh sửa, đừng coi `If-Match: *` là version check. ETag không thay ACL, validation, CSRF, cache policy, hay kế hoạch xử lý conflict ở giao diện người dùng.
