# ETag, Last-Modified và yêu cầu có điều kiện trong Spring MVC

## 1. Mục tiêu bài học

Khi một client tải cùng tài nguyên nhiều lần, không nhất thiết phải nhận lại toàn bộ JSON/HTML/file mỗi lần. HTTP cho phép client giữ bản biểu diễn (representation) đã nhận rồi hỏi server: **“Nội dung này đã thay đổi chưa?”**. Nếu chưa thay đổi, server có thể trả **304 Not Modified** không kèm response body. Với các thao tác cập nhật, HTTP còn cho phép client nói: **“Chỉ ghi nếu tài nguyên vẫn đúng phiên bản tôi đã đọc”**, từ đó tránh nhiều tình huống *lost update*.

Spring MVC (Servlet stack) hỗ trợ cơ chế này qua `ResponseEntity.eTag(...)`, `lastModified(...)`, `WebRequest.checkNotModified(...)` và các thành phần HTTP caching khác. Bài dùng **Java 17+, Spring Framework 6.x/Spring Boot 3.x**; không coi những ví dụ Servlet MVC này là hướng dẫn cho Spring WebFlux.

Sau bài, bạn có thể:

- Giải thích `ETag` và `Last-Modified` là **response validators**, không phải thay thế cho `Cache-Control`.
- Dùng `If-None-Match` và `If-Modified-Since` cho conditional GET/HEAD, hiểu tại sao 304 không mang body.
- Dùng `If-Match` và `If-Unmodified-Since` cho optimistic concurrency; phân biệt `412 Precondition Failed` với `409 Conflict` và `428 Precondition Required`.
- Hiểu strong vs weak ETag, cách so sánh theo HTTP Semantics (RFC 9110), precedence giữa các điều kiện và độ chính xác timestamp.
- Thêm validator vào controller qua `ResponseEntity`; biết giới hạn của `ShallowEtagHeaderFilter`, proxy/cache và variant `Vary`.
- Thực hành controller và in-memory atomic update có thể chạy trong Spring Boot 3; kiểm thử bằng `curl`, MockMvc, xem kỳ vọng status/headers.
- Tránh lỗi caching dữ liệu riêng tư, ETag không nhất quán với representation và kiểm tra phiên bản không atomic.

**Quan trọng:** `ETag`/`Last-Modified` chỉ mô tả trạng thái tài nguyên hoặc representation tại thời điểm xác định. Chúng không tự cấp quyền truy cập, không bảo đảm cache an toàn với dữ liệu người dùng và không giúp tránh race nếu logic cập nhật backend không atomic.

## 2. Khi nào dùng HTTP conditional requests?

Giả sử GET một tài liệu:

```http
GET /api/documents/1 HTTP/1.1
Host: localhost:8080
Accept: application/json
```

Response đầu tiên:

```http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "doc-1"
Last-Modified: Thu, 01 Oct 2026 10:00:00 GMT
Cache-Control: no-cache

{"id":1,"text":"Xin chào","version":1}
```

Client giữ body cùng validator và gửi lại:

```http
GET /api/documents/1 HTTP/1.1
If-None-Match: "doc-1"
```

Nếu representation vẫn là phiên bản đó:

```http
HTTP/1.1 304 Not Modified
ETag: "doc-1"
Cache-Control: no-cache

[no response body]
```

Phần body mẫu `[no response body]` là **chú thích**, không phải bytes được gửi. Response 304 **không có message body**; client/cache dùng lại response body đã lưu của lần 200 trước. Nếu validator không khớp, server trả 200 với representation hiện tại và validator mới.

Tương tự, trước khi sửa tài liệu, client có thể gửi `If-Match: "doc-1"`. Nếu user khác đã đổi phiên bản thành `"doc-2"`, request sửa cũ phải bị từ chối bằng **412** (trừ các trường hợp đặc biệt theo RFC) thay vì lặng lẽ ghi đè.

Hai mục tiêu rất khác nhau:

| Mục tiêu | Header request | Status nếu điều kiện không cho phép xử lý |
| --- | --- | --- |
| Tái xác thực cache GET/HEAD | `If-None-Match`, `If-Modified-Since` | **304 Not Modified** khi bản client đang có vẫn còn hợp lệ |
| Ngăn ghi đè bản mới | `If-Match`, `If-Unmodified-Since` | **412 Precondition Failed** khi precondition không đúng |
| Chỉ tạo nếu chưa có resource | `If-None-Match: *` ở unsafe method khi áp dụng | **412** nếu tài nguyên đã tồn tại |
| Yêu cầu client luôn gửi điều kiện cho một endpoint write | Chính sách ứng dụng, ví dụ buộc `If-Match` | **428 Precondition Required** nếu thiếu |

`304` không có nghĩa lỗi; `412` là xung đột với precondition HTTP cụ thể; `428` là chính sách server muốn request có điều kiện.

## 3. Phân biệt Cache-Control và response validators

Hai nhóm header giải quyết câu hỏi khác nhau:

| Header | Trả lời | Ví dụ |
| --- | --- | --- |
| `Cache-Control` | Có được lưu/reuse? Khi nào phải revalidate? | `no-cache`, `private`, `max-age=60` |
| `ETag` | Phiên bản/identity của representation được chọn | `"doc-1"` |
| `Last-Modified` | Thời điểm server cho rằng representation thay đổi cuối cùng | HTTP-date |
| `Vary` | Những request headers ảnh hưởng đến representation được chọn | `Accept`, `Accept-Language` |
| `Expires` | Mốc hết hạn absolute theo HTTP cache | HTTP-date |

**`Cache-Control: no-cache` không có nghĩa “cấm lưu”.** Theo semantics HTTP caching, cache có thể lưu response nhưng phải revalidate với origin trước khi dùng lại (tùy các điều kiện khác). Nếu dữ liệu không được phép lưu, dùng `no-store` phù hợp. Khi có thông tin theo từng user, cần xét `private`, `Authorization`/cookies, shared caches và policy bảo mật.

Trường hợp một bản JSON public có `Cache-Control: max-age=60`, cache có thể dùng response còn fresh mà không gửi conditional GET mỗi lần. Sau 60 giây, cache có thể revalidate bằng ETag/Last-Modified. **Tự gắn ETag không tự làm response cacheable**, và không đảm bảo giảm request đến server nếu client/cache không lưu response.

## 4. ETag: entity tag là gì?

`ETag` (entity tag) là validator cho một **selected representation** của HTTP resource. Dạng thường gặp:

```http
ETag: "v17"
ETag: "sha256-abc123"
ETag: W/"semantic-v17"
```

Dấu ngoặc kép là thành phần cú pháp quan trọng của ETag. Prefix `W/` đánh dấu **weak validator**. String bên trong gọi là opaque tag; client **không nên giải mã nội dung** hay đoán giá trị từ dữ liệu nghiệp vụ. Server có thể tạo từ revision, version token hoặc hash có cơ chế nhất quán.

### 4.1. Strong ETag và weak ETag

- **Strong validator** (ví dụ `"abc"`): dùng khi server bảo đảm representation được xem là giống nhau ở mức đủ chặt theo strong comparison. Với payload được truyền theo nhiều biến thể, logic tạo ETag phải phản ánh những khác biệt có ảnh hưởng byte-for-byte.
- **Weak validator** (ví dụ `W/"abc"`): dùng khi server muốn coi những representation khác byte nhưng tương đương về ý nghĩa là một phiên bản cho cache validation.
- Strong ETag thường phù hợp với `If-Match` để ngăn ghi đè, còn weak ETag có thể dùng `If-None-Match` khi revalidate.
- Không tự thêm `W/` chỉ vì “nhẹ hơn”; phải hiểu tính chính xác/ý nghĩa của validator và lựa chọn theo contract.

Ví dụ:

| Giá trị | `If-None-Match` dùng weak comparison | `If-Match` dùng strong comparison |
| --- | --- | --- |
| Current ETag `"v1"` so với client `"v1"` | Match | Match |
| Current `"v1"` so với client `W/"v1"` | Match | **Không** match |
| Current `W/"v1"` so với client `W/"v1"` | Match | **Không** match |
| Current `"v2"` so với client `"v1"` | Không match | Không match |

Theo RFC 9110, `If-Match` dùng **strong comparison**, còn `If-None-Match` dùng **weak comparison**. Một weak ETag không được xem là tương đương strong tag trong điều kiện ghi chống lost update.

### 4.2. ETag từ database revision có luôn mạnh không?

Không nhất thiết. Nếu response JSON có thêm field, đổi thứ tự serializer, đổi ngôn ngữ, đổi compression/variant hoặc dữ liệu ngoài record mà revision không tăng, ETag chỉ từ `@Version` của JPA có thể **không còn đại diện chính xác** cho bytes của representation. Muốn dùng strong ETag, phải định nghĩa version liên hệ chắc chắn với **mọi thay đổi có ý nghĩa đối với selected representation**, hoặc tạo hash từ representation bytes canonical/phù hợp.

Trong ví dụ bên dưới, API cố định **một JSON representation** từ `id`, `text`, `version`, và tất cả thay đổi text đều tăng revision. Đây là mô hình học tập có thể dùng strong tag dạng `"doc-{version}"`. Trong production, thay serializer/media type/response schema mà không đổi revision cần đánh giá lại cách tạo validator; không đơn giản dùng cùng strong ETag cho JSON và XML.

### 4.3. ETag không phải secret

Đừng nhúng mật khẩu, token, PII, hash có thể bị dùng để dò dữ liệu nhạy cảm, hoặc key nội bộ bí mật vào ETag. ETag cũng có thể gây tracking nếu thiết kế gắn identifier riêng cho từng người trên nhiều tài nguyên/website; tránh dùng validator như cookie thay thế.

## 5. Last-Modified: thời điểm thay đổi

`Last-Modified` cho client biết thời điểm server tin rằng selected representation được chỉnh sửa gần nhất, theo định dạng **HTTP-date**, thường:

```http
Last-Modified: Thu, 01 Oct 2026 10:00:00 GMT
```

Không gửi Java `Instant.toString()` trực tiếp thành HTTP Last-Modified. Spring MVC `ResponseEntity.lastModified(...)` định dạng header theo HTTP. Ví dụ HTTP-date được viết GMT với độ chính xác **giây**.

### 5.1. Ưu điểm

- Dễ dùng khi hệ thống đã có `updatedAt` cho một resource.
- Client có thể gửi `If-Modified-Since` để hỏi resource có thay đổi sau mốc thời gian đó không.
- Có thể bổ trợ ETag cho clients/caches hỗ trợ date validators.

### 5.2. Giới hạn

- **Độ chính xác giây**: hai lần sửa trong cùng một giây có thể chia sẻ cùng `Last-Modified`, khiến client chỉ gửi date validator có nguy cơ nhận 304 không mong muốn.
- Đồng hồ/replica/server có thể lệch nhau; timestamps do client khai báo không đáng tin.
- Một file tạo lại từ source với metadata mới có thể có timestamp thay đổi nhưng nội dung giữ nguyên; revalidation kém hiệu quả.
- Field `updatedAt` chỉ phản ánh database row không đủ nếu JSON kết hợp nhiều bảng/cache/translation.
- `If-Unmodified-Since` không phải công cụ optimistic locking tốt bằng **strong If-Match** nếu có nhiều writes nhanh.

Nếu resource thay đổi nhiều lần/giây, ưu tiên ETag chính xác và bảo đảm freshness. Tốt nhất có nguồn server-authoritative modification time, không dựa vào ngày máy client hay định dạng locale.

## 6. Conditional GET với If-None-Match

`If-None-Match` kiểm tra xem selected representation có ETag trùng một trong những tag client nêu không.

```http
If-None-Match: "v1"
If-None-Match: W/"v1"
If-None-Match: "v1", "v2", "v3"
If-None-Match: *
```

Với **GET/HEAD**, nếu điều kiện `If-None-Match` được đánh giá **false** vì selected representation đã trùng tag client có, server thường trả **304**, không có body. Nếu tag khác, tiếp tục GET bình thường, thường **200** với body mới.

`If-None-Match: *` nghĩa là điều kiện chỉ đúng khi **không có representation hiện tại**; với GET của resource đang tồn tại, điều kiện false và có thể trả 304. Với các unsafe methods (POST/PUT), cùng `If-None-Match: *` thường được dùng cho “chỉ tạo nếu chưa tồn tại”; nếu resource đã tồn tại thì **412**.

Nếu một cache/client chứa stale body nhưng gửi tag `"old"` và server đang là `"new"`, server **phải cung cấp bản hiện tại** khi các điều kiện khác cho phép, không trả 304 chỉ vì request có header If-None-Match.

## 7. Conditional GET với If-Modified-Since

Client có thể gửi:

```http
If-Modified-Since: Thu, 01 Oct 2026 10:00:00 GMT
```

Đối với GET/HEAD, nếu selected representation **không thay đổi sau thời điểm đó**, server thường trả 304. Nếu đã thay đổi, 200 có body mới.

Điều kiện dùng HTTP-date hợp lệ. RFC 9110 yêu cầu bỏ qua `If-Modified-Since` nếu:

- Request chứa `If-None-Match` (ETag là validator chính xác hơn).
- Header date không hợp lệ hoặc có nhiều giá trị không hợp lệ theo ngữ pháp.
- Method không phải GET/HEAD.

Trong HTTP, server không nên dùng thời gian tương lai của client như một cách mù quáng để trả 304 nếu metadata resource không đáng tin. Spring hỗ trợ xử lý ngày ở controller nhưng bạn vẫn phải có modification time đúng.

### Nếu có cả hai điều kiện

```http
If-None-Match: "stale-tag"
If-Modified-Since: Thu, 01 Oct 2026 10:00:00 GMT
```

**If-None-Match có ưu tiên so với If-Modified-Since**: nếu current ETag khác `"stale-tag"`, request vẫn có thể nhận 200 **ngay cả khi** timestamp chưa vượt date trong header. Không được viết logic `if (etagMatched || notModifiedSince) return 304`, bởi đó có thể trái quy tắc precedence.

## 8. If-Match và If-Unmodified-Since: chống mất cập nhật

Kịch bản:

```text
T0: Document version 7
A: GET /documents/1 -> ETag "doc-7"
B: GET /documents/1 -> ETag "doc-7"
B: PUT If-Match: "doc-7" -> thành công, version 8
A: PUT If-Match: "doc-7" -> 412 Precondition Failed
A: GET lại version 8 -> quyết định merge, rồi PUT "doc-8"
```

**`If-Match`** yêu cầu server chỉ thực hiện method khi selected representation **đang match strong tag** của client. Có thể gửi danh sách tag hoặc `*` (resource hiện tồn tại), nhưng một API có quyền đặt thêm policy yêu cầu chính xác revision để tránh overwrite. `If-Match: W/"doc-7"` không hợp lệ cho strong match và sẽ không cho phép ghi dựa trên weak tag.

**`If-Unmodified-Since`** dùng date precondition: chỉ xử lý nếu resource không được thay đổi sau thời điểm client chỉ định. Nó yếu hơn trong các ứng dụng cập nhật nhiều lần/giây, và phải được bỏ qua khi đã có `If-Match`.

### Vì sao không chỉ check trong controller rồi save?

Mô hình không đủ an toàn:

```java
Document before = repository.findById(id).orElseThrow();
if (before.version() == clientVersion) {
    repository.save(update(before)); // race giữa check và save!
}
```

Đây là **snippet phản ví dụ**, không phải code compile độc lập. Hai requests có thể cùng vượt kiểm tra trước khi một trong hai save. Cần CAS, conditional UPDATE SQL (`UPDATE ... WHERE id=? AND version=?`) hoặc optimistic locking thực sự (`@Version` JPA) trong transaction, xử lý row-count/optimistic-lock conflict thành 412 theo HTTP precondition contract.

Nếu policy yêu cầu `If-Match` mà client không gửi, server có thể trả **428 Precondition Required** (RFC 6585). Nếu gửi ETag cũ, trả **412 Precondition Failed**. Nếu user gửi dữ liệu mâu thuẫn nghiệp vụ không liên quan HTTP precondition, **409 Conflict** hoặc lỗi business khác có thể thích hợp.

## 9. Thứ tự ưu tiên các request preconditions theo RFC 9110

Khi có nhiều conditional headers, thứ tự đánh giá không tùy ý. Tóm tắt cho origin server:

1. **`If-Match`**: kiểm tra trước; nếu false, thông thường 412. Dùng strong comparison.
2. Nếu **không có If-Match** mới xét **`If-Unmodified-Since`**; nếu false, thông thường 412.
3. **`If-None-Match`**: nếu false, GET/HEAD → 304; method khác → 412.
4. Với GET/HEAD, chỉ khi **không có If-None-Match** mới xét **`If-Modified-Since`**; nếu false → 304.
5. Khi có `Range`/`If-Range` và điều kiện trước cho phép, có thể xét đáp ứng partial content (206); ngoài phạm vi demo.
6. Nếu không có điều kiện ngăn, xử lý method bình thường.

Đây là mô tả rút gọn; RFC có ngoại lệ như request thay đổi trạng thái đã thành công trước đó và quy định không nhất thiết evaluate preconditions nếu request không thể thành công ngoài điều kiện. Ví dụ authentication/authorization thường phải được giải quyết trước khi xác nhận sự tồn tại hay version của tài nguyên cho người không có quyền.

### Bảng hành vi

| Method | Conditional header | Khi match / thời điểm chưa đổi | Khi khác / đã đổi |
| --- | --- | --- | --- |
| GET | `If-None-Match: "v1"` | 304 | 200 (bản mới) |
| HEAD | `If-None-Match: "v1"` | 304 | HEAD 200 không body |
| GET | `If-Modified-Since` | 304 nếu chưa đổi sau mốc | 200 |
| PUT | `If-Match: "v1"` | Chỉ ghi nếu phiên bản hiện tại đúng | 412 nếu ETag hiện tại khác |
| DELETE | `If-Match: "v1"` | Xóa nếu precondition đúng và có quyền | 412 nếu không khớp |
| PUT create-only | `If-None-Match: *` | 412 nếu resource đang có | Có thể tạo khi chưa có |
| PUT | `If-Unmodified-Since` | Chỉ ghi nếu không đổi sau mốc | 412 nếu đã đổi |

Trong bảng, cột “match” của If-None-Match mang nghĩa **ETag trùng**, khiến precondition “none match” thất bại; không nhầm logic boolean và status.

## 10. Spring MVC hỗ trợ ở đâu?

Spring Framework có các cơ chế:

- `ResponseEntity.ok().eTag(...).lastModified(...).cacheControl(...).body(dto)`: khai báo validators và cache directives trên response. Spring MVC xử lý conditional GET/HEAD tương ứng để có thể trả 304 khi tag/date khớp, không cần bạn tự xây 304 trong trường hợp thông thường.
- `WebRequest.checkNotModified(...)`: controller có thể chủ động kiểm tra validator trước khi tạo body nặng; khi phù hợp có thể kết thúc sớm.
- `ShallowEtagHeaderFilter`: tính ETag dựa trên response content đã được render; giảm băng thông nhưng **không tránh công việc tạo body**.
- Static resource handling: Spring MVC hỗ trợ caching/conditional requests riêng cho tài nguyên tĩnh và `Resource`, cần cấu hình đúng.
- `CacheControl`: xây `Cache-Control` header trong ResponseEntity.
- `ServletWebRequest`/`HttpServletResponse`: các lựa chọn thấp hơn khi cần kiểm soát tinh vi.

Tham khảo chính thức: Spring Framework — HTTP Caching: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html

### 10.1. ResponseEntity example ngắn

```java
@GetMapping("/books/{id}")
public ResponseEntity<BookResponse> get(@PathVariable long id) {
    BookResponse book = service.find(id);
    return ResponseEntity.ok()
        .eTag("\"book-" + book.version() + "\"")
        .lastModified(book.updatedAt().toEpochMilli())
        .cacheControl(CacheControl.noCache())
        .body(book);
}
```

**Đây là snippet trong controller** với `service`, record `BookResponse` và imports đã tồn tại, không phải ứng dụng compile độc lập. Đảm bảo metadata ETag/updatedAt thống nhất với body được trả. Spring MVC có thể xử lý `If-None-Match`, `If-Modified-Since` trên `ResponseEntity` này.

### 10.2. checkNotModified trước khi render view tốn chi phí

```java
@GetMapping("/reports/{id}")
public String report(
        @PathVariable long id, WebRequest request, Model model) {

    String etag = reportService.currentEtag(id);

    if (request.checkNotModified(etag)) {
        return null; // MVC đã chuẩn bị 304 / điều kiện response.
    }

    model.addAttribute("report", reportService.render(id));
    return "report";
}
```

Đây cũng là **snippet** yêu cầu các bean/imports phù hợp. Có thể tránh tạo report đắt khi precondition cho phép trả 304, **nếu** metadata đủ tin cậy để quyết định từ trước. Bắt buộc kiểm tra authentication/authorization trước khi dùng validator để tránh để lộ sự tồn tại/trạng thái tài nguyên cho người không có quyền.

### 10.3. ShallowEtagHeaderFilter không phải deep validator

Một shallow ETag filter thường phải render response (và buffer/capture content) rồi mới tính checksum. Nó có thể tiết kiệm **băng thông ở response 304**, nhưng không tiết kiệm công việc controller, DB và serializer ở lượt kiểm tra. Với response lớn hoặc streaming, buffering có thể tốn RAM/latency và không phù hợp.

Nếu biết revision/update timestamp từ metadata nhanh, **deep ETag** trong controller/service thường tốt hơn. Nếu dùng `ShallowEtagHeaderFilter`, đọc tài liệu về conditional handling, async dispatch, response wrapping và trường hợp không áp dụng; không bật mặc định cho mọi streaming/file endpoint.

## 11. Ví dụ runnable: tài liệu với GET conditional và PUT If-Match

Ứng dụng mẫu dùng **Spring Boot 3.x + Java 17**, Maven:

- `spring-boot-starter-web`: Spring MVC/Jackson.
- `spring-boot-starter-validation`: validation cho body PUT.
- `spring-boot-starter-test` (test scope): JUnit/MockMvc.

Không cần database. Một document được lưu trong `AtomicReference`. Cả kiểm tra precondition và commit update được kết hợp qua `compareAndSet`, minh họa tránh race trong **một JVM duy nhất**. Production nhiều instance bắt buộc dùng DB transaction/conditional update hoặc distributed state có cơ chế tương đương.

Các file:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  DocumentController.java
src/test/java/com/example/demo/
  DocumentControllerTest.java
```

### 11.1. DemoApplication.java

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 11.2. DocumentController.java

```java
package com.example.demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final AtomicReference<State> state =
            new AtomicReference<>(new State(
                1L, "Xin chào", 1L,
                Instant.parse("2026-10-01T10:00:00Z")));

    @GetMapping(path = "/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<DocumentResponse> find(
            @PathVariable long id) {

        State current = state.get();
        if (id != current.id()) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noCache())
                .eTag(etag(current))
                .lastModified(current.updatedAt().toEpochMilli())
                .body(new DocumentResponse(
                    current.id(), current.text(), current.version()));
    }

    @PutMapping(path = "/{id}",
                consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Void> replace(
            @PathVariable long id,
            @RequestHeader(value = HttpHeaders.IF_MATCH,
                           required = false) String ifMatch,
            @Valid @RequestBody UpdateRequest input) {

        if (id != 1L) {
            return ResponseEntity.notFound().build();
        }

        if (ifMatch == null || ifMatch.isBlank()) {
            // Chính sách API: từ chối PUT thiếu precondition.
            return ResponseEntity.status(
                    HttpStatus.PRECONDITION_REQUIRED).build();
        }

        // CAS gắn kiểm tra phiên bản với cập nhật.
        for (;;) {
            State before = state.get();

            if (!strongIfMatch(ifMatch, etag(before))) {
                return ResponseEntity.status(
                        HttpStatus.PRECONDITION_FAILED).build();
            }

            State after = new State(
                    before.id(),
                    input.text(),
                    before.version() + 1,
                    Instant.now().truncatedTo(ChronoUnit.SECONDS));

            if (state.compareAndSet(before, after)) {
                // Không trả body với 204.
                return ResponseEntity.noContent().build();
            }
            // Có PUT đồng thời thắng CAS; đọc lại version rồi check.
        }
    }

    private static String etag(State current) {
        return "\"doc-" + current.version() + "\"";
    }

    private static boolean strongIfMatch(
            String header, String currentEtag) {

        String value = header.trim();

        // If-Match: * khi tài nguyên tồn tại.
        // Không dùng * để ngăn ghi đè: nó chỉ yêu cầu tồn tại.
        if ("*".equals(value)) {
            return true;
        }

        // Ví dụ chỉ sinh tags dạng "doc-N", không chứa dấu phẩy;
        // parser split này KHÔNG thay RFC grammar parser tổng quát.
        return Arrays.stream(value.split(","))
                .map(String::trim)
                .anyMatch(candidate -> candidate.equals(currentEtag));
        // W/"doc-N" sẽ không match strong currentEtag.
    }

    private record State(
            long id, String text, long version, Instant updatedAt) {}

    public record DocumentResponse(
            long id, String text, long version) {}

    public record UpdateRequest(
            @NotBlank @Size(max = 2000) String text) {}
}
```

**Giới hạn parser trong demo:** `strongIfMatch` hỗ trợ tag server tạo `"doc-N"`, list các tag đó và `*`. Nó không phải parser ETag RFC đầy đủ cho mọi opaque-tag có dấu phẩy/escape; nếu API hỗ trợ tập client rộng, dùng parser đúng chuẩn hoặc thành phần framework chuyên trách. `W/"doc-N"` không strong-match, phù hợp semantics của If-Match.

**Giới hạn timestamp:** `updatedAt` cắt tới giây; hai lần PUT trong một giây có thể cùng `Last-Modified`. Ví dụ ưu tiên ETag revision và nhấn mạnh không dùng Last-Modified đơn độc để bảo vệ writes tốc độ cao. Nếu hệ thống cần IMS-only chính xác dưới concurrency, phải thiết kế mốc thời gian có tính chất phù hợp hoặc chọn ETag làm validator chính.

**Giới hạn cache/storage:** `AtomicReference` chỉ bảo vệ dữ liệu trong **một process**, mất dữ liệu khi restart và không đồng bộ giữa nhiều pods. Dùng database `@Version`/conditional update SQL trong ứng dụng thật, xử lý conflict thành 412. Đừng nhầm CAS trong Java với transaction phân tán.

**Giới hạn access control:** Demo chưa bật authentication/authorization. Production phải kiểm tra user có quyền đọc/sửa tài liệu trước khi xác nhận version/tồn tại. Có thể dùng `CacheControl.noCache().cachePrivate()` hoặc `noStore()` theo mức nhạy cảm. Đừng cache public dữ liệu cá nhân.

## 12. Chạy demo và kiểm chứng bằng curl

Chạy trong project Maven Boot 3 đã tạo:

```bash
./mvnw spring-boot:run
```

Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Ứng dụng nghe cổng 8080 nếu không đổi `server.port`. File Java dùng Spring dependencies; `javac DocumentController.java` độc lập sẽ không đủ classpath.

### 12.1. GET lần đầu: 200 + validators

```bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/documents/1
```

Khi app vừa khởi động (chưa có PUT), kết quả kỳ vọng:

```http
HTTP/1.1 200 OK
ETag: "doc-1"
Last-Modified: Thu, 01 Oct 2026 10:00:00 GMT
Cache-Control: no-cache
Content-Type: application/json

{"id":1,"text":"Xin chào","version":1}
```

Các header HTTP khác có thể được thêm bởi Boot/server; thứ tự JSON fields được Jackson quyết định. Date là mốc khởi tạo cố định trong demo, **không** phải thời gian request đang diễn ra.

### 12.2. Conditional GET theo ETag: 304

```bash
curl -i -H 'If-None-Match: "doc-1"' \
  http://localhost:8080/api/documents/1
```

Dự kiến **304 Not Modified**, response không có body. Nếu bạn đang dùng Windows PowerShell hoặc cmd, đặt quotes/escaping phù hợp shell; ví dụ PowerShell có thể dùng `curl.exe -i -H 'If-None-Match: "doc-1"' URL`.

Thử weak tag:

```bash
curl -i -H 'If-None-Match: W/"doc-1"' \
  http://localhost:8080/api/documents/1
```

Dự kiến **304**, vì `If-None-Match` dùng weak comparison. Nếu state đã tăng version, cả hai header cũ sẽ không còn khớp, GET trả **200** với version mới.

### 12.3. Conditional GET theo thời gian

```bash
curl -i \
  -H 'If-Modified-Since: Thu, 01 Oct 2026 10:00:00 GMT' \
  http://localhost:8080/api/documents/1
```

Khi chưa cập nhật, thường trả **304**. Sau khi PUT thành công vào thời điểm muộn hơn, request dùng date cũ trả **200** với JSON mới.

### 12.4. If-None-Match ưu tiên hơn If-Modified-Since

```bash
curl -i \
  -H 'If-None-Match: "not-current"' \
  -H 'If-Modified-Since: Thu, 01 Oct 2026 10:00:00 GMT' \
  http://localhost:8080/api/documents/1
```

Dự kiến **200**, vì ETag khác và date condition phải bị bỏ qua khi If-None-Match hiện diện. Đây là một test giúp phát hiện server tự viết điều kiện bằng logic OR sai.

### 12.5. PUT không có If-Match: 428

```bash
curl -i -X PUT \
  -H 'Content-Type: application/json' \
  --data '{"text":"Nội dung mới"}' \
  http://localhost:8080/api/documents/1
```

Demo trả **428 Precondition Required** do chính sách chỉ chấp nhận write có `If-Match`. Không phải mọi server bắt buộc áp policy này; 428 do API chủ động lựa chọn.

### 12.6. PUT đúng version: 204 rồi GET phiên bản mới

```bash
curl -i -X PUT \
  -H 'Content-Type: application/json' \
  -H 'If-Match: "doc-1"' \
  --data '{"text":"Nội dung mới"}' \
  http://localhost:8080/api/documents/1
```

Nếu chưa có PUT trước đó, trả **204 No Content**. Sau đó:

```bash
curl -i http://localhost:8080/api/documents/1
```

Dự kiến **200**, body:

```json
{"id":1,"text":"Nội dung mới","version":2}
```

Header ETag lúc đó `"doc-2"`. GET lại sau PUT để lấy validator mới; demo **không** đính kèm ETag mới vào response 204.

### 12.7. PUT với ETag cũ: 412

```bash
curl -i -X PUT \
  -H 'Content-Type: application/json' \
  -H 'If-Match: "doc-1"' \
  --data '{"text":"Nội dung stale"}' \
  http://localhost:8080/api/documents/1
```

Dự kiến **412 Precondition Failed**, không sửa document version 2. Nếu gửi `If-Match: W/"doc-2"`, demo cũng trả 412 bởi weak validator không strong-match. Nếu gửi `If-Match: *`, theo semantics chỉ kiểm tra existence, **không chống ghi đè thay đổi giữa GET/PUT**; người dùng cần hiểu sự khác nhau.

### 12.8. GET resource khác: 404

```bash
curl -i http://localhost:8080/api/documents/999
```

Dự kiến **404 Not Found**. Không trả `304` chỉ vì một cached ETag client gửi; validator của resource khác không áp dụng cho URI mới.

## 13. MockMvc: kiểm thử conditional GET và concurrent update

Tạo `src/test/java/com/example/demo/DocumentControllerTest.java` trong project có `spring-boot-starter-test`.

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentControllerTest {

    @Autowired
    MockMvc mvc;

    private String currentTag() throws Exception {
        MvcResult result = mvc.perform(get("/api/documents/1"))
            .andExpect(status().isOk())
            .andExpect(header().exists(HttpHeaders.ETAG))
            .andExpect(header().exists(HttpHeaders.LAST_MODIFIED))
            .andReturn();

        return result.getResponse().getHeader(HttpHeaders.ETAG);
    }

    @Test
    void matchingTagReturns304WithoutBody() throws Exception {
        String tag = currentTag();

        mvc.perform(get("/api/documents/1")
                .header(HttpHeaders.IF_NONE_MATCH, tag))
            .andExpect(status().isNotModified())
            .andExpect(content().string(""));
    }

    @Test
    void weakValidatorAlsoMatchesForGet() throws Exception {
        String tag = currentTag();

        mvc.perform(get("/api/documents/1")
                .header(HttpHeaders.IF_NONE_MATCH, "W/" + tag))
            .andExpect(status().isNotModified());
    }

    @Test
    void staleTagOverridesDateValidator() throws Exception {
        MvcResult initial = mvc.perform(get("/api/documents/1"))
            .andExpect(status().isOk()).andReturn();

        String lastModified = initial.getResponse()
                .getHeader(HttpHeaders.LAST_MODIFIED);

        mvc.perform(get("/api/documents/1")
                .header(HttpHeaders.IF_NONE_MATCH, "\"not-current\"")
                .header(HttpHeaders.IF_MODIFIED_SINCE, lastModified))
            .andExpect(status().isOk());
    }

    @Test
    void putRequiresVersionAndRejectsStaleWrites() throws Exception {
        String old = currentTag();

        mvc.perform(put("/api/documents/1")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"New content\"}"))
            .andExpect(status().isPreconditionRequired());

        mvc.perform(put("/api/documents/1")
                .header(HttpHeaders.IF_MATCH, old)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"New content\"}"))
            .andExpect(status().isNoContent());

        mvc.perform(put("/api/documents/1")
                .header(HttpHeaders.IF_MATCH, old)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"Stale overwrite\"}"))
            .andExpect(status().isPreconditionFailed());

        mvc.perform(get("/api/documents/1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.text").value("New content"));
    }
}
```

Bộ test dùng singleton controller có in-memory state chung, nhưng từng test lấy **ETag hiện tại** thay vì hardcode revision 1. Không chạy song song với test khác sửa cùng resource nếu muốn assertions deterministic; nếu dùng JUnit parallel execution, isolate state/repository theo test. `lastModified` test phụ thuộc mốc server; test precedence không dựa một timestamp có thể đổi trong cùng giây.

Chạy:

```bash
./mvnw test
```

PowerShell:

```powershell
.\mvnw.cmd test
```

Đây là **mã kiểm thử mẫu**, không phải tuyên bố đã chạy trên repository người dùng. Khi Spring Security được bật, test PUT có thể bị CSRF/authorization filter chặn 403 trước controller; bổ sung `spring-security-test`, `with(csrf())` và user có quyền theo policy, rồi kiểm thử 428/412.

### Bổ sung test hữu ích

- GET không có condition trả 200 và cả ETag/Last-Modified.
- GET với `If-Modified-Since` đúng date trả 304, và date cũ hơn trả 200.
- If-None-Match có nhiều tags, tag thứ hai khớp, vẫn 304.
- GET với ETag khác trả 200 và body mới.
- PUT `If-Match: W/"doc-N"` trả 412.
- PUT với format JSON sai hoặc thiếu text trả 400 trước logic write.
- PUT đồng thời cùng một ETag: **chỉ một request được phép ghi**, request còn lại 412 trong mô hình CAS.
- Test 304 không chứa body nhưng giữ validator/cache headers phù hợp.
- GET resource không tồn tại trả 404; không lộ version cho người không có quyền.
- Với HTTP server thật, kiểm tra proxy/cache có bỏ/biến đổi ETag, Vary hoặc Content-Encoding hay không.

## 14. Last-Modified trong Spring MVC và độ chính xác giây

Giá trị `Instant` của database có thể chứa milli/nano seconds, nhưng HTTP-date chỉ biểu diễn đến **giây**. Nếu bạn so sánh raw `Instant` với `If-Modified-Since` rồi trả 200 trong khi chưa có thay đổi thực, đó có thể chỉ do chênh lệch milli. Ngược lại, nếu update trong cùng giây, date-only validator có thể trả 304 sai với một tài nguyên đã đổi.

Vì vậy:

1. Định nghĩa authoritative `updatedAt` với semantics đúng cho **toàn representation**.
2. Khi phục vụ date validator, chuẩn hóa comparison theo HTTP-date precision, không so raw millis một cách tùy tiện.
3. Nếu cập nhật thường xuyên, ưu tiên ETag; client nên gửi `If-None-Match` khi có.
4. Không dùng Last-Modified của row A nếu JSON response còn phụ thuộc row B đã thay đổi.
5. Đừng lấy client-provided date làm source of truth để cập nhật metadata.
6. Với các server replicas, bảo đảm validators nhất quán trên cùng một resource version.
7. Không dùng date-only If-Unmodified-Since làm OCC khi updates dưới giây có thể xảy ra.

`Instant.now().truncatedTo(ChronoUnit.SECONDS)` trong demo giúp hiển thị HTTP-date gọn; **không làm date validator trở thành cơ chế optimistic locking mạnh**.

## 15. Vary, Content-Encoding và representation variants

Một resource có thể trả JSON và XML hoặc nhiều ngôn ngữ:

```http
GET /articles/7
Accept: application/json
Accept-Language: vi-VN
Accept-Encoding: gzip
```

Nếu representation thay đổi theo các headers này, cache phải phân biệt variant tương ứng. Header `Vary` cho cache biết những request headers nào tham gia lựa chọn representation:

```http
Vary: Accept, Accept-Language, Accept-Encoding
```

Đây là **ví dụ**, chỉ đưa những headers thật sự ảnh hưởng representation. Việc compression, content negotiation hay CDN có thể bổ sung `Vary` cũng tùy hạ tầng; không tự gắn bừa mọi header.

ETag cũng phải phù hợp **selected representation**. Strong ETag của JSON có bytes khác XML hoặc bản tiếng Việt có thể cần khác; nếu coi hai bản tương đương về nghĩa, cân nhắc weak validators với semantic rules thích hợp. Một hash từ JSON bytes không thể tái sử dụng nguyên xi như strong tag cho gzipped byte stream nếu không giải thích semantics representation coding theo HTTP.

**Cache key không chỉ là URL** khi có `Vary`. Nếu response dữ liệu cá nhân bị cache public theo URL mà không xét Authorization/cookie, `ETag` không chữa được rò rỉ thông tin. Các policy `private`, `no-store`, security và CDN settings phải được thiết kế đồng bộ.

## 16. Cache-Control: no-cache, no-store, private, max-age

| Directive | Ý nghĩa chính |
| --- | --- |
| `no-cache` | Có thể lưu nhưng **phải revalidate** trước khi tái sử dụng |
| `no-store` | Không lưu nội dung response theo chỉ thị cache |
| `private` | Chỉ private cache (ví dụ browser) được lưu theo chính sách; shared cache không lưu |
| `public` | Cho phép shared cache khi đáp ứng điều kiện liên quan |
| `max-age=60` | Fresh trong 60 giây theo HTTP age semantics |
| `must-revalidate` | Khi stale, cache phải revalidate trước reuse theo quy tắc |
| `immutable` | Tài nguyên được xem không thay trong freshness lifetime khi phù hợp |

Với dữ liệu cá nhân/secret, `CacheControl.noStore()` thường phù hợp hơn conditional GET nếu caching không được cho phép. Với dữ liệu public ít đổi và muốn tiết kiệm băng thông, dùng `maxAge(...)` kết hợp ETag/Last-Modified sau khi stale. Với dữ liệu cần mỗi lần kiểm tra server, `noCache()` cộng validator là pattern phổ biến.

`ETag` không thay thế `Cache-Control`. `304` là response cho revalidation, không có body; cache phải áp dụng logic cập nhật metadata của stored response khi nhận 304.

## 17. 304 và những headers cần giữ

Response **304 Not Modified** không có message body. Server cần cung cấp metadata cache/validator phù hợp theo RFC 9110 và RFC 9111, gồm những header liên quan mà một 200 tương ứng sẽ gửi, ví dụ `ETag`, `Cache-Control`, `Content-Location`, `Date`, `Expires`, `Vary` theo điều kiện của chuẩn.

Không nhất thiết mọi 304 đều có `Content-Type` giống 200; hãy kiểm tra những headers chuẩn yêu cầu và behavior framework. Không gọi `response.getWriter().write(...)` sau khi đã quyết định 304 và không trả JSON `{"message":"not modified"}` như body 304.

Nếu không có bản lưu trong cache/client, một response 304 một mình **không đủ** để tạo nội dung. Client không gửi validator tùy tiện trừ khi thật sự có trạng thái lưu tương ứng, và khi không có cached body hãy fetch lại 200.

## 18. HEAD, Range, If-Range và file lớn

HEAD có semantics như GET về metadata nhưng không có response content. `If-None-Match`/`If-Modified-Since` cũng áp dụng cho conditional HEAD.

Với file download:

- `Range` có thể yêu cầu một phần representation.
- `If-Range` yêu cầu server chỉ trả partial content khi validator tương thích; nếu không, bỏ qua Range để trả representation đầy đủ.
- `If-Range` cần validator phù hợp; **không dùng weak ETag** cho điều kiện byte-range.
- Response partial có thể là **206 Partial Content** hoặc **416 Range Not Satisfiable** tùy request.
- Conditional requests và Range có thứ tự/điều kiện riêng theo RFC; không biến mọi request Range có `If-None-Match` thành 206.

Ví dụ này không triển khai file ranges. Nếu API tải file lớn cần resume, hãy dùng Spring `Resource` và controller/static resource features phù hợp, test HTTP thật với ETag, If-Range, Accept-Ranges, Content-Range và proxy. Đừng viết parser byte ranges thủ công chỉ để tiết kiệm vài dòng.

## 19. Optimistic locking nhiều instance và database

Một backend nhiều replica không thể dùng một `AtomicReference` trong mỗi pod: chúng có state riêng và ETags mâu thuẫn. Nên đưa version authoritative xuống database (hoặc storage transactionally consistent).

Ví dụ ý tưởng SQL:

```sql
UPDATE documents
SET text = :newText,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND version = :expectedVersion;
```

Nếu row count = 1, update thành công. Nếu row count = 0, cần phân biệt tài nguyên đã mất/quyền thay đổi với stale version theo contract, thường trả 404/403/412. Mọi precondition cần được kiểm tra **tại cùng điểm atomic với mutation**, không tách GET version rồi một UPDATE không điều kiện.

Spring Data JPA với `@Version` cho phép optimistic locking của entity, nhưng exception/thời điểm flush có thể xuất hiện trong transaction; controller/service phải map conflict thích hợp, không nuốt lỗi thành 200. Nếu dùng `If-Match`, tránh dùng mã version từ ETag không được chứng thực hoặc không khớp đúng resource/user.

### 412 và 409

- `412 Precondition Failed`: header `If-Match`/`If-Unmodified-Since`/`If-None-Match` của request không thỏa trạng thái hiện tại.
- `409 Conflict`: mâu thuẫn với trạng thái/luật nghiệp vụ ngoài precondition (ví dụ trạng thái đơn hàng không cho phép hủy).
- `428 Precondition Required`: server yêu cầu request có điều kiện nhưng client không gửi.

Không biến mọi optimistic locking exception thành 409 nếu HTTP contract đã quy định `If-Match`. Ngược lại, thiếu precondition không nhất thiết là 428 trừ khi API định nghĩa policy này.

## 20. Các sai lầm thường gặp

1. **Bỏ dấu ngoặc kép ETag:** `If-None-Match: abc` không phải cách biểu diễn chuẩn của tag `"abc"`.
2. **Dùng weak ETag cho If-Match mạnh:** không strong-match; thường 412.
3. **Coi ETag là mật khẩu/định danh bí mật:** có thể bị lộ, cache/log/track.
4. **Gắn cùng strong ETag cho JSON và XML có bytes khác:** validator không phản ánh selected representation.
5. **Chỉ dựa updatedAt của bảng chính khi JSON lấy nhiều bảng:** dữ liệu đổi mà validator cũ.
6. **Cho rằng có ETag tức cache tự lưu dữ liệu an toàn:** cần Cache-Control và auth/cache policy.
7. **Nhầm no-cache với no-store:** no-cache vẫn cho phép lưu nhưng cần revalidate.
8. **Tự viết `If-None-Match OR If-Modified-Since`:** vi phạm precedence khi cả hai xuất hiện.
9. **Dùng Last-Modified với nano precision trong HTTP header:** HTTP-date chỉ đến giây.
10. **Dùng date-only optimistic locking với nhiều writes trong cùng giây:** có nguy cơ lost update.
11. **Trả 304 có body JSON:** sai semantics.
12. **Trả 304 khi resource chưa tồn tại:** nhầm với 404.
13. **Chỉ check version rồi save sau đó không atomic:** hai clients có thể cùng ghi đè.
14. **Bật ShallowEtagHeaderFilter và nghĩ tránh được query/serializer:** filter đã cần body để tính ETag.
15. **Tính checksum của body lớn cho mọi request và nghĩ miễn phí:** dùng CPU/RAM và buffering.
16. **Không xét Vary với nhiều representation/locale:** shared cache có thể trả nhầm variant.
17. **Dùng ETag cá nhân hóa nhưng cache public:** rò rỉ data/track user.
18. **Không kiểm tra auth trước khi trả validator:** có thể lộ existence/version.
19. **Dùng If-Match * như chống ghi đè:** * chỉ yêu cầu hiện hữu.
20. **Dựa vào controller response version thay cho database lock:** race giữa check/write vẫn tồn tại.
21. **Cố dùng HTTP status 304 cho PUT:** khi `If-None-Match` false ở method khác GET/HEAD, status thường 412.
22. **Không test 412/428:** frontend âm thầm overwrite thay đổi của người khác.
23. **Không test 304 body rỗng:** client có thể dùng sai cơ chế cache.
24. **Không đo bandwidth và server CPU riêng:** shallow validators thường tiết kiệm bandwidth, không tiết kiệm render.
25. **Không test qua proxy/CDN:** edge có thể strip/replace validators hoặc nén/đổi representation.
26. **Không có migration/invalidator khi đổi serialization/schema:** ETag mạnh cũ có thể không còn phù hợp.

## 21. Checklist triển khai production

### Tài nguyên và representation

- [ ] Validator biểu diễn đúng resource/representation và đổi khi nội dung công khai đổi?
- [ ] Strong hay weak ETag được chọn có chủ đích theo semantics?
- [ ] Giá trị ETag là opaque, không lộ secret hoặc PII?
- [ ] Last-Modified là server-authoritative HTTP date, có rủi ro same-second được xử lý?
- [ ] Với nhiều variants, Vary và ETag tương thích cách chọn representation?
- [ ] Dữ liệu cá nhân dùng Cache-Control private/no-store phù hợp, không cache public tùy tiện?

### Conditional reads

- [ ] GET bình thường trả 200/body/ETag (và Last-Modified nếu có)?
- [ ] If-None-Match matching trả 304 **không body**?
- [ ] If-None-Match stale trả 200/body mới?
- [ ] Nếu có cả If-None-Match và If-Modified-Since, kiểm precedence?
- [ ] Date invalid/method không phù hợp được xử lý đúng?
- [ ] 304 vẫn có những cache headers/validator cần thiết?
- [ ] Auth/tenant check xảy ra trước disclosure của resource validator?

### Conditional writes

- [ ] If-Match strong tags được so sánh đúng; weak tags không dùng cho lost update?
- [ ] Missing precondition trả 428 nếu API yêu cầu?
- [ ] Stale precondition trả 412, không mutation?
- [ ] Check + update atomic ở DB/transaction hoặc CAS tương đương?
- [ ] Khi nhiều pods/instances, version thống nhất?
- [ ] Race được kiểm thử, không phụ thuộc một read-before-write rời rạc?
- [ ] GET sau update cung cấp validator mới cho client?

### Hệ thống

- [ ] Có test MockMvc cho headers, body, statuses, header precedence?
- [ ] Có HTTP integration test qua servlet container, reverse proxy, CDN?
- [ ] Shallow ETag không áp cho streaming/large content một cách mù quáng?
- [ ] Cache hit/revalidation/bandwidth/CPU/DB được đo riêng?
- [ ] Monitoring 304/412/428 và logs không làm lộ ETags chứa dữ liệu nhạy cảm?

## 22. Câu hỏi tự kiểm tra

**1.** ETag khác Cache-Control thế nào?

**Đáp án:** ETag là validator của representation; Cache-Control quy định lưu/reuse/revalidate. Có ETag không đồng nghĩa được cache public.

**2.** GET có `If-None-Match` trùng ETag hiện tại, server trả gì?

**Đáp án:** Thường 304 Not Modified với body rỗng; client dùng cached body.

**3.** PUT có `If-Match` cũ sau khi người khác cập nhật?

**Đáp án:** 412 Precondition Failed nếu precondition không khớp, không tiến hành mutation.

**4.** `If-Match: W/"abc"` có match strong current `"abc"` không?

**Đáp án:** Không. If-Match dùng strong comparison.

**5.** GET chứa cả `If-None-Match` stale và `If-Modified-Since` trùng date?

**Đáp án:** If-None-Match ưu tiên. Stale tag không ngăn body mới, request có thể trả 200.

**6.** Vì sao Last-Modified khó dùng chống writes nhanh?

**Đáp án:** HTTP-date chỉ tới giây, có thể không nhận ra hai thay đổi cùng giây.

**7.** Vì sao ShallowEtagHeaderFilter không tiết kiệm DB query?

**Đáp án:** Nó dựa vào response body đã render mới tính ETag, thường không bỏ qua việc tạo body.

**8.** `If-Match: *` có chống lost update không?

**Đáp án:** Không. Nó chỉ yêu cầu resource tồn tại, không yêu cầu đúng phiên bản.

**9.** Nhiều pods chạy AtomicReference riêng có chống lost update toàn hệ thống không?

**Đáp án:** Không. Cần authoritative state/transaction/version ở shared database hoặc storage.

**10.** 304 có được kèm JSON mô tả “not modified” không?

**Đáp án:** Không. 304 không có message body; hãy trả validator/cache metadata theo chuẩn.

**11.** Vì sao ETag từ version của bảng có thể không mạnh với JSON?

**Đáp án:** JSON có thể đổi do serializer, locale, quan hệ khác hoặc field ngoài version row, nên tag không đại diện đầy đủ cho representation.

**12.** Khi thiếu If-Match ở PUT, lúc nào trả 428?

**Đáp án:** Khi API yêu cầu precondition để bảo vệ updates; 428 là policy của server, không mặc định cho mọi PUT.

## 23. Tài liệu tham khảo

- Spring Framework — HTTP Caching (controllers, CacheControl, ShallowEtagHeaderFilter): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html
- Spring Framework — ResponseEntity: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html
- Spring Framework — ServletWebRequest Javadoc: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/web/context/request/ServletWebRequest.html
- Spring Framework — ShallowEtagHeaderFilter Javadoc: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/web/filter/ShallowEtagHeaderFilter.html
- Spring Framework — CacheControl API: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/http/CacheControl.html
- RFC 9110 — HTTP Semantics, conditional request fields `If-Match`, `If-None-Match`, `If-Modified-Since`, `If-Unmodified-Since`, `If-Range`, `304`/`412`: https://www.rfc-editor.org/rfc/rfc9110.html
- RFC 9111 — HTTP Caching (`Cache-Control`, `Vary`, validation, 304 updates): https://www.rfc-editor.org/rfc/rfc9111.html
- RFC 6585 — Additional HTTP Status Codes (`428 Precondition Required`): https://www.rfc-editor.org/rfc/rfc6585.html
- Spring Data JPA — Optimistic Locking/`@Version` use: https://docs.spring.io/spring-data/jpa/reference/
- Jakarta Persistence specification: https://jakarta.ee/specifications/persistence/
