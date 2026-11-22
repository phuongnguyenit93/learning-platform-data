# Kiểm thử tải tệp, cookie, phiên và tài nguyên tĩnh trong Spring Boot

Một web API có thể trả JSON đúng nhưng vẫn thất bại khi người dùng tải một tệp, trình duyệt không giữ cookie, phiên đăng nhập biến mất sau request tiếp theo, hoặc CSS/JavaScript không tải được khi đóng gói JAR. Những lỗi này không thể được phát hiện đầy đủ chỉ bằng unit test của service. Chúng nằm tại giao điểm của **Spring MVC**, **Servlet container**, **HTTP headers**, **trạng thái client**, **session store**, **resource handler**, **reverse proxy** và **trình duyệt**.

Bài thuộc nhóm **Kiểm thử web runtime**. Trọng tâm là **Spring Boot 3.3.x, Java 17+, Spring MVC/Servlet, JUnit 5 và MockMvc**. Ta sẽ xây một project chạy được với:

- **Upload:** `POST /api/files` bằng `multipart/form-data`, lưu file nhỏ trong memory để thử nghiệm.
- **Download:** `GET /api/files/{id}` trả bytes chính xác, content type, length và `Content-Disposition: attachment`.
- **Cookie:** `POST /api/cookies/theme?value=dark` phát `Set-Cookie`; `GET /api/cookies/theme` đọc cookie; endpoint xóa cookie.
- **Session:** `GET /api/session/visit` tăng biến đếm trong `HttpSession`; `POST /api/session/logout` invalidates session.
- **Static:** `GET /assets/hello.txt` qua `ResourceHttpRequestHandler`, không qua một `@GetMapping` tự viết.
- **Tests:** `MockMultipartFile`, `MockHttpSession`, assertions trên `Set-Cookie`, bytes, status, static resources và một live HTTP test với `@SpringBootTest(RANDOM_PORT)` + Java `HttpClient`/`CookieManager`.

**Phân biệt bắt buộc:** `MockMvc` thực thi pipeline Spring MVC bằng mock Servlet request/response; nó **không khởi động một HTTP server thật**, không tạo cookie jar trình duyệt và `multipart()` **không thử multipart parser của Tomcat**. Một bài test `MockMvc` pass chưa chứng minh rằng container, proxy, TLS, upload size limit, session cookie hay caching hoạt động đúng ngoài mạng. Vì vậy phải chọn tầng kiểm thử phù hợp cho từng hành vi.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **upload** và **download**, request body, multipart field names, file bytes, HTTP status và headers.
2. Viết kiểm thử `MockMvcRequestBuilders.multipart()` với `MockMultipartFile` và nhận biết giới hạn mô phỏng của nó.
3. So sánh bytes của file tải xuống, kiểm tra `Content-Type`, `Content-Length`, `Content-Disposition`, `Cache-Control` và error 404.
4. Thử `Set-Cookie`, `Cookie`, các thuộc tính `Path`, `Domain`, `HttpOnly`, `Secure`, `SameSite`, `Max-Age`.
5. Phân biệt cookie được gửi bởi browser với `HttpSession` do server quản lý; kiểm tra tạo, dùng lại, invalidation và timeout.
6. Sử dụng `MockHttpSession` trong `MockMvc` thay vì kỳ vọng mock container tự quản lý `JSESSIONID` như Tomcat.
7. Kiểm tra static resources từ `classpath:/static/`, default mappings, welcome page, HTTP caching và file không được phép công khai.
8. Chọn `@WebMvcTest`, `@SpringBootTest + @AutoConfigureMockMvc` hay `RANDOM_PORT` và hiểu trade-offs.
9. Thử giới hạn file upload trên **hai lớp**: validation ứng dụng và cấu hình multipart parser thật.
10. Viết test tích cực và tiêu cực: file rỗng/lớn, cookie không hợp lệ, session mới/cũ, tài nguyên 404, data leaks.
11. Phân tích sự khác biệt giữa `HTTP 200`, `206 Partial Content`, `304 Not Modified`, `400`, `403`, `404` và `413`.
12. Đưa các yêu cầu bảo mật của upload/download, cookies, sessions và static resources vào test plan.

## 2. Ma trận: cần kiểm thử ở tầng nào?

| Tình huống | MockMvc | HTTP server thật / RANDOM_PORT | Browser hoặc proxy E2E |
| --- | --- | --- | --- |
| Controller nhận đúng file field `file` | Rất phù hợp | Phù hợp | Thường không bắt buộc |
| Body bytes upload được xử lý đúng | Phù hợp | Phù hợp | Khi có client cụ thể |
| Parser multipart, boundary, file size limit của container | **Không đủ** | **Cần** | Cần nếu đi qua ingress |
| Download trả đúng bytes + headers | Phù hợp | Phù hợp | Khi browser download UX quan trọng |
| `Content-Disposition` được browser hiểu đúng filename | Test header | Test header | Cần cho nhiều browser/Unicode |
| `Set-Cookie` có flags đúng | Test trực tiếp header | Test header thực | Cần cho policy browser |
| Client tự giữ/gửi cookie qua request sau | Không tự làm; truyền cookie bằng test code | Cookie-aware client kiểm thử được | Browser là chuẩn hành vi thực |
| `HttpSession` giữ trạng thái qua requests | Dùng `MockHttpSession` | Cookie jar + container/session store | Cần với SSO/auth flows |
| Session persistence khi restart/đổi replica | Không chứng minh | Cần deployment và store thật | Cần cluster E2E |
| Classpath static asset có thể được serve | Phù hợp với context thật | Phù hợp khi đóng gói JAR | Cần để kiểm tra CDN/cache |
| Cache `304`, Range `206`, gzip, reverse proxy | Có thể thử vài contract | Cần để xác thực network behavior | Cần nếu có CDN/gateway |
| Authentication/CSRF và object-level authorization | Test với Spring Security | Test live | Test browser flow |

**Không có một annotation kiểm thử nào thay thế tất cả các tầng.** Mục tiêu không phải “mọi test phải chạy cả hệ thống”, mà là chọn tầng thấp nhất có thể chứng minh một hợp đồng và thêm một số integration/E2E tests cho các hành vi phụ thuộc container hoặc browser.

## 3. Upload file qua multipart/form-data

### 3.1. Cấu trúc HTTP multipart

Browser gửi form:

```html
<form action="/api/files" method="post"
      enctype="multipart/form-data">
  <input type="file" name="file">
  <button type="submit">Upload</button>
</form>
```

Ở HTTP level, request tương đương:

```http
POST /api/files HTTP/1.1
Content-Type: multipart/form-data; boundary=BOUNDARY123

--BOUNDARY123
Content-Disposition: form-data; name="file"; filename="example.txt"
Content-Type: text/plain

example content
--BOUNDARY123--
```

Đây là wire format minh họa, không phải body chính xác do trình duyệt tạo. `boundary` do client HTTP library tạo, và các phần thực được phân tách theo cú pháp multipart. Spring MVC bind field có `name="file"` vào `@RequestParam("file") MultipartFile file`.

Ba điểm dễ nhầm:

- **Field name** `file` phải khớp tên tham số controller. Client có `name="avatar"` nhưng server đòi `file` có thể gây 400 vì thiếu required part/parameter.
- **Original filename** như `../../secrets.txt` là thông tin **do client cung cấp**, không được dùng trực tiếp làm đường lưu hoặc tin rằng đó là tên an toàn.
- **Content-Type** của part cũng có thể được client giả mạo. Kiểm tra extension/MIME header không đủ để bảo đảm file thực sự an toàn; đối với uploads công khai cần allowlist, scan, file signatures và chính sách lưu phù hợp.

### 3.2. MockMultipartFile không có nghĩa đã parse multipart thực

Trong Spring Test:

```java
MockMultipartFile sample = new MockMultipartFile(
    "file",
    "sample.txt",
    "text/plain",
    "hello\n".getBytes(StandardCharsets.UTF_8)
);

mockMvc.perform(multipart("/api/files").file(sample));
```

`MockMultipartFile` dựng một `MultipartFile` giả với field name, filename, content type và bytes. `multipart()` tạo `MockMultipartHttpServletRequest`; nó **không thực sự đọc/parses raw multipart body bằng servlet container**. Bởi vậy test này phát hiện mapping, validation và service call, nhưng **không** chứng minh boundary parsing, streaming-to-disk threshold hay upload max-size của Tomcat.

Nếu test muốn chứng minh request từ một browser/curl đúng, phải có bài kiểm thử với **HTTP server thật**, sử dụng client multipart thực tế.

### 3.3. Nên assert điều gì ở upload?

- Thành công: status 201/200 theo contract, response ID và media type phù hợp.
- Field name: gửi `file` đúng; trường hợp thiếu file gây 400 (có thể do MVC binding).
- File rỗng: không nhận/lưu nếu nghiệp vụ không cho phép.
- File quá lớn: app validate rõ và embedded servlet container cũng giới hạn body/part.
- Nội dung: bytes không bị biến đổi encoding, hash đúng nếu nghiệp vụ yêu cầu.
- Tên file bất thường: `../a.txt`, Unicode, control chars — không được quyết định path lưu hoặc response header mà chưa sanitize.
- MIME giả: không tin `file.getContentType()` làm bằng chứng file sạch.
- Duplicate và concurrency: hai upload có IDs riêng; không overwrite tenant khác.
- Quyền: user A không thể tải file của user B chỉ vì đoán được ID.
- Cleanup: temporary files/storage không tồn tại vô hạn sau thất bại.
- CSRF và authentication nếu browser dùng session cookies.

### 3.4. Upload lớn và memory

Không nên gọi `file.getBytes()` cho file nhiều GB trong production; nó copy toàn bộ content vào memory. Với demo nhỏ có giới hạn 64 KiB, dùng byte array giúp test dễ hiểu. Sản phẩm thực phải dùng streaming tới disk/object storage, kiểm soát quota, timeout, antivirus và cleanup. Đừng lưu user uploads vào `src/main/resources/static`: nó là tài nguyên công khai được đóng gói khi build, không phải private upload directory.

## 4. Download file: kiểm tra bytes và HTTP contract

Server không chỉ trả một mảng bytes. Browser/client dựa vào:

| Header/status | Ý nghĩa | Điều cần test |
| --- | --- | --- |
| `200 OK` | Response có full representation | Body bytes đúng |
| `Content-Type` | Loại nội dung | Không tin MIME của upload; với download không biết loại nên dùng octet-stream |
| `Content-Length` | Kích thước representation được truyền | Khi biết độ dài, so với bytes |
| `Content-Disposition: attachment` | Gợi ý browser tải thay vì render inline | Filename được tạo an toàn ở server |
| `Cache-Control: no-store` | Không lưu cache file riêng tư trong bài mẫu | Không bị shared cache lưu nhầm |
| `X-Content-Type-Options: nosniff` | Giảm sniffing content type trên browser | Có với file do người dùng tải lên |
| `404 Not Found` | Không có file hoặc không cho biết tài nguyên | Không lộ path nội bộ |
| `206 Partial Content` | Trả một khoảng bytes theo `Range` | `Content-Range` và đúng phần bytes |
| `304 Not Modified` | Conditional request xác nhận representation chưa đổi | Không có full body |
| `416 Range Not Satisfiable` | Range không thỏa mãn representation | Không trả nhầm 200 và dữ liệu sai |

**Lưu ý:** `206/416` liên quan byte ranges, không tự xảy ra với mọi loại return type. Spring MVC hỗ trợ ranges cho `Resource` hoặc `ResponseEntity<Resource>` theo điều kiện của framework. `InputStreamResource` không phù hợp với cơ chế này trong các trường hợp được ghi ở tài liệu range; nên dùng `ByteArrayResource` hoặc một `Resource` có thể đọc lại khi cần range. Download thực tế có thể do CDN/object storage xử lý ranges độc lập.

### 4.1. Không dùng client filename trực tiếp trong Content-Disposition

Phản ví dụ:

```java
// Không làm thế với dữ liệu chưa sanitize:
String filename = multipartFile.getOriginalFilename();
```

Tên file có thể chứa `../`, slash/backslash, dấu quote, control characters hoặc ký tự Unicode bất thường. Nên dùng một tên generated/allowlisted, hoặc hàm sanitize và `ContentDisposition.attachment().filename(...)` phù hợp, không nối chuỗi header thủ công từ input tùy ý.

### 4.2. Byte equality khác text equality

Nếu file chứa NUL, byte `0xFF`, ảnh PNG hay ZIP, test `response.getContentAsString()` có thể biến đổi encoding. Dùng:

```java
assertThat(result.getResponse().getContentAsByteArray())
    .isEqualTo(expectedBytes);
```

Khi file lớn, có thể dùng hash SHA-256 và content length. Nhưng đừng chỉ assert filename hoặc status rồi kết luận download không bị hỏng.

### 4.3. HEAD, Range và conditional requests

- `HEAD` cần header/status tương ứng GET mà không có body response.
- `Range: bytes=0-3` kỳ vọng `206` và 4 bytes đầu khi server hỗ trợ; có thể có `Content-Range`.
- `If-Modified-Since` hoặc `If-None-Match` có thể kích hoạt `304` khi server có `Last-Modified`/`ETag` phù hợp.
- Nếu không có validator, `304` không bắt buộc xảy ra.
- `Cache-Control` là policy; `Last-Modified`/`ETag` là validators; **không đồng nhất** chúng.
- Có caching ở CDN/proxy, phải kiểm chứng tại chặng thật; `MockMvc` không mô phỏng toàn bộ proxy.

Với Spring Boot static resource handler, `Last-Modified` thường được hỗ trợ dựa trên resource metadata; việc dùng `If-Modified-Since` có thể nhận `304`. Một file được đóng gói trong JAR có timestamp, thứ tự làm tròn tới giây và behavior có thể phụ thuộc cách build/resource implementation; viết test hợp đồng dựa trên header thực nhận, không hardcode mốc thời gian.

## 5. Cookie: Set-Cookie là response header, Cookie là request header

Browser nhận:

```http
Set-Cookie: theme=dark; Path=/; Max-Age=600; HttpOnly; SameSite=Lax
```

Trong request cùng origin sau đó, nếu các điều kiện cookie phù hợp, browser gửi:

```http
Cookie: theme=dark
```

**`Set-Cookie` và `Cookie` khác vai trò.** Server đặt cookie bằng `Set-Cookie`; browser quyết định có lưu và gửi nó trở lại hay không, dựa trên `Domain`, `Path`, `Secure`, `SameSite`, thời gian hết hạn, chính sách third-party cookies và browser privacy modes.

### 5.1. Các attributes cần test

| Thuộc tính | Ý nghĩa thực tế | Điều phải kiểm |
| --- | --- | --- |
| `Path=/` | Giới hạn phạm vi URL gửi cookie | Đường được chọn có phù hợp ứng dụng? |
| `Domain` | Phạm vi host/subdomains | Không đặt quá rộng; host-only thường an toàn hơn |
| `HttpOnly` | JavaScript `document.cookie` không đọc trực tiếp | Không thay authentication/CSRF, cookie vẫn được gửi trong HTTP |
| `Secure` | Browser thường chỉ gửi trên HTTPS (có ngoại lệ/chi tiết localhost) | Production phải bật TLS và Secure |
| `SameSite=Strict/Lax/None` | Chính sách gửi trong cross-site contexts | Không thay CSRF validation khi cần |
| `Max-Age`, `Expires` | Thời hạn lưu cookie | Giá trị 0 thường dùng xóa |
| Cookie value | Dữ liệu client gửi lại | Không chứa password/secret plain text không cần thiết |

**`HttpOnly` không mã hóa cookie.** **`Secure` không ngăn XSS toàn bộ trang.** **`SameSite=Lax` không thay thế CSRF token** cho các thao tác state-changing trong threat model tương ứng. Với cross-site `SameSite=None`, browser hiện đại thường yêu cầu `Secure`; khi có CORS credentials phải cấu hình origin/cookie policy đầy đủ.

### 5.2. Tại sao MockMvc không tự làm cookie jar?

Trong `MockMvc`, một request mới thường bắt đầu với mock request mới. Nếu response đầu tiên có `Set-Cookie`, test không tự có browser để lưu/gửi lại ở request sau. Muốn test controller đọc cookie:

```java
mockMvc.perform(get("/api/cookies/theme")
        .cookie(new Cookie("theme", "dark")))
    .andExpect(jsonPath("$.theme").value("dark"));
```

Đây là **test ứng dụng với cookie do test cung cấp**, không chứng minh browser sẽ lưu cookie khi `Secure/SameSite/Domain` được đặt. Test cookie jar thật với `HttpClient` hoặc browser trên live server.

### 5.3. Xóa cookie phải khớp scope

Khi xóa, gửi `Set-Cookie` cùng **name**, **Path** và khi đã dùng Domain thì **Domain** tương ứng, với `Max-Age=0`. Nếu cookie được tạo ở `Path=/app` nhưng xóa ở `Path=/`, browser có thể giữ cookie cũ. Test không chỉ thấy `Max-Age=0` mà phải kiểm tra cookie name/path/domain và kết quả browser sau đó.

### 5.4. Cookie không phải session

Một cookie có thể lưu theme/language đơn giản, nhưng **đừng cho rằng cookie tự là một server-side session**. Ngược lại, session cookie `JSESSIONID` thường chỉ là một **session identifier**; dữ liệu `HttpSession` như cart/visits/CSRF state nằm trong container session store hoặc Spring Session repository. Không gửi object Java session qua cookie mặc định.

## 6. HttpSession: kiểm tra tạo, tái sử dụng và hủy

Servlet `HttpSession` là nơi server lưu trạng thái gắn với session ID. Ví dụ:

```java
@GetMapping("/api/session/visit")
public Map<String, Integer> visit(HttpSession session) {
    Integer current = (Integer) session.getAttribute("visits");
    int next = current == null ? 1 : current + 1;
    session.setAttribute("visits", next);
    return Map.of("visits", next);
}
```

Đây là **snippet**, controller đầy đủ ở mục 10. Lần gọi đầu tiên trên session mới trả `{"visits":1}`; cùng session lần sau trả `{"visits":2}`. Nếu client không mang đúng session identifier, server có thể tạo session mới, và đếm lại từ 1.

### 6.1. Test bằng MockHttpSession

```java
MvcResult first = mockMvc.perform(get("/api/session/visit"))
    .andExpect(jsonPath("$.visits").value(1))
    .andReturn();

MockHttpSession session =
    (MockHttpSession) first.getRequest().getSession(false);

mockMvc.perform(get("/api/session/visit").session(session))
    .andExpect(jsonPath("$.visits").value(2));
```

Đây là cách test server state. **Không bắt buộc có `JSESSIONID` Set-Cookie trong MockMvc**. Spring Framework docs nêu MockMvc không có servlet container thật, mặc định không có jsessionid cookie hay các dispatch semantics của network container. Vì vậy không viết `MockMvc` test yêu cầu container phát JSESSIONID tự động rồi coi failure là Spring session bug.

### 6.2. Invalidation

`session.invalidate()` làm session không còn hợp lệ. Với `MockHttpSession` có thể assert `isInvalid()`. Trong browser/session-client thực, việc logout có thể yêu cầu thêm cookie deletion và security context cleanup, tùy hệ thống. Không đồng nhất “session bị invalidate” với “browser không còn gửi cookie cũ”, vì browser có thể giữ identifier cũ tới khi hết hạn/được xóa; server phải từ chối/tạo session mới cho ID invalid.

### 6.3. Timeout và phân tán

- `server.servlet.session.timeout=15m` quy định timeout session của Servlet theo cấu hình.
- Session timeout không phải cookie expiry; cookie session có thể không có `Max-Age` và hết khi browser session kết thúc theo chính sách trình duyệt.
- Với multi-instance app, một in-memory `HttpSession` trên Pod A không tự xuất hiện ở Pod B.
- Nếu dùng Spring Session Redis/JDBC, cần test repository, serialization, TTL, session invalidation và network failure.
- Session fixation protection khi login, rotation session ID và re-authentication là trách nhiệm security framework/cấu hình.
- Unit test có `MockHttpSession` không chứng minh session tồn tại sau restart/pod failover.

### 6.4. Cookie JSESSIONID và authentication

`JSESSIONID` có thể được Servlet container tạo khi session thật xuất hiện. Cookie name có thể thay theo `server.servlet.session.cookie.name` hoặc Spring Session/security config. Trong bài demo dùng default, live test kiểm tra cookie persistence bằng `HttpClient.CookieManager`.

**Cẩn trọng:** không log session IDs, không đưa chúng vào metric labels, URL hoặc support ticket công khai. Session identifier là credential bearer trong nhiều ứng dụng; ai sở hữu nó có thể chiếm phiên nếu thiếu bảo vệ khác.

## 7. Tài nguyên tĩnh: route, classpath và cache

Spring Boot 3.3 (khi không thay MVC auto-configuration) mặc định phục vụ static content từ:

- `classpath:/static/`
- `classpath:/public/`
- `classpath:/resources/`
- `classpath:/META-INF/resources/`
- Một số nguồn dưới ServletContext root theo cấu hình.

Mặc định mappings là `/**`, handler thường là `ResourceHttpRequestHandler`. Ví dụ file `src/main/resources/static/assets/hello.txt` được truy cập tại **`GET /assets/hello.txt`**, không phải `GET /static/assets/hello.txt`.

### 7.1. Không dùng src/main/webapp cho executable JAR

Spring Boot docs nhấn mạnh `src/main/webapp` dùng chủ yếu với WAR packaging; khi build executable JAR, static files ở đó có thể bị bỏ qua. Đặt assets vào `src/main/resources/static` hoặc địa điểm đúng cấu hình để chúng được đóng gói trong JAR.

### 7.2. Welcome page và route ưu tiên

Một `index.html` tại `classpath:/static/index.html` có thể được phục vụ ở `/` làm welcome page khi không có controller mapping ưu tiên khác. Controller `@GetMapping("/")` có thể thay thế welcome page theo handler mapping order. Test route thực tế, đừng chỉ kiểm tra file tồn tại trên disk.

### 7.3. Public static vs private uploads

**Đừng đặt file tải lên của người dùng tại `classpath:/static/`** nếu không muốn mọi người có thể thử truy cập theo URL. Trong demo, upload được lưu trong memory và truy cập qua controller có ID; production cần object-level authorization trước khi trả bytes. Static directory chỉ nên chứa assets công khai (CSS, JS, images, icons) không chứa environment secrets, backups hoặc dữ liệu khách hàng.

### 7.4. Test static bytes và 404

Với `@SpringBootTest + @AutoConfigureMockMvc`, Spring Boot tạo MVC mappings/resource handlers như ứng dụng thật (trừ khác biệt mock container):

```java
mockMvc.perform(get("/assets/hello.txt"))
    .andExpect(status().isOk())
    .andExpect(content().string("asset-ok\n"));

mockMvc.perform(get("/private-note.txt"))
    .andExpect(status().isNotFound());
```

Trong demo, `private-note.txt` nằm ở `src/main/resources/private/private-note.txt`, **ngoài** các static resource locations mặc định. Test 404 xác minh không bị serve bởi default resource handler. Nhưng security scan vẫn phải tìm secret files, archive/backup extensions và đường dẫn đặc biệt; test một path không chứng minh mọi đường đi đều an toàn.

### 7.5. Cache-Control, Last-Modified và 304

Với assets công khai ít thay đổi, có thể cấu hình:

```properties
spring.web.resources.cache.period=60s
spring.web.resources.cache.use-last-modified=true
```

Điều này cho phép cache resource theo kỳ 60 giây và dùng Last-Modified metadata khi có. `Cache-Control` và `Last-Modified` phục vụ hai mục đích:

- `Cache-Control: max-age=60` hướng dẫn cache freshness.
- `Last-Modified` cùng `If-Modified-Since` cho phép conditional GET; khi chưa thay đổi có thể trả `304` không kèm toàn bộ body.

Nếu dùng hash-based asset versioning, có thể cấu hình resource chain; khi filename có content hash, cache dài thường hợp lý hơn. Nhưng upload/download riêng tư cần policy ngược lại như `Cache-Control: no-store`. Không cấu hình cache dài trên toàn app rồi vô tình cache tài liệu cá nhân.

### 7.6. Static resource không được test như controller business

`@WebMvcTest(SomeController.class)` là slice giới hạn, không chắc bao gồm toàn bộ resource config hoặc các bean mà full application có. Khi mục tiêu kiểm tra file tĩnh từ classpath và auto-configuration, **full application context với MockMvc** thường phù hợp hơn slice controller. Với packaging/CDN behavior, thêm `bootJar` + HTTP server thật + browser/edge tests.

## 8. Dự án hoàn chỉnh Spring Boot 3.3, Java 17+

Ta tạo một ứng dụng nhỏ nhưng đầy đủ để thực hành. Nó **không có Spring Security** vì muốn tập trung vào test transport/session/resource behavior; trong production mọi endpoint liên quan file/session cần xác thực, phân quyền, quota, CSRF và giám sát.

### 8.1. Build Gradle

Tạo từ [Spring Initializr](https://start.spring.io/) với Java 17+, Spring Boot **3.3.x**, Gradle/Groovy, Spring Web. Nếu cần một phiên bản cụ thể của nhánh 3.3, ví dụ `3.3.13`, chỉnh trong file Gradle do Initializr tạo:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là file `build.gradle` cốt lõi với plugin/dependencies và Java 17. Sử dụng Gradle Wrapper do Initializr cung cấp; không tự ép phiên bản Spring MVC/Jackson/JUnit lệch BOM. Với Spring Boot 4.x, package và tên test auto-configuration có thể khác; bài này chủ động giữ **Boot 3.3.x**.

`settings.gradle`:

```groovy
rootProject.name = 'runtime-files-test'
```

Cấu trúc thư mục:

```text
build.gradle
settings.gradle
gradlew
gradlew.bat
gradle/wrapper/...
src/
  main/
    java/demo/
      RuntimeFilesTestApplication.java
      FileStore.java
      FileController.java
      CookieSessionController.java
    resources/
      application.properties
      static/index.html
      static/assets/hello.txt
      private/private-note.txt
  test/
    java/demo/
      WebRuntimeMockMvcTest.java
      WebRuntimeHttpIntegrationTest.java
```

Tất cả Java classes ở package `demo` nên Spring Boot component scan tìm đúng controllers/service. File `src/main/resources/private/private-note.txt` chỉ nhằm kiểm tra không vô tình serve thư mục private.

### 8.2. RuntimeFilesTestApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuntimeFilesTestApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                RuntimeFilesTestApplication.class, args);
    }
}
```

### 8.3. FileStore.java — lưu file nhỏ trong memory

```java
package demo;

import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@Service
public class FileStore {

    private static final int MAX_BYTES = 64 * 1024;

    private final ConcurrentMap<String, byte[]> files =
            new ConcurrentHashMap<>();

    public String save(MultipartFile file) throws IOException {
        if (file.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "File must not be empty");
        }

        if (file.getSize() > MAX_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.valueOf(413),
                    "File too large");
        }

        byte[] bytes = file.getBytes();

        if (bytes.length > MAX_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.valueOf(413),
                    "File too large");
        }

        // Không tin originalFilename làm filesystem path.
        String id = UUID.randomUUID().toString();
        files.put(id, bytes.clone());
        return id;
    }

    public byte[] load(String id) {
        byte[] value = files.get(id);

        if (value == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND,
                    "File not found");
        }

        return value.clone();
    }
}
```

Lưu tại `src/main/java/demo/FileStore.java`.

Đây là **memory-only lab**. `ConcurrentHashMap` giúp nhiều requests thao tác map cơ bản an toàn; `UUID` tạo ID khó đoán hơn một số tăng, **không phải authorization**. File được copy vào RAM có giới hạn 64 KiB và **mất sau restart**. Production dùng disk/object storage phù hợp, quản lý quotas, file type validation, antivirus, multi-tenant permissions, TTL và cleanup. Không dùng `file.getOriginalFilename()` làm key/path lưu và không lưu dữ liệu riêng trong static directory.

Tại sao có cả `file.getSize()` và `bytes.length`? `getSize` cho phép reject sớm ở lớp ứng dụng; sau khi đọc bytes, ta vẫn đối chiếu độ dài thực. Điều này không thay giới hạn ở servlet multipart parser/gateway vì file đã có thể chiếm tài nguyên trước khi tới service.

### 8.4. FileController.java — upload và download

```java
package demo;

import java.io.IOException;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.http.CacheControl;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
public class FileController {

    private final FileStore store;

    public FileController(FileStore store) {
        this.store = store;
    }

    public record UploadedFile(String id) {
    }

    @PostMapping(path = "/api/files",
                 consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public UploadedFile upload(
            @RequestParam("file") MultipartFile file)
            throws IOException {

        return new UploadedFile(store.save(file));
    }

    @GetMapping("/api/files/{id}")
    public ResponseEntity<Resource> download(
            @PathVariable("id") String id) {

        byte[] bytes = store.load(id);

        ContentDisposition disposition =
                ContentDisposition.attachment()
                        .filename("download.bin")
                        .build();

        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        disposition.toString())
                .header("X-Content-Type-Options", "nosniff")
                .cacheControl(CacheControl.noStore())
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .contentLength(bytes.length)
                .body(new ByteArrayResource(bytes));
    }
}
```

Điểm đáng chú ý:

- Upload phản hồi `201 Created` với JSON `{"id":"..."}`; tên JSON field dựa trên record accessor.
- `MultipartFile` được bind từ field tên `file`, không phải mọi file field tùy ý.
- Download dùng `ResponseEntity<Resource>` + `ByteArrayResource`, giúp Spring MVC có thể áp dụng range handling cho `Resource` khi điều kiện thỏa. Không dùng `InputStreamResource` chỉ để kiểm tra resumable download.
- `Content-Disposition` do server tạo là tên cố định `download.bin`, không dùng original filename tùy ý.
- `application/octet-stream` và `nosniff` phù hợp khi loại file không đáng tin hoặc không biết.
- `Cache-Control: no-store` tránh cache document do upload ở demo; với file public/immutable cần chiến lược cache khác.
- Không có authorization trong demo. Production **phải** kiểm tra owner/tenant trước `store.load(id)`; UUID không thay quyền truy cập.
- `Content-Length` trong full 200 là độ dài bytes; khi xử lý Range 206, Spring có thể điều chỉnh headers theo representation từng phần.

### 8.5. CookieSessionController.java

```java
package demo;

import java.time.Duration;
import java.util.Map;

import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class CookieSessionController {

    @PostMapping("/api/cookies/theme")
    public ResponseEntity<Map<String, String>> setTheme(
            @RequestParam("value") String value,
            HttpServletRequest request) {

        if (!"dark".equals(value) && !"light".equals(value)) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "theme must be dark or light");
        }

        ResponseCookie cookie = ResponseCookie
                .from("theme", value)
                .path("/")
                .httpOnly(true)
                .secure(request.isSecure())
                .sameSite("Lax")
                .maxAge(Duration.ofMinutes(10))
                .build();

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .cacheControl(CacheControl.noStore())
                .body(Map.of("theme", value));
    }

    @GetMapping("/api/cookies/theme")
    public Map<String, String> readTheme(
            @CookieValue(value = "theme", required = false)
            String value) {

        return Map.of("theme",
                value == null ? "unset" : value);
    }

    @PostMapping("/api/cookies/theme/clear")
    public ResponseEntity<Void> clearTheme(
            HttpServletRequest request) {

        ResponseCookie expired = ResponseCookie
                .from("theme", "")
                .path("/")
                .httpOnly(true)
                .secure(request.isSecure())
                .sameSite("Lax")
                .maxAge(Duration.ZERO)
                .build();

        return ResponseEntity.noContent()
                .header(HttpHeaders.SET_COOKIE, expired.toString())
                .build();
    }

    @GetMapping("/api/session/visit")
    public ResponseEntity<Map<String, Integer>> visit(
            HttpSession session) {

        Integer previous =
                (Integer) session.getAttribute("visits");

        int next = previous == null ? 1 : previous + 1;

        session.setAttribute("visits", next);

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of("visits", next));
    }

    @PostMapping("/api/session/logout")
    public ResponseEntity<Void> logout(
            HttpServletRequest request) {

        HttpSession session = request.getSession(false);

        if (session != null) {
            session.invalidate();
        }

        return ResponseEntity.noContent()
                .cacheControl(CacheControl.noStore())
                .build();
    }
}
```

Lưu tại `src/main/java/demo/CookieSessionController.java`.

**Một số lưu ý chuyên môn:**

- `secure(request.isSecure())` chỉ để demo chạy được với local HTTP và kiểm thử HTTPS mô phỏng bằng `MockMvc.secure(true)`. **Production phải bảo đảm HTTPS và Secure cookie** bằng trusted TLS termination/forwarded headers; không tin header `X-Forwarded-Proto` từ Internet chưa được strip/validate.
- Cookie `theme` là HttpOnly trong demo để minh họa flag; một theme cookie trong ứng dụng thật có thể được JS đọc nếu có yêu cầu, khi đó hãy quyết định theo threat model, không copy flags máy móc.
- `SameSite=Lax` không thay CSRF token cho state-changing POST khi dùng cookie session authentication.
- `Map.of(...)` không chấp nhận null; controller thay missing cookie bằng chuỗi `"unset"`.
- `HttpSession` được tạo khi request vào endpoint visit. Test với `MockMvc` phải truyền cùng `MockHttpSession` sang request thứ hai.
- `logout` invalidate server session; nó **không mặc nhiên xóa mọi cookie trong browser**. Với authentication thật, sử dụng logout handling của Spring Security và cookie deletion phù hợp.
- Không đọc `Cookie[]` thô chỉ để log; session ID và tokens trong cookie là dữ liệu nhạy cảm.

### 8.6. Static files

Tạo file `src/main/resources/static/assets/hello.txt` có đúng một dòng kết thúc bằng newline:

```text
asset-ok
```

Dữ liệu được kiểm tra trong test là chuỗi `"asset-ok\n"`. Giữ newline cuối tệp.

Tạo `src/main/resources/static/index.html`:

```html
<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><title>Web runtime lab</title></head>
<body>
  <h1>Spring Boot web runtime lab</h1>
  <p><a href="/assets/hello.txt">Static asset</a></p>
</body>
</html>
```

Tạo file `src/main/resources/private/private-note.txt`:

```text
NOT_PUBLIC
```

File trong `private/` nằm trong classpath nhưng không thuộc static resource locations của Boot. `GET /private-note.txt` phải không trả nội dung của nó qua default static handler.

**Không cần một @Controller cho `/assets/hello.txt`**. Với Boot 3.3 MVC auto-configuration, `ResourceHttpRequestHandler` phục vụ nó từ classpath.

### 8.7. application.properties

```properties
server.port=8080

# Session Servlet: lab. Production bắt buộc HTTPS/Secure.
server.servlet.session.timeout=15m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax

# Giới hạn của container khi nhận multipart thực.
spring.servlet.multipart.max-file-size=64KB
spring.servlet.multipart.max-request-size=128KB

# Cache public static resources trong thời gian ngắn.
spring.web.resources.cache.period=60s
spring.web.resources.cache.use-last-modified=true

# Giữ Boot MVC auto-configuration và static mappings.
spring.web.resources.add-mappings=true
```

Lưu tại `src/main/resources/application.properties`.

**Giới hạn multipart trong property và validation trong FileStore phục vụ hai tầng khác nhau.** `spring.servlet.multipart.max-file-size`/`max-request-size` tác động tới multipart parser của server thật. Khi `MockMvc.multipart()` tự dựng `MockMultipartHttpServletRequest`, parser không chạy như live Tomcat; test upload quá lớn trong MockMvc chỉ chứng minh guard 64 KiB ở `FileStore`.

Với production, bật `server.servlet.session.cookie.secure=true` trên HTTPS, và đảm bảo reverse proxy forwarded headers được xử lý chỉ ở trust boundary. Local HTTP demo cố ý không cưỡng bức Secure cho `JSESSIONID` để có thể thử cookie jar; **không triển khai properties lab như production security config**.

### 8.8. Chạy ứng dụng

```bash
./gradlew clean test bootRun
```

PowerShell:

```powershell
.\gradlew.bat clean test bootRun
```

Để đóng gói JAR:

```bash
./gradlew bootJar
java -jar build/libs/runtime-files-test-0.0.1-SNAPSHOT.jar
```

Đây là lệnh chạy được khi Gradle Wrapper từ Initializr tồn tại và project đã tạo theo cấu trúc ở trên. Không chạy riêng `javac FileController.java` vì nó cần Spring/Jakarta dependencies từ Gradle.

## 9. Kiểm thử với MockMvc: full Spring MVC context

`@SpringBootTest` mặc định dùng `webEnvironment=MOCK`, không start embedded HTTP server. `@AutoConfigureMockMvc` tạo `MockMvc` nối vào MVC context. Vì muốn test **cả static handler, multipart mapping, cookie endpoints và sessions**, chọn full context thay vì `@WebMvcTest` cho một controller.

Tạo `src/test/java/demo/WebRuntimeMockMvcTest.java`:

```java
package demo;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.Cookie;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.allOf;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class WebRuntimeMockMvcTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper json;

    @Test
    void uploadAndDownloadKeepExactBytes() throws Exception {
        byte[] expected = new byte[] {
                0, 1, 2, 10, 13, 65, (byte) 255
        };

        MockMultipartFile part = new MockMultipartFile(
                "file",
                "../untrusted.txt",
                "text/plain",
                expected
        );

        MvcResult upload = mvc.perform(
                multipart("/api/files").file(part))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").isNotEmpty())
            .andReturn();

        String id = json.readTree(
                upload.getResponse().getContentAsString())
                .get("id").asText();

        MvcResult download = mvc.perform(
                get("/api/files/{id}", id))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.CONTENT_DISPOSITION,
                    containsString("attachment")))
            .andExpect(header().string(
                    HttpHeaders.CONTENT_DISPOSITION,
                    containsString("download.bin")))
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, "no-store"))
            .andExpect(header().string(
                    "X-Content-Type-Options", "nosniff"))
            .andReturn();

        assertThat(download.getResponse()
                .getContentAsByteArray())
            .isEqualTo(expected);

        assertThat(download.getResponse()
                .getContentLength())
            .isEqualTo(expected.length);
    }

    @Test
    void rejectsEmptyAndExcessivelyLargeFile() throws Exception {
        MockMultipartFile empty =
                new MockMultipartFile("file", new byte[0]);

        mvc.perform(multipart("/api/files").file(empty))
            .andExpect(status().isBadRequest());

        MockMultipartFile tooLarge = new MockMultipartFile(
                "file", "big.bin", "application/octet-stream",
                new byte[64 * 1024 + 1]
        );

        mvc.perform(multipart("/api/files").file(tooLarge))
            .andExpect(status().is(413));
    }

    @Test
    void missingDownloadReturns404() throws Exception {
        mvc.perform(get(
                "/api/files/00000000-0000-0000-0000-000000000000"))
            .andExpect(status().isNotFound());
    }

    @Test
    void cookieHasExpectedAttributes() throws Exception {
        mvc.perform(post("/api/cookies/theme")
                .param("value", "dark")
                .secure(true))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.SET_COOKIE,
                allOf(
                    containsString("theme=dark"),
                    containsString("Path=/"),
                    containsString("HttpOnly"),
                    containsString("SameSite=Lax"),
                    containsString("Max-Age=600"),
                    containsString("Secure")
                )));

        mvc.perform(get("/api/cookies/theme")
                .cookie(new Cookie("theme", "dark")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.theme").value("dark"));

        mvc.perform(get("/api/cookies/theme"))
            .andExpect(jsonPath("$.theme").value("unset"));

        mvc.perform(post("/api/cookies/theme/clear")
                .secure(true))
            .andExpect(status().isNoContent())
            .andExpect(header().string(
                    HttpHeaders.SET_COOKIE,
                    allOf(
                        containsString("theme="),
                        containsString("Path=/"),
                        containsString("Max-Age=0")
                    )));
    }

    @Test
    void cookieRejectsUnexpectedValue() throws Exception {
        mvc.perform(post("/api/cookies/theme")
                .param("value", "malicious"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void sessionPersistsOnlyWhenExplicitlyReused()
            throws Exception {

        MvcResult first = mvc.perform(
                get("/api/session/visit"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.visits").value(1))
            .andReturn();

        MockHttpSession sameSession =
                (MockHttpSession) first.getRequest()
                        .getSession(false);

        assertThat(sameSession).isNotNull();

        mvc.perform(get("/api/session/visit")
                .session(sameSession))
            .andExpect(jsonPath("$.visits").value(2));

        // Request mới không truyền session cũ.
        mvc.perform(get("/api/session/visit"))
            .andExpect(jsonPath("$.visits").value(1));

        mvc.perform(post("/api/session/logout")
                .session(sameSession))
            .andExpect(status().isNoContent());

        assertThat(sameSession.isInvalid()).isTrue();
    }

    @Test
    void staticAssetIsPublicButPrivateResourceIsNot()
            throws Exception {

        mvc.perform(get("/assets/hello.txt"))
            .andExpect(status().isOk())
            .andExpect(content().string("asset-ok\n"));

        mvc.perform(get("/private-note.txt"))
            .andExpect(status().isNotFound());
    }
}
```

**Vì sao test này quan trọng?**

- Download test dùng bytes chứa `0x00` và `0xFF` để tránh “chỉ text thì đúng” nhưng binary đã hỏng; response binary được so sánh **chính xác**.
- Filename upload cố tình chứa `../`; server không dùng nó làm đường lưu hoặc download header. Đây không phải test toàn diện về path traversal/storage.
- 413 ở `MockMvc` đến từ guard ứng dụng; nó **không xác nhận** `spring.servlet.multipart.max-file-size` được Tomcat thực thi.
- Cookie test kiểm tra `Set-Cookie` attributes bằng matcher trên header; `secure(true)` mô phỏng HTTPS ở request để thử code `request.isSecure()`.
- `.cookie(new Cookie(...))` chỉ mô phỏng client đã gửi cookie, không có browser cookie jar thật.
- Session test dùng `MockHttpSession` cho request thứ hai và kiểm tra invalidation; request mới không mang session sẽ thấy counter khởi tạo lại.
- Static test chạy qua resource handler của application context đầy đủ, nhưng vẫn chưa kiểm tra JAR packaging/CDN.
- Test không đưa file vào filesystem, nên không cần cleanup thư mục upload.

**Lưu ý về imports:** `StandardCharsets` được import trong listing để tiện các biến thể test dùng UTF-8; Java cho phép unused imports ở compilation thông thường. Các assertions khác dùng AssertJ/Hamcrest/MockMvc từ `spring-boot-starter-test`.

### 9.1. Không nhầm HTTP status với mọi lỗi ở multipart

Test `MockMultipartFile` kích thước quá mức kiểm tra nhánh `FileStore` và kỳ vọng `413`. Trong live Tomcat, request có thể bị từ chối **trước khi controller chạy**, bởi multipart resolver/container. Nếu có custom `@ControllerAdvice`, status body có thể khác. Cần test độc lập với real multipart request vượt giới hạn; nếu mục tiêu là contract 413 chuẩn hóa, hãy implement exception handler và test nó ở live server.

### 9.2. Kiểm tra MIME/charset thế nào?

Đừng assert `Content-Type` bất kỳ nếu dự án không quy định rõ. Ví dụ static `hello.txt` thường nhận `text/plain`; charset parameter có thể khác theo container/config. Với download demo, method đặt `application/octet-stream` rõ ràng, nên có thể assert. Với JSON error response, Spring Boot 3.3 và problem details config ảnh hưởng body; không hardcode error JSON mặc định thành hợp đồng nghiệp vụ.

### 9.3. Kiểm tra Range bằng MockMvc có thể hữu ích, nhưng cần live test

Khi Spring MVC gặp `GET /api/files/{id}` trả `ResponseEntity<Resource>` status 200, nó có hỗ trợ `Range` theo các điều kiện được nêu trong tài liệu. Một assertion bổ sung có thể thử:

```java
mvc.perform(get("/api/files/{id}", id)
        .header(HttpHeaders.RANGE, "bytes=0-3"))
    .andExpect(status().isPartialContent())
    .andExpect(header().exists(
            HttpHeaders.CONTENT_RANGE));
```

Đây là **snippet bổ sung** cần một `id` đã upload ở test setup, không phải test method độc lập. Nếu nó thất bại, kiểm tra Resource type, status/headers, HTTP message converter và phiên bản Spring; không tự bỏ qua lỗi. Dù MockMvc trả 206 đúng, vẫn test live server khi chức năng resume/download lớn quan trọng.

## 10. Kiểm thử qua HTTP thật với RANDOM_PORT

Với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, Boot khởi động embedded Tomcat ở một port ngẫu nhiên. Java `HttpClient` tạo real TCP HTTP requests; `CookieManager` giúp giữ cookie giữa các request trong cùng test. Điều này khác MockMvc và rất hữu ích cho `JSESSIONID`, cookie headers, static resource packaging ở runtime và container behavior.

Tạo `src/test/java/demo/WebRuntimeHttpIntegrationTest.java`:

```java
package demo;

import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebRuntimeHttpIntegrationTest {

    @LocalServerPort
    int port;

    @Test
    void realCookieJarReusesServletSession()
            throws Exception {

        CookieManager cookies =
                new CookieManager(null, CookiePolicy.ACCEPT_ALL);

        HttpClient client = HttpClient.newBuilder()
                .cookieHandler(cookies)
                .build();

        URI uri = URI.create(
                "http://localhost:" + port + "/api/session/visit");

        HttpRequest request = HttpRequest.newBuilder(uri)
                .GET()
                .build();

        HttpResponse<String> first = client.send(
                request,
                HttpResponse.BodyHandlers.ofString());

        HttpResponse<String> second = client.send(
                request,
                HttpResponse.BodyHandlers.ofString());

        assertThat(first.statusCode()).isEqualTo(200);
        assertThat(second.statusCode()).isEqualTo(200);

        assertThat(first.body()).contains("\"visits\":1");
        assertThat(second.body()).contains("\"visits\":2");

        assertThat(cookies.getCookieStore().getCookies())
            .anySatisfy(cookie ->
                assertThat(cookie.getName())
                    .isEqualTo("JSESSIONID"));
    }

    @Test
    void staticAssetIsServedOverActualHttp()
            throws Exception {

        HttpClient client = HttpClient.newHttpClient();

        URI uri = URI.create(
                "http://localhost:" + port
                + "/assets/hello.txt");

        HttpRequest request = HttpRequest.newBuilder(uri)
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString());

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body()).isEqualTo("asset-ok\n");
    }
}
```

Đây là integration test với **container thật**, không có browser automation. CookieManager kiểm tra Java HTTP client nhận `JSESSIONID` và gửi lại để server cùng session tăng biến đếm. Nó không chứng minh Chrome/Safari có cùng chính sách third-party cookies, không thử TLS vì URL là localhost HTTP, và không kiểm tra multi-pod session persistence.

**Quan trọng về transactions:** trong `RANDOM_PORT`, HTTP server xử lý request ở thread/transaction khác test method. Một test `@Transactional` ở test thread không tự rollback thay đổi database thực hiện qua HTTP request. Khi test có repository thật, dùng fixtures, database độc lập và cleanup đáng tin.

### 10.1. Kiểm tra cookie của chính ứng dụng qua real client

Test ở trên dùng session cookie container. Muốn test `theme` riêng, có thể gửi POST `/api/cookies/theme?value=dark` qua cùng `HttpClient.CookieManager` rồi GET `/api/cookies/theme` và assert body trả `dark`. Dùng Java `HttpRequest.BodyPublishers.noBody()` và header/URI phù hợp; hoặc thử bằng curl theo mục 11. Đừng suy rằng `HttpOnly` làm Java HTTP client không gửi cookie: HttpOnly chủ yếu hạn chế truy cập từ JavaScript trong browser.

### 10.2. Gửi multipart thật từ integration test

`java.net.http.HttpClient` không có builder multipart ở mức tiện dụng như Spring Test; bạn phải tạo boundary và raw body đúng format, hoặc dùng một HTTP client multipart library phù hợp. Đối với bài học, `curl -F` là cách nhanh, đáng tin để xác minh container parser và limits. Không dùng `MockMultipartFile` để chứng minh Tomcat đã parse raw multipart boundary.

## 11. Thực hành curl với ứng dụng đang chạy

Sau khi chạy `./gradlew bootRun` hoặc JAR, dùng terminal khác.

### 11.1. Upload một file nhỏ

Tạo file local:

```bash
printf 'hello-file\n' > demo-upload.txt
```

Gửi multipart thật:

```bash
curl -i -F 'file=@demo-upload.txt;type=text/plain' \
  http://localhost:8080/api/files
```

Response tiêu biểu:

```http
HTTP/1.1 201
Content-Type: application/json

{"id":"<server-generated-uuid>"}
```

UUID là ngẫu nhiên, không cố định. `curl -F` tự tạo multipart boundary; không tự đặt `Content-Type: multipart/form-data` bằng một header trống boundary khi chưa xây request body.

### 11.2. Download và so sánh bytes

Thay ID thật:

```bash
curl -i \
  'http://localhost:8080/api/files/PUT-UUID-HERE'
```

Hoặc lưu bytes:

```bash
curl -sS -o downloaded.bin \
  'http://localhost:8080/api/files/PUT-UUID-HERE'
```

So sánh:

```bash
cmp demo-upload.txt downloaded.bin
```

`cmp` exit code 0 khi bytes bằng nhau trên Unix-like systems. Nếu Windows, dùng PowerShell `Get-FileHash` với SHA-256, hoặc Java/Python test có hàm hash. Không dựa vào text editor để xác nhận file binary không hỏng.

Header download dự kiến gồm `Content-Disposition: attachment; filename="download.bin"`, `Content-Type: application/octet-stream`, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` và Content-Length của file.

### 11.3. Upload vượt giới hạn thực

Tạo file hơn 64 KiB:

```bash
dd if=/dev/zero of=big-demo.bin bs=1024 count=65
```

Gửi:

```bash
curl -i -F 'file=@big-demo.bin' \
  http://localhost:8080/api/files
```

Ở đây **server multipart parser thật** có thể từ chối request trước `FileStore.save`. Quan sát status, error type, access/application logs và cleanup. Nếu contract yêu cầu nhất quán `413` cho mọi quá giới hạn, thêm global exception handler cho `MaxUploadSizeExceededException` và test live. Không tự khẳng định mọi Boot/container version trả một JSON lỗi y hệt nhau.

### 11.4. Thử cookie với curl jar

Trên môi trường Unix, tạo thư mục test riêng và file cookie jar tạm:

```bash
jar="$(mktemp)"
curl -sS -c "$jar" -b "$jar" -X POST \
  'http://localhost:8080/api/cookies/theme?value=dark'

curl -sS -c "$jar" -b "$jar" \
  'http://localhost:8080/api/cookies/theme'

rm -f "$jar"
```

Body thứ nhất được controller trả:

```json
{"theme":"dark"}
```

Body thứ hai kỳ vọng cũng là `{"theme":"dark"}` nếu cookie jar thực sự lưu/gửi cookie. Cookie file có thể chứa session IDs và thông tin nhạy cảm trong ứng dụng khác; **không commit vào Git, không dán nội dung jar lên chat/ticket**, xóa khi xong.

Với localhost HTTP, cookie theme được đặt `Secure` tùy `request.isSecure()` nên demo cho phép thử. **Production phải chạy HTTPS và Secure**, không bỏ Secure chỉ để browser gửi cookie trên HTTP công khai.

### 11.5. Thử HttpSession với cùng jar

```bash
jar="$(mktemp)"

curl -sS -c "$jar" -b "$jar" \
  http://localhost:8080/api/session/visit

curl -sS -c "$jar" -b "$jar" \
  http://localhost:8080/api/session/visit

rm -f "$jar"
```

Body kỳ vọng lần lượt:

```json
{"visits":1}
```

```json
{"visits":2}
```

Nếu gọi lần hai không có `-b "$jar"` hoặc dùng jar khác, thường là session khác và counter bắt đầu lại. Đây là hành vi **client giữ session identifier**, không phải dữ liệu count nằm trong cookie.

### 11.6. Static resource và cache

```bash
curl -i http://localhost:8080/assets/hello.txt
curl -i http://localhost:8080/
curl -i http://localhost:8080/private-note.txt
```

Kỳ vọng static asset và welcome page trả 200, private resource trả 404. Static asset có cache policy khoảng 60 giây theo properties. Thử `HEAD`:

```bash
curl -I http://localhost:8080/assets/hello.txt
```

`HEAD` không trả body trong giao thức HTTP dù headers có thể mô tả representation. Nếu muốn thử `304`, lấy Last-Modified từ GET response, gửi lại `If-Modified-Since` đúng format; không hardcode một timestamp tùy ý.

### 11.7. Thử Range bytes

```bash
curl -i -H 'Range: bytes=0-3' \
  http://localhost:8080/assets/hello.txt
```

Khi Spring resource handler xử lý Range theo HTTP, body phần tử 0..3 của `asset-ok\n` là `asse`, response thường `206 Partial Content` với `Content-Range: bytes 0-3/9`. Đây là behavior cần xác nhận thực trên server/container/proxy; nếu server trả `200` full response, xem đường handler, Range support, compression/edge và headers trước khi kết luận. Không trộn test range với một proxy tự chuyển đổi compressed content.

### 11.8. Cookie attrs bằng browser DevTools

Với HTTPS staging, mở DevTools → Application/Storage → Cookies để xem Domain, Path, Secure, HttpOnly, SameSite và expiry; Network tab xem `Set-Cookie`/`Cookie` trong requests. Browser có thể từ chối lưu cookie vì Secure/SameSite/Domain hoặc third-party policy ngay cả khi server đã gửi `Set-Cookie` đúng cú pháp. Đó là lý do cần E2E cho login/session flow.

## 12. @WebMvcTest, MockMvc và RANDOM_PORT chọn thế nào?

### 12.1. @WebMvcTest — slice, nhanh nhưng ít bean

`@WebMvcTest(FileController.class)` thường scan MVC controllers, filters, converters và selected MVC infrastructure, không tự scan mọi `@Service`/repository. Với demo `FileController` phụ thuộc `FileStore`, test slice cần mock/import dependency. Phù hợp để kiểm tra argument binding, status, validation/exception mapping và headers của một controller; không phù hợp làm bằng chứng toàn bộ static resource packaging, session store phân tán hoặc server multipart config.

Với Spring Boot 3.3, có thể dùng `@MockBean` hoặc `@Import` cho collaborators trong slice. Kiểm tra annotations đúng version; ví dụ Boot 3.3 khác Spring Boot 4.x về vị trí một số test packages.

### 12.2. @SpringBootTest(MOCK) + @AutoConfigureMockMvc

Đây là tầng mẫu `WebRuntimeMockMvcTest`: load full application context, nhưng Servlet objects được mock. Phù hợp test nhiều controllers, filters, static resource mappings và session attributes. Không start port.

### 12.3. @SpringBootTest(RANDOM_PORT)

`RANDOM_PORT` start web server thực. Client có thể dùng `TestRestTemplate`, Java `HttpClient` hoặc `WebTestClient` được cấu hình live. Phù hợp cookie persistence thật, HTTP headers, multipart parser, response status, embedded container, static packaging. Nhưng thường chậm hơn và phải cleanup DB/files/session state.

### 12.4. Browser/E2E với proxy/CDN

Nếu lỗi chỉ xuất hiện ở HTTPS/SameSite/third-party cookies, CDN 304, reverse proxy upload body limit hoặc file download browser UX, cần chạy qua **đường đi production-like**. `RANDOM_PORT` localhost không đại diện cho TLS termination, ingress headers, browser restrictions hoặc shared caches.

## 13. Security tests: upload và download

### 13.1. Object-level authorization

Trong demo, `GET /api/files/{id}` chưa xác thực. Với production, test cần chứng minh:

- User A upload file và nhận ID.
- User B không đọc được file của A (403 hoặc 404 theo policy, tránh enumeration).
- Anonymous user không upload/download khi không được phép.
- Admin được truy cập theo quyền cụ thể, có audit khi cần.
- ID không dự đoán được vẫn **không phải** authorization.
- Path traversal qua file name, URL encoding, percent-encoded slash và Unicode không dẫn tới file ngoài storage root.

Một test chỉ có status 200 cho user A là chưa đủ; phải có **negative permission tests**.

### 13.2. CSRF với browser session cookies

Nếu ứng dụng dùng Spring Security và session/cookie login, các POST upload, POST set-theme, POST logout có thể cần CSRF token. Spring Security test hỗ trợ:

```java
mvc.perform(multipart("/api/files")
        .file(sample)
        .with(csrf()))
    .andExpect(status().isCreated());
```

Đây là **snippet dành cho project có `spring-security-test`, Spring Security filter chain và `sample` đã được tạo**, không nằm trong demo chưa cài Security. Không copy đoạn này vào project chỉ có `spring-boot-starter-web` rồi tưởng nó compile. Khi CSRF bật, test còn phải kiểm tra thiếu/invalid token bị từ chối.

Với multipart, vị trí multipart parsing và CSRF filter có trade-offs: token ở header từ JavaScript client thường tiện hơn token nằm trong multipart body vì server có thể cần parse body để lấy CSRF. Xem hướng dẫn Spring Security về Multipart và CSRF.

### 13.3. Chống upload độc hại

Trên production:

1. Giới hạn part/file/request bytes tại edge và servlet container.
2. Giới hạn số files/parts và số upload đồng thời.
3. Dùng generated storage key, không trust filename/path.
4. Allowlist file types theo nghiệp vụ; nhận biết content signature, không chỉ extension.
5. Scan malware và cô lập vùng upload tạm; xử lý kết quả scan trước khi cho tải.
6. Không phục vụ file chưa kiểm soát dưới cùng origin có quyền truy cập cookies nhạy cảm nếu có nguy cơ active content.
7. Download qua attachment/nosniff và headers phù hợp.
8. Có authN/authZ, tenant isolation và quota.
9. Dọn orphaned files khi transaction hoặc scan fail.
10. Không log raw uploaded bytes, filename nhạy cảm hoặc auth headers.

Test phải bao gồm PDF giả, ZIP, SVG/HTML, file quá lớn, empty, filename chứa `../`, extension giả và MIME mismatch, nhưng dùng **fixtures vô hại** có kiểm soát.

### 13.4. Cache file riêng tư

`Cache-Control: no-store` làm rõ intention không lưu response file riêng tư trong cache. Nhưng CDN/proxy có custom policies có thể vẫn cần bypass rules; kiểm tra rằng file user A không bị cache trả cho user B. Với signed URLs, test expiry, signature validation, download after revocation và clock skew.

## 14. Cookie và session security tests

### 14.1. Session fixation

Khi login, Spring Security thường đổi session ID hoặc migrate session theo configured strategy để chống fixation. Test nên xác minh session mới sau authentication không tái sử dụng identifier do attacker đặt từ trước, đồng thời giữ đúng business state nếu cấu hình yêu cầu. Demo không có authentication, nên không tự tạo logic fixation.

### 14.2. Logout phải vô hiệu hóa phiên

Một logout đúng cần server invalidation/security context cleanup và cookie handling phù hợp. Test:

- Sau logout, cookie/session ID cũ không truy cập được endpoint cần authentication.
- Nếu gửi cookie cũ, server không phục hồi session authenticated.
- Browser không giữ credential có hiệu lực.
- Session repository phân tán xóa/expire đúng.
- CSRF token cũ không còn dùng được trong ngữ cảnh bảo mật mới.
- Đăng nhập lại tạo phiên hợp lệ theo chính sách.

Trong demo, `logout` chỉ `session.invalidate()` và trả 204, phù hợp kiểm thử Servlet session lifecycle, **không phải implementation xác thực production**.

### 14.3. HttpOnly, Secure, SameSite

| Test | Cách kiểm |
| --- | --- |
| Cookie `HttpOnly` | Assert trong Set-Cookie; kiểm tra browser `document.cookie` không đọc được |
| `Secure` | Assert khi HTTPS/secure request và thử browser HTTPS; proxy forwarded scheme đúng |
| `SameSite=Lax` | Header + browser navigation/cross-site behavior |
| `SameSite=None` | Test thêm Secure và CORS credentials/third-party policy |
| Cookie expiration | Test Max-Age và browser jar; không chỉ sleep trong unit test |
| Path/Domain | Test cookie chỉ gửi đúng scope |
| Session cookie rotation | Test login flow live cùng security |
| Cookie tampering | Test server không tin cookie user-controlled để cấp quyền |

Cookie của browser chịu cả chính sách client; HTTP client Java có thể chấp nhận cookie mà Safari/Chrome chặn. Vì vậy cross-site login flows cần browser E2E bên cạnh assertions ở server.

### 14.4. Session state và nhiều pods

Nếu session lưu trong memory của Tomcat trên Pod A, request tiếp theo qua Pod B không tự thấy `visits=2`. Sticky sessions có thể giảm sự cố ở một số mô hình, nhưng không giải quyết failover khi Pod A chết. Nếu cần session dùng chung, cấu hình Spring Session Redis/JDBC và test multi-replica, TTL, serialization, failover và invalidation.

### 14.5. Timeout tests không nên dùng Thread.sleep dài

MockHttpSession có thể điều chỉnh time/attributes trong test, nhưng nó không mô phỏng đầy đủ expiration bởi container thật. Với integration test, sử dụng timeout ngắn trên môi trường cô lập và clock/test hooks nếu được hỗ trợ; tránh tests `Thread.sleep(15*60*1000)` vì chậm và flaky. Test các boundaries (trước/sau expiry) và kết quả authentication.

## 15. Static resource caching, Range, security và packaging

### 15.1. Cache-Control và 304

`spring.web.resources.cache.period=60s` có thể tạo cache-control headers cho static assets, nhưng bản thân `max-age` không phải validator. Khi resource có `Last-Modified` và client gửi `If-Modified-Since` phù hợp, handler có thể trả 304. Nếu ETag được cấu hình bởi framework/Filter/CDN, `If-None-Match` có thể dùng ETag; **đừng giả định mọi static response đều có ETag mặc định**.

Test theo contract:

- GET asset trả 200, đúng bytes và content type.
- HEAD không có body.
- Cache-Control tương ứng policy.
- Nếu response có Last-Modified, conditional GET thích hợp cho 304 và empty body.
- Range nếu hỗ trợ: 206, Content-Range và đúng bytes.
- Asset missing: 404, không trả HTML lạ hoặc data private.
- Versioned asset URL: khi nội dung đổi, hash/version đổi; immutable cache chỉ đặt cho file versioned.

### 15.2. NGINX/CDN khác embedded resource handler

Một CDN có thể trả 304 từ cache mà request không đi tới Spring Boot; ingress có thể gzip/resize response; CDN còn có cache key gồm/không gồm query/cookie. Do đó test `MockMvc` không chứng minh CDN 304/206 và test local JAR cũng chưa chứng minh cache invalidation khi deploy nhiều replicas.

### 15.3. Resource locations và security boundary

Static locations mặc định là **tài nguyên công khai**. Không đặt `application.properties` chứa secret, private uploads, DB dumps hoặc source mapping nhạy cảm vào `static`. Spring Boot không tự phục vụ `classpath:/private/` qua `/**`, nhưng khi cấu hình thêm `spring.web.resources.static-locations=file:/...` hoặc custom `addResourceHandlers`, review root kỹ để không mở nhầm filesystem/private dirs.

Test traversal attempts với encoded paths và dot segments; cần test bằng live HTTP client vì mock request canonicalization và container normalization có thể khác. Đừng chỉ thử một chuỗi `../` rồi tuyên bố đã chặn mọi path traversal.

### 15.4. JAR packaging regression

Một dự án chạy từ IDE có thể tìm thấy `src/main/resources/static/assets/hello.txt`, nhưng khi build fat JAR cấu hình sai, resource có thể không nằm trong JAR. Tối thiểu chạy:

```bash
./gradlew bootJar
java -jar build/libs/runtime-files-test-0.0.1-SNAPSHOT.jar
curl -i http://localhost:8080/assets/hello.txt
```

Có thể kiểm tra JAR listing bằng `jar tf` trong local build, nhưng chỉ nhìn danh sách tệp không đủ xác minh route, Content-Type, caching hoặc static security.

## 16. Test negative cases và error diagnostics

| Tình huống | Test | Cần phân biệt |
| --- | --- | --- |
| Thiếu multipart field `file` | POST multipart với field khác | Binding error 400, không phải 500 |
| File rỗng | `MockMultipartFile("file",new byte[0])` | Contract từ chối 400 |
| File quá lớn ở app | MockMultipartFile 65 KiB | FileStore trả 413 |
| File quá lớn ở Tomcat | `curl -F` 65 KiB | Container reject trước controller |
| File download ID không có | GET random ID | 404; không lộ filesystem path |
| File download ID của user khác | Authenticated user B GET A file | 403/404 theo policy |
| Cookie sai giá trị | `value=malicious` | 400, không phản ánh header tùy ý |
| Cookie thiếu | GET readTheme không Cookie | `theme=unset` |
| Cookie bị sửa | Client gửi cookie ngoài allowlist | Server validate, không cấp quyền |
| Session không được reuse | MockMvc request mới không `session(...)` | Counter trở lại 1 |
| Session bị invalidate | POST logout + test invalid | Không phục hồi auth/session |
| Session timeout | Live short timeout/clock control | Không mặc định tương đương cookie expiry |
| Static asset không có | GET /assets/missing.txt | 404 |
| Tài nguyên private | GET /private-note.txt | 404 dù file nằm trong classpath |
| Static caching | GET + conditional GET | 304 chỉ khi validator phù hợp |
| Partial download | Range bytes valid/invalid | 206/416 theo hỗ trợ |
| Reverse proxy upload limit | Upload qua NGINX ingress | Có thể trả 413 từ proxy trước app |
| HTTPS cookie policy | Secure/SameSite/CORS | Browser thực có thể chặn dù MockMvc pass |

Một bug thuộc container không nên bị “sửa” bằng cách nới test `MockMvc`; cần kiểm tra boundary thật ở đúng tầng.

### 16.1. Diagnostic đầu tiên khi upload 400/413

1. Client có dùng `multipart/form-data` và boundary tự động không?
2. `@RequestParam("file")` có đúng field name không?
3. File rỗng, part name sai hay content encoding lỗi?
4. File size vượt `max-file-size` hay tổng vượt `max-request-size`?
5. NGINX có `client_max_body_size`/WAF limit riêng không?
6. Spring Security có trả 403 vì CSRF/auth trước controller không?
7. Client timeout/broken pipe khi upload lâu có được log phân loại an toàn không?
8. App có xử lý `MaxUploadSizeExceededException` thành response thống nhất không?
9. Storage quota/permissions/virus scan có gây 500 không?
10. Upload response có correlation ID để tìm log mà không in file content không?

### 16.2. Diagnostic khi session mỗi request đều bị reset

1. Browser/client có lưu Set-Cookie không?
2. Cookie có đúng Domain/Path? Có Secure trên HTTP? SameSite có chặn cross-site?
3. Client fetch có dùng credentials mode đúng? Server có CORS credentials và origin allowlist?
4. Cookie đã hết hạn/chính sách browser chặn third-party?
5. Session cookie name có bị thay hoặc nhiều services dùng trùng cookie name?
6. Có load balancer chuyển sang Pod có session store khác?
7. Session bị invalidate do logout, TTL, security hoặc app restart?
8. Reverse proxy có strip Set-Cookie/Cookie hoặc rewrite domain/path sai?
9. `MockMvc` test có truyền `MockHttpSession` rõ ràng không?
10. Có đang trộn session cookie với theme cookie/CSRF token không?

### 16.3. Diagnostic static 404

1. File có thực sự ở `src/main/resources/static`?
2. Build JAR đã đóng gói file chưa?
3. URL có chứa `/static/` sai không?
4. Có custom `spring.mvc.static-path-pattern` hoặc `spring.web.resources.static-locations`?
5. Có `@EnableWebMvc` làm mất một số auto-configuration của Boot?
6. Controller/forward/security routing có chặn `/assets/**` không?
7. Frontend base path/context path/ingress rewrite có đúng không?
8. Static/CDN cache 404 cũ có bị giữ lại không?
9. Path case-sensitive khác nhau giữa OS?
10. Tệp thuộc private resource location hay webapp directory bị bỏ khi build JAR?

## 17. Kết hợp Spring Security trong test

Demo không cài Security, nhưng trong sản phẩm thật, bật Security thay đổi kết quả:

- `@WebMvcTest` có thể tự mang security filters, dẫn tới 401/403 nếu không cấu hình test principal.
- Spring Security test hỗ trợ `@WithMockUser`, `user(...)`, `csrf()` và request post-processors.
- Multipart POST và logout POST dưới cookie auth có thể cần CSRF.
- HTTP GET file riêng phải kiểm tra object ownership/tenant, không chỉ `authenticated()` trên URL.
- Static CSS/JS public có thể `permitAll`, nhưng chỉ assets cần public; không dùng `web.ignoring()` tùy tiện để vượt qua toàn bộ security filters.
- Session fixation/migration trên login nên được test ở security integration layer.
- Session repository/CSRF cookie policies có thể làm live flow khác MockMvc.
- Nếu dùng OAuth2 bearer token stateless, không cần kỳ vọng JSESSIONID như login cookie-session thông thường.

**Không dùng `@AutoConfigureMockMvc(addFilters=false)` chỉ để khiến test xanh** nếu mục tiêu là xác minh authentication/CSRF behavior. Chỉ tắt filters khi test cố ý tách biệt controller và security đã được test ở nơi khác.

## 18. WebFlux và reactive file transfer khác MVC

Spring WebFlux dùng `WebTestClient`, `ServerWebExchange` và reactive `Flux<DataBuffer>`. Nó không dùng `MockMvc`/`MultipartFile` semantics y hệt Spring MVC.

- Upload reactive có `FilePart` và `transferTo`; test qua `WebTestClient` hoặc HTTP client.
- Download reactive có `Resource` hoặc streaming body với backpressure.
- File buffer ownership/retain/release khác Servlet; không join toàn bộ file lớn vào memory chỉ để test/log.
- Cookies và sessions trong WebFlux dùng `WebSession`, không phải `jakarta.servlet.http.HttpSession`.
- Static resources và cache vẫn cần kiểm tra runtime/packaging/CDN, nhưng handler classes khác MVC.

Không thêm `spring-boot-starter-webflux` chỉ để “dùng WebTestClient” rồi nghĩ application đã chuyển sang non-blocking. Khi cả MVC/WebFlux starters có mặt, Spring Boot có quy tắc quyết định web application type; xác định stack trước khi chọn test APIs.

## 19. CI và dữ liệu test

### 19.1. Test không nên phụ thuộc máy cá nhân

- Dùng files fixtures nhỏ, synthetic, không chứa dữ liệu khách hàng.
- Không dựa vào `C:\Users\...` hoặc `/home/me/Downloads`.
- Không dùng hardcoded TCP port cho integration tests; dùng `RANDOM_PORT`.
- Dùng tên file/generated IDs, không giả định thứ tự requests trong parallel tests.
- Xóa temporary files/cookie jars sau khi chạy.
- Nếu dùng storage thực, tạo test container/object bucket tách biệt và cleanup.
- Không commit session cookies, access tokens hoặc HTTP captures có PII.
- Ghi checksum expected cho binary fixture quan trọng.
- Định nghĩa contract rõ về 400/403/404/413/206/304 và test qua đúng tầng.

### 19.2. Tránh test flaky về thời gian/cookie

Đừng `Thread.sleep(15*60*1000)` để đợi session timeout; dùng timeout ngắn/clock hooks được hỗ trợ ở môi trường kiểm thử. Với `Last-Modified`, độ chính xác giây có thể gây test 304 thất thường nếu resource được tạo/đổi trong cùng giây. Không assert chính xác từng byte trong `Set-Cookie` khi thứ tự attributes do container khác nhau; kiểm tra thuộc tính cần thiết và browser behavior.

### 19.3. CI chạy hai nhóm tests

- **Fast tests:** controller binding, guards, bytes, `MockHttpSession` và static handler qua `MockMvc`.
- **Live server tests:** cookie jar, multipart parser, session cookie, resource HTTP, Range/conditional, real status/headers.
- **Deployment smoke tests:** `bootJar`, ingress/CDN cache, HTTPS cookie policy, private file permissions, large uploads và multi-pod session store.

Không cần chạy tất cả browser E2E trên mọi commit nếu chi phí lớn, nhưng phải có regression suite cho các hợp đồng sống còn.

## 20. Câu hỏi tự kiểm tra

**1.** `MockMvc.multipart()` pass có chứng minh Tomcat đọc multipart boundary đúng không?  
**Đáp án:** Không. MockMvc tạo `MockMultipartHttpServletRequest`, bỏ qua parser request thật. Cần live HTTP multipart test.

**2.** Vì sao phải so sánh `getContentAsByteArray()` thay vì `getContentAsString()` cho ZIP?  
**Đáp án:** Binary data có bytes không phải UTF-8; chuyển String có thể sai content.

**3.** `Content-Disposition: attachment` và Content-Type có chức năng gì?  
**Đáp án:** Attachment gợi ý tải xuống; Content-Type cho biết representation type. Cần filename an toàn và nosniff khi phục vụ user uploads.

**4.** Cookie `HttpOnly` có khiến browser không gửi nó cùng HTTP request không?  
**Đáp án:** Không. HttpOnly chủ yếu chặn JavaScript đọc qua document.cookie; browser vẫn gửi nếu scope/policy cho phép.

**5.** `Secure` cookie có thích hợp trên HTTP production không?  
**Đáp án:** Production dùng HTTPS + Secure; trên HTTP thường không được gửi/lưu theo browser policy.

**6.** `MockMvc` có tự nhận JSESSIONID từ response và đính kèm ở request sau không?  
**Đáp án:** Không. Dùng `MockHttpSession` trong test hoặc cookie-aware HTTP client live.

**7.** Thấy Set-Cookie nghĩa là browser chắc chắn lưu cookie?  
**Đáp án:** Không. Domain/Path/Secure/SameSite/third-party policy có thể làm client từ chối.

**8.** Sau `session.invalidate()` browser có thể vẫn gửi cookie JSESSIONID cũ không?  
**Đáp án:** Có. Server phải coi session cũ là invalid; để xóa browser cookie cần xử lý cookie scope đúng.

**9.** `src/main/resources/private/secret.txt` có được Boot static handler tự phục vụ không?  
**Đáp án:** Không theo default static locations; chỉ các thư mục configured static public được expose. Nhưng custom configs có thể làm thay đổi.

**10.** Tại sao tài nguyên static ở `src/main/webapp` có thể không nằm trong executable JAR?  
**Đáp án:** Boot docs cảnh báo đường đó phù hợp WAR hơn, có thể bị build tool bỏ trong JAR.

**11.** `Cache-Control: max-age=60` đồng nghĩa mọi request sẽ nhận 304?  
**Đáp án:** Không. 304 cần conditional request và validator Last-Modified/ETag phù hợp.

**12.** Vì sao byte Range test cần 206 và Content-Range?  
**Đáp án:** Để xác minh server trả đúng một phần representation, không toàn file hoặc dữ liệu sai.

**13.** HTTP session memory ở Pod A có tự có ở Pod B không?  
**Đáp án:** Không. Cần session store phân tán như Spring Session và test failover.

**14.** File ID UUID khó đoán có thay authorization khi download không?  
**Đáp án:** Không. Phải kiểm tra owner/tenant/resource permissions.

**15.** Vì sao MockMvc upload 65 KiB trả 413 vẫn chưa chứng minh property `spring.servlet.multipart.max-file-size=64KB`?  
**Đáp án:** Đó là guard ở FileStore; parser Tomcat không chạy trong MockMvc.

**16.** Khi login bằng cookie-session, upload POST có cần CSRF test?  
**Đáp án:** Thường có theo Spring Security policy, trừ khi mô hình đã được thiết kế stateless hoặc có ngoại lệ an toàn.

## 21. Checklist thực hiện

- [ ] Test upload đúng multipart field name, bytes, status và response ID.
- [ ] Test file rỗng, oversized, malformed multipart và content type giả.
- [ ] Kiểm tra container limit riêng bằng HTTP thật; không chỉ MockMultipartFile.
- [ ] Không dùng original filename làm filesystem path/storage key.
- [ ] Download test byte exact, Content-Disposition, Content-Type, Content-Length, Cache-Control và nosniff.
- [ ] File không tồn tại/không đủ quyền trả 404/403 đúng contract.
- [ ] Range 206/416 và conditional requests được test khi sản phẩm hỗ trợ.
- [ ] Set-Cookie có Path/Domain/HttpOnly/Secure/SameSite/Max-Age phù hợp.
- [ ] Cookie jar/browser gửi lại đúng cookie; MockMvc được cung cấp Cookie thủ công.
- [ ] Session reuse dùng MockHttpSession; live test JSESSIONID bằng cookie-aware client.
- [ ] Session invalidation, timeout, fixation và multi-pod repository được kiểm tra theo threat model.
- [ ] Static files nằm ở đúng classpath public locations và trong JAR build.
- [ ] Private file paths không được serve, kể cả qua custom static mappings.
- [ ] Cache-Control/Last-Modified/ETag và CDN invalidation có chính sách đúng.
- [ ] Spring Security/CSRF/ownership được test, không tắt filters bừa bãi.
- [ ] E2E HTTPS browser kiểm tra Secure/SameSite/CORS khi có cross-site flow.
- [ ] Tests không dùng dữ liệu khách hàng, không log cookie/session/file content.
- [ ] Cleanup temporary files, cookie jars và test repository data.
- [ ] CI có MockMvc tests, RANDOM_PORT tests và smoke qua deployment path.
- [ ] Phân biệt lỗi controller, multipart parser, reverse proxy, browser và session store.

## Tài liệu tham khảo chính thức

1. [Spring Boot 3.3 — Servlet Web Applications, Static Content](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
2. [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
3. [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
4. [Spring Framework 6.1 — MockMvc](https://docs.spring.io/spring-framework/reference/6.1/testing/mockmvc.html)
5. [Spring Framework 6.1 — MockMvc vs End-to-End Tests](https://docs.spring.io/spring-framework/reference/6.1/testing/mockmvc/vs-end-to-end-integration-tests.html)
6. [Spring Framework — MockMultipartFile Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/mock/web/MockMultipartFile.html)
7. [Spring Framework — MockHttpSession Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/mock/web/MockHttpSession.html)
8. [Spring Framework — Static Resources](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-config/static-resources.html)
9. [Spring Framework — Range Requests](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-range.html)
10. [Spring Framework — ResponseEntity and Resource](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-controller/ann-methods/responseentity.html)
11. [Spring Guide — Uploading Files](https://spring.io/guides/gs/uploading-files/)
12. [Spring Security — Testing CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
13. [Spring Security — CSRF and Multipart](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
14. [MDN — HTTP Cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies)
15. [MDN — HTTP Range Requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Range_requests)
16. [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)

**Kết luận:** kiểm thử web runtime không dừng ở việc assert controller trả 200. **Upload** đòi đúng multipart field/bytes và parser/size limits, **download** đòi bytes/headers/authorization, **cookie** đòi scope/flags và client thực sự lưu/gửi lại, **HttpSession** đòi lifecycle/identifier/store, còn **static resources** đòi classpath packaging, handler, cache và không lộ tài nguyên private. Sử dụng **MockMvc cho MVC contract** và **RANDOM_PORT/browser/edge tests cho hành vi container & client thực** sẽ tránh nhiều kết luận sai và giữ ứng dụng an toàn khi triển khai.
