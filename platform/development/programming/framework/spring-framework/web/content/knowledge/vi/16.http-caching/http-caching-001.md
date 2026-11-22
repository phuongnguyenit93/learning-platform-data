# Cache-Control, Expires và cache trình duyệt so với cache dùng chung trong Spring MVC

## 1. Vì sao HTTP cache quan trọng?

Một client gọi `GET /api/products` và nhận JSON 100 KB. Nếu mỗi lần người dùng mở lại trang đều phải tải toàn bộ từ origin server, mạng và backend sẽ phải làm thêm việc. **HTTP caching** cho phép tái sử dụng một HTTP response khi còn hợp lệ, hoặc **revalidate** với server để tránh chuyển lại body không đổi.

Tuy nhiên không phải mọi dữ liệu đều phù hợp cache dùng chung. Nếu response của `GET /api/me` chứa tên, email hoặc số dư và bị CDN/proxy phục vụ cho người dùng khác, lỗi cache có thể trở thành lỗ hổng rò rỉ dữ liệu. Vì vậy, hiểu `Cache-Control` và `Expires` là một phần của **thiết kế giao thức HTTP và bảo mật**, không chỉ là mẹo tăng tốc.

Sau bài này, bạn có thể:

1. Phân biệt **private cache** (thường là browser) và **shared cache** (reverse proxy, CDN, forward proxy).
2. Giải thích khả năng **lưu (store)**, thời hạn **freshness** và điều kiện **revalidation** là ba quyết định riêng.
3. Dùng đúng `max-age`, `s-maxage`, `private`, `public`, `no-cache`, `no-store`, `must-revalidate`, `immutable` và `Expires`.
4. Biết vì sao request có `Authorization`, response có `Set-Cookie` hoặc dùng session cần xem xét cache policy chặt chẽ.
5. Thiết kế caching cho tài nguyên công khai, HTML động, API cá nhân hóa và dữ liệu nhạy cảm.
6. Dùng `org.springframework.http.CacheControl`, `ResponseEntity`, `ETag` và Spring static resource handling.
7. Viết contract tests bằng MockMvc, quan sát headers bằng curl và tránh rủi ro cache leakage.

**Phạm vi:** Spring Web MVC (Servlet stack), **Java 17, Spring Boot 3.3.5 / Spring Framework 6.1.x**, HTTP caching theo **RFC 9111 (HTTP Caching)** và các điều kiện request theo RFC 9110. Bài không thay thế chính sách của một CDN cụ thể, cũng không phải Spring `@Cacheable` dùng cho caching kết quả method trong JVM/Redis.

## 2. HTTP cache nằm ở đâu?

```text
┌──────────────────┐
│ Browser người A  │
│ private HTTP     │
│ cache            │
└────────┬─────────┘
         │ HTTP request
         ▼
┌──────────────────┐
│ Shared cache /   │
│ CDN / proxy      │
│ (nhiều clients)  │
└────────┬─────────┘
         │ có thể chuyển tới origin
         ▼
┌──────────────────┐
│ Spring MVC       │
│ origin server    │
└──────────────────┘
         ▲
         │
┌────────┴─────────┐
│ Browser người B  │
│ private cache    │
└──────────────────┘
```

Sơ đồ mang tính khái niệm, không phải topology bắt buộc. Có hệ thống có nhiều CDN/proxies, có hệ thống không có shared cache.

### 2.1. Private cache

Một **private cache** gắn với một user/client, điển hình là browser HTTP cache. Một response có dữ liệu cá nhân **có thể được cache ở browser của người đó** nếu policy cho phép và có lợi, nhưng không nên xuất hiện trong shared cache.

Ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, max-age=60

{"displayName":"Lan"}
```

Nghĩa cơ bản:

- `private`: **shared cache không được lưu response** (ở dạng directive unqualified).
- `max-age=60`: trong điều kiện bình thường, một private cache có thể coi response là fresh tối đa 60 giây, xét thêm Age/Date và quy tắc tính tuổi.
- Không có nghĩa dữ liệu được mã hóa hay chỉ user đúng mới xem được. Browser history, disk, local access, session hay cách browser cô lập cache vẫn cần xem xét.
- Nếu dữ liệu nhạy cảm không được lưu trên thiết bị, dùng `no-store` thay vì `private`.

### 2.2. Shared cache

**Shared cache** dùng lại response cho nhiều clients. CDN ở trước origin là ví dụ phổ biến. Khi nhận dữ liệu công khai đúng policy, một CDN có thể trả body ngay mà không gọi Spring MVC ở mỗi request.

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=120, s-maxage=600

{"siteName":"Java Learning","theme":"light"}
```

- Browser có thể coi response fresh khoảng **120 giây**.
- Shared cache có thể coi response fresh khoảng **600 giây** nhờ `s-maxage` (nếu các điều kiện lưu/tái sử dụng khác cũng thỏa).
- `public` cho phép shared cache lưu những response mà bình thường có thể bị hạn chế, kể cả response cho request có `Authorization`; vì vậy chỉ dùng khi chắc chắn representation an toàn để chia sẻ.
- Directive không đảm bảo một CDN sẽ thật sự lưu: CDN có thể không bật caching, bị giới hạn dung lượng hoặc có policy riêng.

### 2.3. Cache dùng chung không đồng nghĩa database cache

HTTP cache lưu/reuse **HTTP responses** theo URL, method, selected request headers, response headers và quy tắc HTTP.

Spring `@Cacheable` thường cache **kết quả method** trong application/Redis/Ehcache. Nó không tự tạo `Cache-Control`, không tự tuân thủ `Vary`, `Authorization` hay trả HTTP `304`. Ngược lại, thêm `Cache-Control` không làm `@Cacheable` tự hoạt động. Hai lớp có thể bổ trợ nhau nhưng phải thiết kế độc lập.

## 3. Ba câu hỏi mà cache phải trả lời

Một cache không thể chỉ thấy `200 OK` rồi quyết định lưu vĩnh viễn. Nó phải trả lời:

1. **Có được lưu response không?** Phụ thuộc method, status, `Cache-Control`, `Authorization`, private/shared restrictions và các quy tắc RFC.
2. **Nếu đã lưu, còn fresh không?** Phụ thuộc `max-age`, `s-maxage`, `Expires`, `Date`, `Age` và thời gian đã trôi qua; có thể có heuristic freshness khi thiếu explicit policy.
3. **Nếu stale, có được tái sử dụng không?** Có thể revalidate thành công bằng `ETag`/`Last-Modified`, hoặc trong một số trường hợp được phép phục vụ stale. `no-cache`/`must-revalidate` đặt điều kiện chặt chẽ.

```text
Client GET /public/config
         |
         v
   Cache có entry?
      /       \
    Không      Có
     |          |
     v          v
  Forward    Entry còn fresh?
  origin        /       \
             Có         Không
              |            |
              v            v
           Reuse       Validate with origin?
           body         /             \
                     304              200 changed
                      |                  |
                      v                  v
                 Reuse stored      Store new response
                 representation    if permitted
```

Đây là flow đơn giản hóa. Cache có thể bỏ qua entry, không lưu, bị evict hoặc cần tuân theo `Vary`, `Authorization`, cache directives bổ sung. HTTP `304 Not Modified` **không phải body JSON mới**; nó cập nhật một số metadata/validators của cached response và giúp tái sử dụng representation đã có.

## 4. Các Cache-Control directives cốt lõi

`Cache-Control` xuất hiện được ở **request** và **response**; ý nghĩa tùy vị trí. Phần sau chủ yếu nói về **response Cache-Control**, vì Spring MVC controller quản lý chính sách dữ liệu nó trả về.

| Response directive | Ý nghĩa chính | Ghi nhớ |
| --- | --- | --- |
| `max-age=N` | Freshness lifetime N giây đối với cache chịu tác động | Không phải “chỉ lưu N giây rồi xóa”; stale entry có thể còn để revalidate |
| `s-maxage=N` | Freshness dành cho **shared cache**, ưu tiên hơn `max-age` và `Expires` | Browser/private cache bỏ qua s-maxage |
| `public` | Cho phép shared caching trong những trường hợp mà bình thường bị hạn chế | Cực kỳ thận trọng với response cá nhân hóa/authenticated |
| `private` | Không cho **shared cache** lưu response, vẫn có thể cho private cache lưu | Không tương đương no-store |
| `no-cache` | Có thể lưu nhưng **phải validate trước mỗi lần reuse** | Không mang nghĩa “không cache” |
| `no-store` | Cache không được lưu request/response theo directive | Dùng cho dữ liệu bí mật, nhưng không bảo đảm xóa cache cũ |
| `must-revalidate` | Khi entry đã stale, không được reuse trước khi validate thành công | Không mang nghĩa “bắt buộc revalidate mọi lần” khi vẫn fresh |
| `proxy-revalidate` | Ý tưởng như must-revalidate nhưng cho shared caches | Cần có policy lưu/freshness khác |
| `no-transform` | Intermediary không được biến đổi response content | Có ích với bytes nhạy format, media |
| `immutable` | Representation dự kiến không đổi trong freshness lifetime | Dùng với hashed/versioned assets, không phải dữ liệu động |
| `stale-while-revalidate=N` | Cho phép dùng stale trong thời gian ngắn khi revalidate bất đồng bộ | Cache phải hỗ trợ; không dùng cho dữ liệu cần tuyệt đối mới |
| `stale-if-error=N` | Cho phép serve stale trong một khoảng khi gặp lỗi cụ thể | Không phù hợp vô điều kiện cho dữ liệu/giá nhạy cập nhật |

### 4.1. no-cache khác no-store

Hai response:

```http
Cache-Control: no-cache
```

và

```http
Cache-Control: no-store
```

**không tương đương**.

- `no-cache` **cho phép lưu** response, nhưng trước **mỗi lần tái sử dụng**, cache phải validate với origin (thường qua conditional request và `304`). Nó tiết kiệm body transfer nếu response không đổi.
- `no-store` yêu cầu cache **không lưu** response theo RFC; giảm nguy cơ dữ liệu nhạy cảm tồn tại ở browser/proxy. Nhưng không thể xóa một bản đã lưu trước đó chỉ bằng cách gửi header mới, vì cache cũ có thể không hỏi origin.
- Dùng `private, no-cache` cho nội dung cá nhân có thể lưu tạm trong browser nhưng mỗi lần dùng lại cần revalidation.
- Dùng `no-store` khi không muốn cache nào giữ dữ liệu, ví dụ response chứa access token, secret reset link, báo cáo nhạy cảm hoặc thông tin tài chính cần hạn chế lưu.

**Lưu ý bảo mật:** HTTP caching directives không thay TLS, authentication, authorization, encryption at rest hay cache eviction thật ở mọi môi trường. Một cache sai chuẩn hoặc độc hại có thể không tuân thủ.

### 4.2. max-age khác thời gian tồn tại tuyệt đối

`Cache-Control: max-age=120` không có nghĩa “cứ đúng 120 giây tính từ khi browser bấm GET thì xóa response”. Nó cho biết thời gian freshness tối đa của response, đo theo **tuổi hiện tại (current age)**. Một shared cache có thể đã giữ response 30 giây rồi mới gửi xuống browser; header `Age: 30` gợi ý rằng browser chỉ còn khoảng 90 giây freshness nếu không có chi tiết khác.

Tính toán đầy đủ trong RFC xét `Date`, `Age`, apparent age, response delay và thời gian cư trú. Với bài cơ bản, ghi nhớ: **Age tiêu thụ một phần max-age**; không cộng thêm nguyên N giây cho mọi tầng cache.

### 4.3. s-maxage khác max-age

```http
Cache-Control: public, max-age=60, s-maxage=300
```

Với response công khai đủ điều kiện lưu, browser/private cache dùng tối đa **60s**, shared cache dùng tối đa **300s** làm freshness lifetime. `s-maxage` còn mang semantics shared-cache revalidation khi stale. Không suy luận rằng sau 60s browser sẽ luôn nhận dữ liệu mới từ origin: browser có thể phải hỏi CDN, và CDN vẫn có thể cung cấp response đang fresh của mình.

Nếu muốn cập nhật rất nhanh với user nhưng giảm origin requests, phải thiết kế CDN cache lifetime và invalidation phù hợp, vì s-maxage dài có thể trì hoãn việc nhìn thấy nội dung mới.

### 4.4. public và private không phải biểu thị quyền truy cập

`public` nghĩa response **có thể được lưu ở shared caches** theo HTTP, chứ không có nghĩa bất kỳ user nào được phép đọc API. `private` nghĩa không được lưu ở shared cache, **không bảo đảm** ACL/authentication trên server. Một API private vẫn phải kiểm tra user/tenant cho từng request đến origin.

Điều nguy hiểm là thêm `public`/`s-maxage` vào API có Authorization để “tăng hit rate” mà không chứng minh dữ liệu chỉ là public representation. Chỉ định `public` một cách vô tình có thể làm shared caches tái sử dụng response authenticated cho user khác theo quy tắc RFC.

## 5. Expires: thời điểm hết fresh theo đồng hồ

`Expires` là HTTP response header chứa một **HTTP-date** tuyệt đối:

```http
Date: Wed, 21 Oct 2026 10:00:00 GMT
Expires: Wed, 21 Oct 2026 10:02:00 GMT
```

Nếu không có cache directives có mức ưu tiên cao hơn, ví dụ này khai báo thời gian fresh khoảng 120 giây kể từ `Date`. `Expires` là **thời điểm GMT**, không phải số giây. `Expires: 120` không hợp lệ theo chuẩn.

So sánh:

```http
Cache-Control: max-age=120
```

và

```http
Expires: Wed, 21 Oct 2026 10:02:00 GMT
```

- `max-age` biểu diễn duration, tránh nhiều rủi ro từ đồng hồ origin/client không đồng bộ.
- `Expires` là absolute date, dễ bị hiểu sai nếu `Date` không chính xác hoặc server/CDN xử lý time không đúng.
- Có thể gửi cả hai để tương thích các client cũ, nhưng **`Cache-Control: max-age` có độ ưu tiên cao hơn `Expires`**.
- Trong shared cache, `s-maxage` cũng override `Expires` và `max-age` dành cho shared freshness.
- Expires đã ở quá khứ biểu diễn response đã hết fresh; không nhất thiết cấm lưu (khác `no-store`).
- Không lấy time từ client để quyết định server data validity; HTTP-date là metadata giao thức.

### 5.1. Quy tắc ưu tiên thường dùng

Với response:

```http
Cache-Control: public, max-age=60, s-maxage=300
Expires: Thu, 22 Oct 2026 10:00:00 GMT
```

- Shared cache theo `s-maxage=300`.
- Private cache/browser theo `max-age=60`.
- `Expires` bị bỏ qua khi các cache lifetime tương ứng được chỉ định.

Đây là **mô hình ưu tiên**. Cache storage/reuse vẫn chịu các điều kiện khác của RFC 9111, ví dụ method/status, authorization, `Vary` và nội dung directives.

### 5.2. Expires không nói response phải được lưu

`Expires` hoặc `max-age` chủ yếu kiểm soát freshness nếu response **đủ điều kiện được lưu**. Có `Expires` tương lai không cho phép bypass `Cache-Control: no-store` hoặc `private` của shared cache. Bước “có được store?” đến trước bước “fresh được bao lâu?”.

## 6. Browser cache, CDN, proxy: ví dụ hành vi thực tế

Giả sử browser A gọi `GET /assets/app.81d31a.js` và CDN trả:

```http
HTTP/1.1 200 OK
Content-Type: text/javascript
Cache-Control: public, max-age=31536000, immutable
ETag: "sha256-81d31a"
```

Vì URL chứa content hash, cùng URL nên luôn có cùng content. Browser và shared cache có thể giữ response lâu (nếu capacity/policy cho phép), giảm băng thông. Khi deploy version mới, HTML tham chiếu **URL mới**; không overwrite bytes ở URL hashed cũ.

Ngược lại:

```http
GET /dashboard
Cookie: SESSION=...
```

Response dashboard cá nhân có thể:

```http
HTTP/1.1 200 OK
Cache-Control: private, no-cache
ETag: "account-42-v7"
Vary: Accept-Language

[HTML dành cho tài khoản đã đăng nhập]
```

Browser có thể giữ một bản và revalidate, shared cache không được lưu. Nếu dashboard hiển thị secrets nhạy cảm, cân nhắc `no-store`.

### Bảng chọn policy theo tình huống

| Nội dung | Policy minh họa | Ghi chú |
| --- | --- | --- |
| JS/CSS có fingerprint trong URL | `public, max-age=31536000, immutable` | Chỉ khi bytes thực sự bất biến với cùng URL |
| Thông báo công khai cập nhật theo giờ | `public, max-age=60, s-maxage=300` | CDN có thể chậm cập nhật tối đa theo policy nếu không purge |
| HTML shell thay đổi mỗi deploy | `no-cache` | Cho phép giữ rồi validate trước reuse |
| API thông tin tài khoản thông thường | `private, no-cache` | Browser có thể lưu; revalidate mỗi lần |
| API báo cáo riêng được phép stale 30s | `private, max-age=30` | Chỉ khi nghiệp vụ chấp nhận 30s cũ |
| API chứa token/credentials/bí mật | `no-store` | Không phụ thuộc vào private cache an toàn tuyệt đối |
| Tài nguyên public có ETag | `public, max-age=120` + ETag | Khi stale có thể trả 304 |
| Trang login/error có nội dung cá nhân | `no-store` hoặc `private, no-cache` tùy độ nhạy | Cần xét session, bfcache và security |
| GET giá/số lượng tồn kho thay đổi nhanh | `no-cache` hoặc freshness rất ngắn | Không lấy cache làm nguồn sự thật cho checkout |
| Tài liệu public có phiên bản rõ | `public, max-age=600` | Đổi URL hoặc purge khi publish lại |

Policy chỉ là **ví dụ thiết kế**, không có một giá trị phù hợp cho mọi API.

## 7. Authorization và Set-Cookie: vùng rủi ro của shared cache

### 7.1. Authorization header

RFC 9111 mặc định hạn chế **shared cache** tái sử dụng response của request có header `Authorization`. Tuy nhiên một số directives **cho phép** shared caching trong điều kiện cụ thể:

- `public`;
- `s-maxage`;
- `must-revalidate` (theo các quy tắc riêng, không có nghĩa luôn fresh hay mặc định cacheable).

**Vì vậy không nói “cứ có Authorization thì CDN tuyệt đối không cache”.** Nếu controller hoặc gateway thêm `Cache-Control: public`, dữ liệu authenticated có thể trở thành shared-cacheable khi các điều kiện khác thỏa. Cần review chính sách từng endpoint.

Ví dụ nguy hiểm:

```http
GET /api/me HTTP/1.1
Authorization: Bearer user-A-token

HTTP/1.1 200 OK
Cache-Control: public, s-maxage=600

{"email":"user-a@example.com"}
```

Đây là **phản ví dụ rủi ro**, không phải policy đề xuất. Nếu shared cache key không tách an toàn theo người dùng hoặc cấu hình bypass, thông tin cá nhân có thể đến sai client.

### 7.2. Cookie/Set-Cookie không tự khóa cache

Một request chứa `Cookie` hoặc response chứa `Set-Cookie` **không tự động có nghĩa mọi shared cache đều bị HTTP cấm lưu**. Nhiều CDN có quy tắc riêng như bypass khi cookie hoặc không cache response Set-Cookie, nhưng đây là **cấu hình sản phẩm/CDN**, không thay cho `Cache-Control`.

Với content cá nhân hóa theo session cookie:

```http
Cache-Control: private, no-cache
```

hoặc nếu nhạy cảm:

```http
Cache-Control: no-store
```

phải được thiết lập **tường minh** và kiểm thử qua đường CDN/ingress thật. Không dùng `Vary: Cookie` như “bùa hộ mệnh” thay `private`: Vary có thể tạo số lượng biến thể lớn, rủi ro cấu hình và cache keys. Đối với API riêng tư, shared cache nên bị chặn theo policy thay vì cố cache mỗi cookie session.

### 7.3. Giới hạn của cache isolation

Ngay cả `private` hoặc `no-store` cũng không thay authn/authz, TLS và kiểm soát local browser. Một hệ thống dùng máy tính chung cần timeout, logout, kiểm soát cookies, quyền truy cập trên thiết bị. `no-store` không xoá một entry cũ chưa bị làm mới chỉ bằng response mới nếu cache không gọi origin; phải phối hợp versioned URLs, invalidation, auth và chính sách cache thực tế.

## 8. ETag, Last-Modified và HTTP 304

`Cache-Control` quyết định cache có thể reuse ra sao. **ETag** và **Last-Modified** là validators giúp cache hỏi server liệu bản đã lưu còn đúng không:

```text
1. GET /api/public/config
   -> 200 OK
      Cache-Control: no-cache
      ETag: "config-v3"
      Body: {"theme":"light"}

2. GET /api/public/config
   If-None-Match: "config-v3"
   -> 304 Not Modified
      ETag: "config-v3"
      [không có response body]

3. Client/cache reuse body của bản đã lưu
```

- `no-cache` vẫn cho phép bước 3 nếu validate thành công.
- `304 Not Modified` tiết kiệm băng thông body và cập nhật một số metadata của entry; nó **không tự tạo** dữ liệu cho client không có cached representation.
- `Last-Modified` và `If-Modified-Since` là cơ chế khác dùng HTTP-date. Timestamp có độ phân giải/các vấn đề độ chính xác nên ETag thường linh hoạt hơn khi representation thay đổi thường xuyên.
- Với cả `If-None-Match` và `If-Modified-Since`, HTTP có quy tắc ưu tiên validator; không kiểm tra độc lập hai header rồi trả 304 sai.
- ETag phải phản ánh version/representation thực, không lấy ngẫu nhiên mỗi request làm mất cache hit; nếu nội dung user-specific, validator cũng phải gắn đúng user và ACL.

### no-cache với ETag khác no-store

`Cache-Control: no-cache` + `ETag` là thiết kế hữu ích cho JSON/HTML công khai thay đổi thường xuyên: cached bytes có thể ở browser, nhưng mỗi lần dùng lại cần origin xác nhận. `no-store` bảo cache đừng lưu response, làm revalidation bằng cached body không còn tác dụng theo ngữ nghĩa thông thường.

### Cache với Age và request Cache-Control

Client có thể gửi:

```http
Cache-Control: no-cache
```

trong **request** để yêu cầu cache không dùng entry đã lưu mà không validate. Nó **không thể ép origin cho dữ liệu mới** nếu origin đã sai, và request directives khác response directives về chủ thể áp dụng. `Cache-Control: max-age=0` trong request thường yêu cầu entry phải có age rất nhỏ/không còn fresh để được dùng, nhưng không giống tuyệt đối với một quy trình purge caches.

## 9. Vary: cache nhiều representations đúng cách

Một URL có thể trả dữ liệu khác nhau tùy request header:

```http
GET /help
Accept-Language: vi
```

và:

```http
GET /help
Accept-Language: en
```

Nếu server dùng `Accept-Language` để chọn ngôn ngữ, response nên có:

```http
Vary: Accept-Language
Cache-Control: public, max-age=300
```

Shared cache cần tính đến `Vary` khi chọn response đã lưu, tránh phục vụ bản tiếng Việt cho request English. Tương tự, với nội dung nén/không nén:

```http
Vary: Accept-Encoding
```

Điều cần phân biệt:

- `Vary` là **cache selection metadata**, không phải phân quyền hay secret protection.
- `Vary: Cookie` hoặc `Vary: Authorization` không phải lúc nào cũng an toàn/khả thi với số lượng biến thể rất lớn; user-specific content thường nên dùng `private` hoặc `no-store` và cấu hình CDN không lưu.
- API có query parameters cũng phải được cache key phân biệt chính xác; một số CDN có cấu hình bỏ query hoặc chuẩn hóa URL. Các query chứa secrets không nên xuất hiện trong URL/log.
- Khi trả ngôn ngữ khác nhau theo session cookie nhưng `Vary: Accept-Language`, policy có thể sai vì nguồn quyết định representation không phải request Accept-Language.

## 10. Spring MVC: CacheControl API

Spring Framework cung cấp `org.springframework.http.CacheControl` để dựng response header đúng cú pháp. API quan trọng:

```java
CacheControl.maxAge(Duration.ofSeconds(120));
CacheControl.noCache();
CacheControl.noStore();
CacheControl.maxAge(Duration.ofSeconds(120)).cachePublic();
CacheControl.maxAge(Duration.ofSeconds(60)).cachePrivate();
CacheControl.maxAge(Duration.ofSeconds(120))
        .sMaxAge(Duration.ofSeconds(600)).cachePublic();
CacheControl.maxAge(Duration.ofDays(365))
        .cachePublic().immutable();
```

Đây là những **snippets Java**, cần imports `CacheControl`, `Duration`; không phải chương trình `main` độc lập. Các methods `cachePublic()`, `cachePrivate()`, `sMaxAge(Duration)` và `immutable()` có trong dòng Spring 6.1.

Có thể kết hợp với `ResponseEntity`:

```java
return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(responseDto);
```

Ví dụ này cần biến `responseDto` và return type phù hợp; controller hoàn chỉnh ở mục 11. `ResponseEntity.cacheControl(...)` đặt HTTP `Cache-Control` trên response chứ không cache một Java object trong Spring Service.

### Expires trong ResponseEntity

Spring không bắt buộc lập trình viên chỉ dùng CacheControl; có thể đặt `Expires` bằng `ResponseEntity.header(...)`:

```java
String expires = ZonedDateTime.now(ZoneOffset.UTC)
        .plusSeconds(120)
        .format(DateTimeFormatter.RFC_1123_DATE_TIME);

return ResponseEntity.ok()
        .header(HttpHeaders.EXPIRES, expires)
        .body(responseDto);
```

Cần imports `ZonedDateTime`, `ZoneOffset`, `DateTimeFormatter`, `HttpHeaders`, `ResponseEntity` và một DTO hợp lệ. Đây là **snippet**. Để tránh tạo một thời điểm quá xa hoặc dùng local timezone không rõ, UTC + HTTP-date là lựa chọn phù hợp. Nếu thêm `max-age` cùng Expires, nhớ **max-age thắng** khi cache hỗ trợ.

## 11. Dự án Java 17/Spring Boot 3.3.5 runnable

Ta xây một REST API với bốn nhóm policy:

1. `GET /api/cache/public` — dữ liệu công khai: browser fresh 120 giây, shared cache fresh 600 giây.
2. `GET /api/cache/revalidate` — dữ liệu công khai nhưng **mỗi lần reuse cần revalidation**, có ETag cố định và hỗ trợ 304.
3. `GET /api/cache/private-demo` — dữ liệu minh họa cá nhân với `private, max-age=60`.
4. `GET /api/cache/secret-demo` — dữ liệu demo nhạy cảm với `no-store`.
5. `GET /api/cache/expires` — chỉ dùng Expires như ví dụ absolute HTTP-date.

Tất cả endpoint trả dữ liệu **cố định, không có authentication**, để tập trung HTTP caching. Các tên `private-demo` và `secret-demo` chỉ minh họa header policy; đây **không phải API xác thực thật** và không tạo/hiển thị secrets thực. Production phải lấy principal từ Spring Security và xác thực quyền trước khi xây response.

### 11.1. Cây project

```text
http-cache-demo/
├── pom.xml
└── src/
    ├── main/java/demo/httpcache/
    │   ├── HttpCacheApplication.java
    │   └── CacheDemoController.java
    └── test/java/demo/httpcache/
        └── CacheDemoControllerTest.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>http-cache-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
```

**`src/main/java/demo/httpcache/HttpCacheApplication.java`**

```java
package demo.httpcache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpCacheApplication.class, args);
    }
}
```

### 11.2. Controller với các policies rõ ràng

**`src/main/java/demo/httpcache/CacheDemoController.java`**

```java
package demo.httpcache;

import java.time.Duration;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/cache")
public class CacheDemoController {

    public record Catalog(String siteName, String release) {}

    @GetMapping("/public")
    public ResponseEntity<Catalog> publicCatalog() {
        Catalog data = new Catalog("Java Learning", "2026.10");

        CacheControl cache = CacheControl
                .maxAge(Duration.ofSeconds(120))
                .cachePublic()
                .sMaxAge(Duration.ofSeconds(600));

        return ResponseEntity.ok()
                .cacheControl(cache)
                .body(data);
    }

    @GetMapping("/revalidate")
    public ResponseEntity<Map<String, String>> revalidate() {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noCache())
                .eTag("config-v1")
                .body(Map.of("theme", "light"));
    }

    @GetMapping("/private-demo")
    public ResponseEntity<Map<String, String>> privateDemo() {
        return ResponseEntity.ok()
                .cacheControl(CacheControl
                        .maxAge(Duration.ofSeconds(60))
                        .cachePrivate())
                .body(Map.of("displayName", "Example User"));
    }

    @GetMapping("/secret-demo")
    public ResponseEntity<Map<String, String>> secretDemo() {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of("notice", "Do not store this response"));
    }

    @GetMapping("/expires")
    public ResponseEntity<Map<String, String>> withExpires() {
        String expires = ZonedDateTime.now(ZoneOffset.UTC)
                .plusSeconds(120)
                .format(DateTimeFormatter.RFC_1123_DATE_TIME);

        return ResponseEntity.ok()
                .header(HttpHeaders.EXPIRES, expires)
                .body(Map.of("policy", "expires-only"));
    }
}
```

**Giải thích code:**

- `@RestController` trả JSON DTO/Map qua Jackson và `ResponseEntity` cung cấp status/headers.
- Endpoint `public` chủ động dùng `max-age=120` và `s-maxage=600` để minh họa sự khác nhau giữa browser và CDN. Chỉ làm vậy vì body là dữ liệu **công khai, không user-specific**.
- `revalidate` có `no-cache` + `ETag`. Trong Spring MVC, khi client gửi `If-None-Match: "config-v1"`, framework có thể xử lý `ResponseEntity` thành `304 Not Modified` với body rỗng.
- `private-demo` cho phép private cache giữ tối đa 60s; shared cache bị cấm lưu do `private`.
- `secret-demo` nói với mọi cache không lưu; JSON ở đây chỉ là **chuỗi giả lập**, không có secret thật.
- `expires` xây HTTP-date tại thời điểm request cộng 120s; **không đặt Cache-Control max-age** để có thể học riêng ưu tiên và cú pháp Expires.
- Các endpoint không thêm `@Cacheable` vì ở đây học HTTP response caching, không phải method-level cache.
- ETag `config-v1` chỉ hợp lệ khi bytes/semantics của representation thực tế không đổi trong cùng version. Nếu đổi JSON body mà quên đổi ETag, server có thể trả 304 sai cho cached body cũ.

### 11.3. Chạy và kiểm tra bằng curl

Từ thư mục `http-cache-demo` có `pom.xml`, cài Java 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

Đây là **hai lệnh chạy tuần tự**. Khi server ở `localhost:8080`, thử:

```bash
curl -i http://localhost:8080/api/cache/public
```

Các headers/body chính (không cam kết thứ tự JSON fields):

```http
HTTP/1.1 200
Content-Type: application/json
Cache-Control: max-age=120, public, s-maxage=600

{"siteName":"Java Learning","release":"2026.10"}
```

Tiếp theo:

```bash
curl -i http://localhost:8080/api/cache/private-demo
```

Dự kiến:

```http
HTTP/1.1 200
Cache-Control: max-age=60, private

{"displayName":"Example User"}
```

Response `secret-demo` có:

```http
HTTP/1.1 200
Cache-Control: no-store
```

Đầu tiên lấy response có ETag:

```bash
curl -i http://localhost:8080/api/cache/revalidate
```

Mong đợi:

```http
HTTP/1.1 200
Cache-Control: no-cache
ETag: "config-v1"

{"theme":"light"}
```

Gửi conditional GET:

```bash
curl -i \
  -H 'If-None-Match: "config-v1"' \
  http://localhost:8080/api/cache/revalidate
```

Spring MVC nên trả status `304 Not Modified` và không có response body khi ETag match. `curl` không phải browser cache mặc định; lệnh chỉ mô phỏng client gửi conditional header, không chứng minh rằng response thực đã được cache trong browser/CDN.

Thử `Expires`:

```bash
curl -i http://localhost:8080/api/cache/expires
```

Dự kiến có `Expires: <HTTP-date>` khoảng hai phút sau thời điểm response được tạo. **Không hardcode ngày giờ** vì phụ thuộc đồng hồ server. Một header `Date` do container hoặc proxy bổ sung có thể xuất hiện tùy runtime.

## 12. MockMvc contract tests

**`src/test/java/demo/httpcache/CacheDemoControllerTest.java`**

```java
package demo.httpcache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CacheDemoControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicResponseHasBrowserAndSharedTtls() throws Exception {
        mvc.perform(get("/api/cache/public"))
           .andExpect(status().isOk())
           .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL,
                    "max-age=120, public, s-maxage=600"))
           .andExpect(jsonPath("$.siteName").value("Java Learning"));
    }

    @Test
    void privateResponseCannotBeStoredBySharedCache()
            throws Exception {
        mvc.perform(get("/api/cache/private-demo"))
           .andExpect(status().isOk())
           .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, "max-age=60, private"));
    }

    @Test
    void secretResponseRequestsNoStorage() throws Exception {
        mvc.perform(get("/api/cache/secret-demo"))
           .andExpect(status().isOk())
           .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, "no-store"));
    }

    @Test
    void unchangedETagGets304WithoutBody() throws Exception {
        mvc.perform(get("/api/cache/revalidate")
                    .header(HttpHeaders.IF_NONE_MATCH, "\"config-v1\""))
           .andExpect(status().isNotModified())
           .andExpect(content().string(""));
    }

    @Test
    void withoutConditionRevalidationEndpointReturnsBody()
            throws Exception {
        mvc.perform(get("/api/cache/revalidate"))
           .andExpect(status().isOk())
           .andExpect(header().string(HttpHeaders.ETAG,
                    "\"config-v1\""))
           .andExpect(header().string(HttpHeaders.CACHE_CONTROL,
                    "no-cache"))
           .andExpect(jsonPath("$.theme").value("light"));
    }

    @Test
    void expiresIsValidHttpDate() throws Exception {
        var result = mvc.perform(get("/api/cache/expires"))
                .andExpect(status().isOk())
                .andExpect(header().exists(HttpHeaders.EXPIRES))
                .andReturn();
        String expires = result.getResponse()
                .getHeader(HttpHeaders.EXPIRES);
        assertTrue(expires != null && expires.contains("GMT"));
    }
}
```

Bộ test gồm **6 test methods**. Chạy:

```bash
mvn test
```

Nếu chạy và toàn bộ tests pass, Maven exit code `0` và sẽ có summary tương tự `Tests run: 6, Failures: 0, Errors: 0, Skipped: 0`. Mã ở đây được thiết kế theo API của Spring MVC 6.1/Java 17; bài không tuyên bố đã thực sự chạy Maven trong quá trình ghi Sheet.

**Giới hạn của tests:**

- MockMvc kiểm tra headers và MVC conditional response, **không chứng minh** CDN đã lưu và tái sử dụng response giữa nhiều users.
- Để kiểm thử shared cache cần staging có proxy/CDN thực, kiểm tra hit/miss/Age/Vary và các request có cookies/Authorization.
- Không dùng `response.getHeader("Expires")` chứa `GMT` như kiểm tra duy nhất cho production: parse HTTP-date theo chuẩn và so policy/freshness kỳ vọng trong test chuyên sâu.
- Khi thêm Spring Security, test phải mô phỏng principal/authn đúng; các endpoint demo hiện không bảo mật thật.

## 13. Static resources: cache lâu chỉ khi URL thay đổi theo nội dung

Spring Boot có thể phục vụ file từ `classpath:/static/`. Đối với CSS/JS/ảnh, caching lâu giúp giảm origin traffic, nhưng dễ gây client giữ **bản cũ** sau deploy nếu URL không thay.

### Thiết kế tốt: fingerprint URL

```text
/assets/site.abc123.css   -> bytes của bản A
/assets/site.def456.css   -> bytes của bản B
```

Nếu cùng URL immutable không đổi bytes, bạn có thể đặt:

```http
Cache-Control: public, max-age=31536000, immutable
```

Khi deploy, HTML phải tham chiếu URL mới, còn file URL cũ phải tiếp tục được phục vụ đúng bytes trong khoảng cần thiết. Đừng dùng `immutable` cho `/index.html`/`/config.json` có thể đổi cùng URL.

### Spring MVC resource handler minh họa

**`AssetsCacheConfig.java`** (cấu hình **tùy chọn**, không cần cho runnable API ở mục 11):

```java
package demo.httpcache;

import java.time.Duration;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class AssetsCacheConfig implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/static/assets/")
                .setCacheControl(CacheControl
                        .maxAge(Duration.ofDays(365))
                        .cachePublic()
                        .immutable());
    }
}
```

Nếu thêm class này, chuẩn bị file dưới `src/main/resources/static/assets/`. Chính sách này **chỉ an toàn nếu mọi file được phục vụ trong /assets/** có URL immutable/fingerprinted**; nếu để `/assets/logo.png` rồi overwrite logo hàng ngày, browser có thể giữ logo cũ rất lâu.

### Cấu hình Spring Boot cho resources

Các properties tồn tại trong Boot 3.3:

```properties
spring.web.resources.cache.cachecontrol.max-age=365d
spring.web.resources.cache.cachecontrol.cache-public=true
```

**Đây là ví dụ cấu hình toàn cục các static resource handlers mặc định, không phải phần bắt buộc trong runnable project.** Cấu hình global có thể ảnh hưởng cả static HTML không versioned. Khi có cả index.html và assets fingerprinted, thường nên chọn **resource handler riêng** như trên hoặc config cụ thể cho từng đường dẫn thay vì áp max-age 1 năm cho tất cả.

### Static resource handling không giống @Cacheable

- `Cache-Control` và `ETag`/`Last-Modified` giúp browser/proxy cache response.
- `spring.web.resources.chain.cache` tối ưu lookup resource chain **ở phía server**, không phải thời hạn browser cache.
- `@Cacheable` tối ưu return values của Spring beans; không mặc định liên quan URL hash, Vary, CDN hay HTTP status.

## 14. Cách kiểm chứng cache trình duyệt và CDN

### 14.1. Dùng DevTools

Trong browser DevTools → Network:

1. Mở trang và ghi lại request URL, status, Cache-Control, Expires, ETag, Last-Modified.
2. Reload bình thường: response có thể dùng memory/disk cache hoặc revalidate theo policy.
3. Thử disabled cache trong DevTools khi cần so sánh (tác dụng phụ thuộc DevTools mở hay không).
4. Với `no-cache`, quan sát conditional request có `If-None-Match` và response `304` nếu đã có ETag/cached representation.
5. Với static assets hashed, có thể thấy resource được phục vụ từ memory/disk cache mà không liên hệ origin.
6. So response có `Vary` đúng khi đổi ngôn ngữ hoặc Accept-Encoding.

**Không dùng browser Back/Forward Cache (bfcache)** làm bằng chứng HTTP cache đang hoạt động. bfcache có thể lưu snapshot của một trang/DOM để quay lại nhanh, là cơ chế khác với HTTP response caching và có điều kiện riêng.

### 14.2. Kiểm tra CDN thật

Với một CDN/proxy staging:

- Request public URL lần đầu, quan sát miss hoặc Age nhỏ; request lần sau có thể hit. Các headers cụ thể như `X-Cache`/`CF-Cache-Status` là **provider-specific**, không phải chuẩn HTTP chung.
- So request từ hai browsers không có auth tới public asset có cùng cache key.
- Với private URL, test hai principals/cookies khác nhau và đảm bảo response A **không thể được tái sử dụng cho B** qua shared cache.
- Gửi request có Authorization tới endpoint public vs private, kiểm tra behavior theo CDN configuration và `Cache-Control`.
- Kiểm tra query parameters, `Vary: Accept-Encoding`, `Vary: Accept-Language`, cookies và redirects.
- Khi purge CDN hoặc deploy phiên bản mới, test sự nhất quán URL/ETag và freshness qua tất cả edge locations.

Nếu không có CDN/proxy trước server, chỉ quan sát headers bằng curl không chứng minh shared caching diễn ra. `Cache-Control` là chính sách mà cache tuân thủ, không phải lệnh “lưu vào CDN ngay”.

## 15. Những lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `no-cache` nhưng browser vẫn có bản response | Hiểu nhầm “no-cache = no-store” | no-cache cho lưu nhưng yêu cầu revalidate trước reuse |
| Có `private` mà dữ liệu còn trong browser disk | private chỉ cấm shared cache | Dùng no-store khi cần không lưu |
| CDN trả nhầm dữ liệu giữa các user | Public/s-maxage nhầm trên response cá nhân, cache key sai | Cấm shared caching, audit Authorization/Cookie/Vary và purge đúng |
| Thêm `Set-Cookie` nhưng CDN vẫn có cache hit | Cookie không tự cấm cache theo RFC | Set explicit Cache-Control và CDN bypass rules |
| Expires đã qua nhưng body vẫn được reuse | Stale serving/validator/heuristic hoặc policy khác | Xem Cache-Control precedence, Age, revalidation |
| max-age 120s nhưng browser chỉ còn 40s | CDN đã giữ 80s, Age/Date | Tính current age thay vì reset TTL ở mỗi tầng |
| Sửa CSS nhưng client thấy bản cũ | Long TTL cùng URL, immutable sai | URL fingerprint + versioning, purge nếu cần |
| 304 không xảy ra dù có ETag | Client chưa gửi If-None-Match, ETag thay mỗi lần | Kiểm tra request headers, ETag lifecycle |
| 304 nhưng nội dung thực đã thay | ETag không tăng theo representation | Dùng version/hash ổn định phản ánh bytes |
| Response có both Expires và max-age khác nhau | Không hiểu precedence | max-age thắng Expires; s-maxage dành shared cache |
| Dữ liệu dịch sai ngôn ngữ qua CDN | Thiếu Vary: Accept-Language hoặc cache key | Set Vary khi representation phụ thuộc header |
| Hệ thống JSON cache có auth mà vẫn public | Chỉ nhìn 200/GET không xét identity | Tách public vs personalized contract, dùng private/no-store |
| Nghe nói `@Cacheable` nhưng DevTools vẫn tải body | Method cache khác HTTP cache | Thêm headers/ETag phù hợp và đo riêng hai tầng |
| CDN không cache dù public,max-age đã có | Cache policy, bypass, Set-Cookie handling hoặc method/status | Kiểm tra config CDN thay vì khẳng định Spring đã lưu |
| Browser không lưu dù max-age lớn | Capacity eviction, private mode, browser policy | Cache headers không bảo đảm retention |
| 304 có Cache-Control khác response 200 | Response validation cập nhật metadata | Kiểm tra response policy trong cả 200 và 304 |
| Dùng immutable cho dữ liệu động | Cùng URL thay bytes nhưng cache không revalidate | Bỏ immutable hoặc đổi URL theo nội dung |

Cách debug có hệ thống:

1. Xác định response có **dữ liệu công khai hay user-specific** trước khi bàn TTL.
2. Kiểm tra response **Cache-Control, Expires, Date, Age, ETag, Last-Modified, Vary**.
3. Kiểm tra request method, URL/query, **Authorization, Cookie, Accept-Language, Accept-Encoding**.
4. Xác định cache nào đang hit: browser, service worker, reverse proxy, CDN hay server method cache.
5. Nếu thấy 304, xác nhận validator đúng và cached body thuộc cùng representation/user.
6. Test hai users thực qua shared cache để tìm leakage, không chỉ check header.
7. Nếu có sự không nhất quán, tách origin response khỏi CDN-transformed response.
8. Xem invalidation/versioning sau deploy, không chỉ thời hạn một lần request.

## 16. Security và chính sách dữ liệu

### 16.1. No-store không làm dữ liệu an toàn tuyệt đối

`no-store` không tự thu hồi bản copy đã rời server, không bảo vệ screenshot, browser extension độc hại, proxy không tuân thủ hay log/observability. Dữ liệu thực sự nhạy cảm còn cần:

- HTTPS và HSTS phù hợp.
- Authentication, authorization và tenant isolation đúng.
- Session expiry, cookie flags và logout.
- Không ghi secrets vào URL/query, logs, tracing hoặc response không cần thiết.
- CDN/reverse proxy config cấm cache endpoints private và không lưu response với tokens.
- Data retention/erasure policies và audit.

### 16.2. Stale content có thể gây sai nghiệp vụ

Một `GET /cart` cache stale có thể làm user thấy số lượng/coupon cũ; còn `POST /checkout` phải **luôn xác thực giá, tồn kho và quyền** trên dữ liệu authoritative. Không dựa vào giá hiển thị từ CDN để quyết định tính tiền. Với content cập nhật mạnh, `no-cache` hoặc low TTL có thể hợp lý; với public read-only content, TTL cao hơn có ích.

### 16.3. Vary và cache key là một phần của security review

Nếu hai users được trả representation khác nhau tại cùng URL, chỉ đặt `max-age` và hy vọng cache “tự phân biệt user” là sai. Cần cấm shared caching hoặc định nghĩa cache key/authorization architecture rất cẩn thận; `private` hoặc `no-store` là điểm xuất phát phù hợp. Cũng cần xét các response lỗi, redirects, 304, preflight và các response từ gateway.

## 17. Bài tập tự kiểm tra

1. `Cache-Control: no-cache` có cho phép cache lưu response không? Khi nào được reuse?
2. `no-store` và `private` khác nhau như thế nào?
3. Với `public, max-age=60, s-maxage=300`, browser và CDN dùng TTL nào?
4. `Expires` tương tác thế nào với `max-age` và `s-maxage`?
5. Vì sao `Authorization` không bảo đảm mọi shared cache tuyệt đối không lưu dữ liệu?
6. Vì sao `Set-Cookie` không phải lá chắn cache cho thông tin cá nhân?
7. Lợi ích của `ETag` và `304 Not Modified` khi response `no-cache` là gì?
8. `Age: 40` ảnh hưởng thế nào tới response `max-age=120`?
9. Khi nào dùng `immutable` cho CSS/JS, và phải phối hợp URL versioning ra sao?
10. `Vary: Accept-Language` giải quyết việc gì? Nó có thay authorization được không?
11. `@Cacheable` và HTTP `Cache-Control` là cùng một lớp cache không?
12. Vì sao test response headers bằng MockMvc chưa chứng minh CDN thật không rò rỉ dữ liệu?

**Gợi ý trả lời:** (1) Có thể store, nhưng phải validate trước reuse. (2) No-store cấm lưu mọi cache, private cấm shared cache. (3) Browser 60s, shared cache 300s nếu các điều kiện khác thỏa. (4) Cache-Control TTL tương ứng ưu tiên Expires. (5) Public/s-maxage/must-revalidate có thể cho phép theo RFC. (6) Cookie không tự cấm shared caching theo chuẩn. (7) Không chuyển lại body khi representation chưa đổi. (8) Gần đúng còn 80s trong mô hình đơn giản. (9) Khi URL chứa fingerprint và bytes không đổi. (10) Phân biệt representation theo language; không phải auth. (11) Không; một cái method cache, một cái HTTP response cache. (12) Shared cache có policy/cache keys thực tế khác MockMvc.

## 18. Tài liệu tham khảo

- [RFC 9111 — HTTP Caching, cache storage/freshness/revalidation](https://www.rfc-editor.org/rfc/rfc9111.html)
- [RFC 9110 — HTTP Semantics, conditional requests](https://www.rfc-editor.org/rfc/rfc9110.html)
- [Spring Framework 6.1 — HTTP Caching (Spring MVC)](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-caching.html)
- [Spring Framework 6.1 — CacheControl Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/CacheControl.html)
- [Spring Framework 6.1 — ResponseEntity Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/ResponseEntity.html)
- [Spring Framework — Static Resources](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html)
- [Spring Boot 3.3 — Common Application Properties, static resources](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)
- [MDN — HTTP Caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- [MDN — Cache-Control header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control)
- [RFC 8246 — immutable response directive](https://www.rfc-editor.org/rfc/rfc8246.html)

**Kết luận:** `Cache-Control` quyết định giới hạn lưu, thời hạn fresh và revalidation; `Expires` là hạn dùng tuyệt đối có độ ưu tiên thấp hơn `max-age`/`s-maxage`. Browser cache phục vụ một client; shared cache/CDN phục vụ nhiều clients và vì vậy yêu cầu thiết kế privacy/cache key nghiêm ngặt. Spring MVC dùng `CacheControl`, `ResponseEntity`, `ETag` và resource handling để hiện thực hóa HTTP policy, nhưng **không tự làm CDN an toàn hay thay kiểm tra quyền**. Trước khi bật caching, hãy hỏi: *Ai được đọc representation? Cache nào có thể giữ? Bao lâu và cập nhật thế nào?*.
