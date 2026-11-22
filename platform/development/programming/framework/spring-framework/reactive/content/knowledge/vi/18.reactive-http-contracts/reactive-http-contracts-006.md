# `CacheControl` và chiến lược bộ nhớ đệm HTTP trong Spring WebFlux

## 1. HTTP caching giải quyết vấn đề gì?

Một API thường trả cùng một tài nguyên nhiều lần: ảnh, file JavaScript, cấu hình công khai, danh mục sản phẩm hoặc dữ liệu bài viết. Nếu client phải tải toàn bộ nội dung ở mọi request, hệ thống tốn băng thông, tăng độ trễ và tạo tải lặp lại lên server.

**HTTP caching** cho phép browser, proxy hoặc CDN lưu response và tái sử dụng theo chính sách do server công bố. Khi bản lưu đã cũ, cache có thể hỏi server xem nội dung có thay đổi không. Nếu chưa thay đổi, server trả `304 Not Modified` mà không phải gửi lại body.

Trong Spring Framework, `org.springframework.http.CacheControl` là builder để tạo header `Cache-Control` cho response. Spring WebFlux có thể gắn chính sách này vào `ResponseEntity`, `ServerResponse` hoặc static resource handler.

Cần phân biệt ba khái niệm:

1. **HTTP cache policy:** hướng dẫn browser, proxy và CDN có được lưu response không, lưu trong bao lâu và khi nào phải xác thực lại.
2. **HTTP validator:** `ETag` hoặc `Last-Modified` giúp cache kiểm tra bản lưu có còn đại diện cho tài nguyên hiện tại không.
3. **Application cache:** cache dữ liệu bên trong ứng dụng, ví dụ Caffeine, Redis hoặc Spring Cache. Đây là cơ chế riêng, không được tạo ra chỉ bằng `CacheControl`.

`CacheControl` không lưu object vào RAM, Redis hay database. Nó tạo chỉ thị HTTP để cache ở phía client hoặc intermediary thực hiện theo.

## 2. Vòng đời của một response được cache

```text
Client gửi GET /products/42
          |
          v
Spring WebFlux tạo response
          |
          | Cache-Control: private, max-age=60
          | ETag: "product-v3"
          v
Browser nhận 200 OK và body
          |
          v
Browser lưu response theo cache key
          |
          | Trong freshness lifetime: có thể dùng bản lưu
          |
          v
Khi cần xác thực lại, gửi If-None-Match
          |
          v
Server so sánh validator
          |
          +---- Chưa đổi ----> 304 Not Modified, không có body
          |
          +---- Đã đổi ------> 200 OK, ETag mới và body mới
```

- **Fresh:** response còn trong freshness lifetime; cache có thể tái sử dụng mà không hỏi origin nếu không có chỉ thị khác.
- **Stale:** freshness lifetime đã hết; cache thường phải revalidate trước khi tái sử dụng.
- **Revalidation:** cache gửi conditional request bằng `If-None-Match` hoặc `If-Modified-Since`.
- **304 Not Modified:** server xác nhận representation đã lưu vẫn phù hợp; cache có thể tiếp tục dùng body cũ.
- **200 OK:** representation mới được gửi khi tài nguyên thay đổi hoặc không có validator phù hợp.

HTTP caching hữu ích nhất với `GET` và `HEAD`. Cache các phương thức khác có điều kiện riêng; không mặc định rằng mọi request đều có thể được cache.

## 3. `Cache-Control` là header nào?

`Cache-Control` là response header chứa một hoặc nhiều directive, phân cách bằng dấu phẩy:

```http
Cache-Control: private, max-age=60, must-revalidate
```

Ví dụ:

```http
Cache-Control: max-age=3600
```

cho phép cache coi response fresh trong 3.600 giây theo HTTP caching model.

Spring cung cấp builder:

```java
CacheControl oneHour =
        CacheControl.maxAge(Duration.ofHours(1));

CacheControl noStore =
        CacheControl.noStore();

CacheControl privateCache =
        CacheControl.maxAge(Duration.ofMinutes(5))
                .cachePrivate();

CacheControl publicAsset =
        CacheControl.maxAge(Duration.ofDays(30))
                .cachePublic()
                .immutable();
```

`CacheControl` là builder cho response directives. Nó không phải parser tổng quát cho request header `Cache-Control`; nếu cần đọc request directive, hãy đọc request headers và xử lý theo chính sách ứng dụng.

## 4. Các directive quan trọng

### 4.1. `max-age`

```http
Cache-Control: max-age=300
```

Response có freshness lifetime 300 giây. Trong thời gian đó, cache có thể dùng bản lưu mà không gửi request tới server, trừ khi có yêu cầu revalidation hoặc chính sách khác.

Spring:

```java
CacheControl.maxAge(Duration.ofMinutes(5));
```

Chỉ đặt `max-age` khi ứng dụng chấp nhận client nhìn thấy bản dữ liệu cũ trong khoảng thời gian đó.

### 4.2. `no-cache` và `no-store`

```http
Cache-Control: no-cache
```

`no-cache` **không đồng nghĩa với cấm lưu**. Cache có thể lưu response, nhưng phải xác thực lại với origin trước khi sử dụng bản lưu.

```java
CacheControl.noCache();
```

Ngược lại:

```http
Cache-Control: no-store
```

yêu cầu cache không lưu response. Dùng khi nội dung nhạy cảm hoặc response không được phép lưu trong cache HTTP.

```java
CacheControl.noStore();
```

`no-store` không thay thế TLS, authentication, authorization, bảo vệ log hoặc quản lý dữ liệu nhạy cảm ở tầng ứng dụng.

### 4.3. `private` và `public`

```http
Cache-Control: private, max-age=60
```

`private` cho biết response dành cho một user; shared cache như proxy/CDN không được lưu response theo directive này. Browser cache riêng của user vẫn có thể lưu.

```http
Cache-Control: public, max-age=3600
```

`public` cho phép cache công khai lưu response trong các trường hợp mà nếu không có directive này thì response có thể bị hạn chế lưu ở shared cache.

Spring:

```java
CacheControl.maxAge(Duration.ofMinutes(1)).cachePrivate();

CacheControl.maxAge(Duration.ofHours(1)).cachePublic();
```

Không gắn `public` cho endpoint cá nhân hóa theo user, tenant, role hoặc cookie nếu chưa chứng minh cache chia sẻ không thể trả nhầm dữ liệu.

### 4.4. `s-maxage`

```http
Cache-Control: public, max-age=60, s-maxage=300
```

`s-maxage` áp dụng cho shared cache và ghi đè freshness lifetime `max-age` trong shared cache. Browser/private cache vẫn dùng `max-age`.

```java
CacheControl.maxAge(Duration.ofMinutes(1))
        .cachePublic()
        .sMaxAge(Duration.ofMinutes(5));
```

Dùng khi muốn CDN/proxy có freshness khác browser, nhưng chỉ khi dữ liệu phù hợp với cache dùng chung.

### 4.5. `must-revalidate` và `proxy-revalidate`

- `must-revalidate`: khi response đã stale, cache phải xác thực lại trước khi dùng.
- `proxy-revalidate`: áp dụng quy tắc tương tự cho shared cache, không áp dụng cho private cache.

```java
CacheControl.maxAge(Duration.ofMinutes(2))
        .mustRevalidate();

CacheControl.maxAge(Duration.ofMinutes(2))
        .proxyRevalidate();
```

Chúng không thay thế validator; muốn revalidate hiệu quả, nên cung cấp `ETag` hoặc `Last-Modified`.

### 4.6. `immutable`

```http
Cache-Control: public, max-age=31536000, immutable
```

`immutable` báo rằng representation sẽ không thay đổi trong freshness lifetime. Nó phù hợp với static asset có tên chứa hash/version, ví dụ `app.8d91a2.js`.

```java
CacheControl.maxAge(Duration.ofDays(365))
        .cachePublic()
        .immutable();
```

Chỉ dùng với URL versioned hoặc tài nguyên thật sự bất biến trong thời hạn cache. Nếu ghi đè nội dung nhưng giữ nguyên URL, client có thể tiếp tục dùng bản cũ rất lâu.

### 4.7. `no-transform`

`no-transform` yêu cầu intermediary không thay đổi representation theo cách làm biến đổi nội dung.

```java
CacheControl.maxAge(Duration.ofHours(1))
        .cachePublic()
        .noTransform();
```

### 4.8. `stale-while-revalidate` và `stale-if-error`

```java
CacheControl policy = CacheControl.maxAge(Duration.ofMinutes(1))
        .staleWhileRevalidate(Duration.ofSeconds(30))
        .staleIfError(Duration.ofMinutes(10));
```

- `stale-while-revalidate=30`: cache có thể phục vụ bản stale tối đa 30 giây trong lúc cố gắng revalidate ở nền.
- `stale-if-error=600`: khi origin gặp lỗi, cache có thể dùng bản stale trong thời gian cho phép.

Hành vi phụ thuộc cache/CDN có hỗ trợ các extension directive hay không. Không giả định mọi browser hoặc proxy đều triển khai giống nhau. Đây không phải retry của Reactor hay Spring Cache.

## 5. Chọn chính sách theo loại dữ liệu

| Loại response | Chính sách thường cân nhắc | Lý do |
|---|---|---|
| JavaScript/CSS/image có hash trong URL | `public`, `max-age` dài, `immutable` | URL mới khi nội dung thay đổi |
| Danh mục công khai thay đổi định kỳ | `public`, `max-age` ngắn, ETag | Cache được nhưng cập nhật tương đối nhanh |
| API phụ thuộc user đăng nhập | `private`, freshness ngắn hoặc `no-cache` | Tránh shared cache lưu dữ liệu cá nhân |
| Response chứa bí mật | `no-store` | Không muốn cache HTTP lưu response |
| Dữ liệu cần kiểm tra mỗi lần dùng nhưng giữ được body | `no-cache` cùng ETag | Cache revalidate, có thể nhận 304 |
| API công khai qua CDN | `public`, `s-maxage`, validator | Freshness riêng cho shared cache |
| Stream thời gian thực/SSE | Policy riêng, thường không cache | Nội dung thay đổi liên tục |

Đây là điểm khởi đầu, không phải công thức bắt buộc. Hãy quyết định theo độ nhạy dữ liệu, tần suất thay đổi, mức chấp nhận stale, cache key và cách triển khai CDN.

## 6. API `CacheControl` trong Spring Framework

Class `org.springframework.http.CacheControl` là builder fluent. Những method thường dùng trong Spring Framework 6.1:

| Method | Directive |
|---|---|
| `maxAge(Duration)` | `max-age` |
| `noCache()` | `no-cache` |
| `noStore()` | `no-store` |
| `cachePrivate()` | `private` |
| `cachePublic()` | `public` |
| `mustRevalidate()` | `must-revalidate` |
| `proxyRevalidate()` | `proxy-revalidate` |
| `sMaxAge(Duration)` | `s-maxage` |
| `staleWhileRevalidate(Duration)` | `stale-while-revalidate` |
| `staleIfError(Duration)` | `stale-if-error` |
| `noTransform()` | `no-transform` |
| `immutable()` | `immutable` |
| `getHeaderValue()` | Lấy chuỗi header đã tạo |

Ví dụ:

```java
CacheControl policy = CacheControl.maxAge(Duration.ofMinutes(10))
        .cachePublic()
        .mustRevalidate()
        .noTransform();

String headerValue = policy.getHeaderValue();
System.out.println(headerValue);
```

Giá trị header được builder tạo theo thứ tự directive tương ứng:

```text
max-age=600, must-revalidate, no-transform, public
```

Không dựa vào thứ tự directive để biểu diễn ưu tiên; ý nghĩa được xác định bởi HTTP semantics. Nếu cần directive không có method tương ứng, có thể thiết lập header thủ công sau khi kiểm tra tương thích và tránh tạo directive mâu thuẫn.

## 7. Gắn `CacheControl` vào response WebFlux

### 7.1. Annotated controller trả `ResponseEntity`

```java
@GetMapping("/catalog/{id}")
Mono<ResponseEntity<ProductView>> getProduct(@PathVariable long id) {
    return productService.findById(id)
            .map(product -> ResponseEntity.ok()
                    .cacheControl(
                            CacheControl.maxAge(Duration.ofMinutes(5))
                                    .cachePrivate()
                    )
                    .eTag(product.etag())
                    .lastModified(product.updatedAt())
                    .body(toView(product))
            );
}
```

`ResponseEntity` builder hỗ trợ `cacheControl`, `eTag` và `lastModified`. WebFlux hỗ trợ method trả `Mono<ResponseEntity<T>>`; service trả Publisher và controller không cần gọi `.block()`.

Khi có conditional request phù hợp, Spring WebFlux có thể so sánh `ETag`/`Last-Modified` với request headers và trả `304 Not Modified` với body rỗng nếu resource chưa đổi. Khi nội dung thay đổi, response thông thường trả `200` cùng validator mới.

### 7.2. Functional endpoint với `ServerResponse`

```java
Mono<ServerResponse> response =
        ServerResponse.ok()
                .cacheControl(
                        CacheControl.maxAge(Duration.ofMinutes(5))
                                .cachePublic()
                )
                .eTag("\"catalog-v4\"")
                .varyBy("Accept-Language")
                .bodyValue(catalog);
```

`cacheControl(...)` đặt `Cache-Control`; `eTag(...)` đặt validator; `varyBy(...)` thông báo header tham gia lựa chọn representation.

### 7.3. Dùng `ServerHttpResponse` trực tiếp

```java
CacheControl policy = CacheControl.noStore();

response.getHeaders().set(
        HttpHeaders.CACHE_CONTROL,
        policy.getHeaderValue()
);
```

Đoạn này chỉ chuẩn bị header. Nếu response đã commit, thay đổi header có thể không còn tác dụng. Hãy đặt cache policy trước khi bắt đầu ghi body.

## 8. `ETag`: validator theo phiên bản representation

`ETag` là entity tag nhận diện một phiên bản representation:

```http
ETag: "product-42-v7"
```

Client gửi lại trong request:

```http
If-None-Match: "product-42-v7"
```

- Nếu khớp trong conditional GET/HEAD, server có thể trả `304 Not Modified` và không gửi lại body.
- Nếu khác, server trả `200 OK`, body mới và ETag mới.

### 8.1. Strong và weak ETag

Strong ETag:

```http
ETag: "v7"
```

Weak ETag:

```http
ETag: W/"v7"
```

- Strong validator biểu thị representation tương đương ở mức byte theo semantics HTTP.
- Weak validator biểu thị nội dung tương đương về ý nghĩa nhưng không cam kết byte-for-byte giống nhau.

Với `If-None-Match` cho GET/HEAD, HTTP sử dụng weak comparison. Với precondition như `If-Match`, strong comparison có ý nghĩa quan trọng.

ETag có thể được tạo từ version number, hash của representation đã serialize, revision ID hoặc checksum ổn định. Không tạo ETag ngẫu nhiên mỗi request; nếu ETag luôn khác, client không thể revalidate thành công.

### 8.2. ETag phải đại diện đúng representation

Nếu cùng URL có nhiều representation tùy `Accept`, `Accept-Language`, `Accept-Encoding` hoặc quyền người dùng, ETag và cache key phải phản ánh sự khác nhau đó. Một ETag chung cho hai representation khác nhau có thể khiến cache tái sử dụng sai body.

`Vary` giúp cache phân biệt cache key; ETag giúp xác thực phiên bản của representation đã chọn.

## 9. `Last-Modified`: validator theo thời điểm

`Last-Modified` cho biết thời điểm resource thay đổi lần cuối:

```http
Last-Modified: Sat, 15 Mar 2025 10:00:00 GMT
```

Client có thể gửi:

```http
If-Modified-Since: Sat, 15 Mar 2025 10:00:00 GMT
```

Nếu resource chưa thay đổi kể từ thời điểm đó, server trả `304 Not Modified`.

Spring:

```java
ResponseEntity.ok()
        .lastModified(updatedAt)
        .body(resource);
```

HTTP date có độ chính xác đến giây; nếu resource thay đổi nhiều lần trong cùng một giây, timestamp có thể không phân biệt được các phiên bản. ETag thường chính xác hơn và có thể kết hợp cả hai.

## 10. Conditional request với `ServerWebExchange`

Spring WebFlux cung cấp:

```java
boolean unchanged = exchange.checkNotModified(etag);

boolean unchangedByDate =
        exchange.checkNotModified(lastModified);

boolean unchangedByBoth =
        exchange.checkNotModified(etag, lastModified);
```

`checkNotModified(...)` so sánh validator ứng dụng tính được với conditional request headers và tự chuẩn bị response status/header khi phù hợp. Nếu trả `true`, request không cần tiếp tục xử lý nội dung. Nếu trả `false`, ứng dụng tiếp tục tạo representation.

| Request precondition | Kết quả khi điều kiện phù hợp |
|---|---|
| GET/HEAD với `If-None-Match` khớp | `304 Not Modified` |
| GET/HEAD với `If-Modified-Since` phù hợp | `304 Not Modified` |
| POST/PUT/DELETE với precondition không đạt | `412 Precondition Failed` |
| Validator không khớp hoặc không có precondition | Tiếp tục xử lý |

Ví dụ khung xử lý trong annotated controller:

```java
@GetMapping("/documents/{id}/manual")
Mono<DocumentView> getDocument(
        @PathVariable long id,
        ServerWebExchange exchange) {

    return documentService.findById(id)
            .flatMap(document -> {
                String etag = document.etag();
                Instant modified = document.updatedAt();

                if (exchange.checkNotModified(etag, modified)) {
                    return Mono.empty();
                }

                return Mono.just(toView(document));
            });
}
```

Đây là mẫu minh họa cho controller trả reactive body. `checkNotModified` chuẩn bị status và headers; khi nó trả `true`, không tạo body mới. Hãy kiểm thử cách kết thúc response với kiểu return cụ thể và phiên bản Spring đang dùng. Với `ResponseEntity`, khai báo ETag và Last-Modified trên builder thường đơn giản hơn.

Tính ETag/Last-Modified cần dữ liệu metadata đáng tin cậy. Nếu phải tải toàn bộ file lớn chỉ để tính hash rồi mới quyết định 304, lợi ích có thể giảm. Có thể lưu version/checksum cùng resource để kiểm tra nhanh.

## 11. `304 Not Modified` không phải response lỗi

Một response 304:

- Không mang response body.
- Cho cache biết representation đã lưu vẫn có thể dùng.
- Có thể cập nhật metadata cache theo headers server gửi.
- Không có nghĩa resource rỗng hoặc request thất bại.

Ví dụ:

```http
HTTP/1.1 304 Not Modified
ETag: "product-42-v7"
Cache-Control: private, max-age=300
```

Client lấy body từ bản cache đã lưu. Server tiết kiệm băng thông vì không phải gửi lại representation.

Đừng trả `200 OK` với body rỗng để mô phỏng 304. Hai response có semantics khác nhau.

## 12. `Vary`: cache key phụ thuộc request header

Giả sử API trả nội dung theo ngôn ngữ:

```text
GET /help
Accept-Language: vi
```

và:

```text
GET /help
Accept-Language: en
```

Cùng URL nhưng body khác nhau. Nếu cache chỉ phân biệt theo URL, response tiếng Việt có thể bị dùng nhầm cho client tiếng Anh. Server nên gửi:

```http
Vary: Accept-Language
```

Trong WebFlux functional response:

```java
return ServerResponse.ok()
        .cacheControl(CacheControl.maxAge(Duration.ofMinutes(10)).cachePublic())
        .varyBy("Accept-Language")
        .bodyValue(translatedContent);
```

Các header thường tham gia `Vary`:

- `Accept-Language` khi nội dung theo ngôn ngữ.
- `Accept-Encoding` khi representation khác theo compression.
- `Accept` khi trả JSON, XML hoặc representation khác nhau.

Chỉ liệt kê request header thực sự làm thay đổi representation. `Vary` và authorization phải được thiết kế cùng nhau; đừng dùng cache key thay cho kiểm tra quyền.

## 13. Cache an toàn với authentication và dữ liệu cá nhân

Cache dùng chung có thể phục vụ cùng một bản response cho nhiều người dùng. Vì vậy cache policy phải tính đến authentication và authorization.

- Với response phụ thuộc user, cân nhắc `private` hoặc `no-store`.
- `private` ngăn shared cache lưu response, nhưng browser cache riêng vẫn có thể lưu.
- Nếu nội dung không được phép lưu ở bất kỳ HTTP cache nào, dùng `no-store`.
- Response có `Authorization` header chịu quy tắc cache riêng trong HTTP. Không giả định CDN sẽ lưu hoặc không lưu chỉ dựa vào URL.
- Nếu response phụ thuộc cookie/session, phải tránh dùng chung body giữa các session. Với nội dung cá nhân hóa, `private` hoặc `no-store` thường rõ ràng hơn.

Không dùng `public` chỉ để tăng cache hit ratio. Cache policy không thay thế authentication, authorization, tenant isolation hoặc kiểm soát truy cập ở server.

## 14. Cache static resources trong WebFlux

Static resources như CSS, JavaScript và ảnh thường có chiến lược cache khác API động:

```java
@Configuration
class StaticResourceConfig implements WebFluxConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/static/assets/")
                .setCacheControl(
                        CacheControl.maxAge(Duration.ofDays(365))
                                .cachePublic()
                                .immutable()
                );
    }
}
```

Đây là cấu hình minh họa cho ứng dụng WebFlux. Cách dùng phù hợp khi URL asset chứa version/hash và nội dung không bị ghi đè dưới cùng URL.

Chiến lược frontend thường gặp:

- File versioned/hash: cache lâu và `immutable`.
- HTML entry point: cache ngắn hoặc revalidate để nhận manifest/asset version mới.
- API dynamic: policy theo quyền truy cập và mức chấp nhận stale.

Nếu static resources được phục vụ qua CDN, cần đồng bộ cache headers ở origin và cấu hình CDN; kiểm tra xem CDN có override policy hay không.

## 15. HTTP cache khác Spring Cache, Caffeine và Redis

| Cơ chế | Cache ở đâu? | Đối tượng lưu | Điều khiển bằng |
|---|---|---|---|
| HTTP browser cache | Thiết bị client | HTTP response | `Cache-Control`, ETag, Last-Modified, Vary |
| Reverse proxy/CDN | Hạ tầng trung gian | HTTP response | HTTP headers và cấu hình CDN |
| Spring Cache | Trong ứng dụng hoặc provider | Kết quả method | `@Cacheable`, `@CacheEvict`, `CacheManager` |
| Caffeine | Bộ nhớ JVM | Object/value | TTL, size, eviction |
| Redis | Cache ngoài ứng dụng | Key/value | TTL, key policy, eviction |

`@Cacheable("products")` có thể tránh truy vấn database lặp lại trong service. `CacheControl.maxAge(...)` hướng dẫn browser/proxy lưu response. Hai cơ chế có thể kết hợp nhưng cần chiến lược invalidation nhất quán.

HTTP cache không tự tạo application cache. Application cache tốt cũng không tự làm browser nhận 304.

## 16. Cache invalidation khi dữ liệu thay đổi

Một chiến lược cache cần trả lời: khi resource được cập nhật, cache cũ được phát hiện và loại bỏ thế nào?

1. **TTL ngắn:** cache tự hết freshness sau khoảng thời gian nhất định. Dễ triển khai nhưng chấp nhận stale trong TTL.
2. **Validator:** ETag/Last-Modified cho phép cache hỏi origin khi stale.
3. **Versioned URL:** nội dung đổi thì URL đổi; phù hợp static assets.
4. **CDN purge:** ứng dụng/deployment gửi lệnh xóa cache theo URL hoặc tag theo tính năng CDN.
5. **Cache key có version:** version mới tạo key mới; bản cũ tự hết hạn.

HTTP caching có quy tắc invalidation sau một số request method không an toàn thành công đối với URI đích, nhưng không nên dựa vào đó để xóa mọi bản cache ở mọi URL hoặc mọi CDN. Nếu cùng dữ liệu xuất hiện ở nhiều endpoint, cần chiến lược purge/version rõ ràng.

Ví dụ sản phẩm đổi tên:

- ETag cũ: `"product-42-v7"`.
- ETag mới: `"product-42-v8"`.
- Client gửi `If-None-Match: "product-42-v7"`.
- Server thấy không khớp, trả `200` và ETag mới cùng body.

## 17. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ tạo endpoint `GET /assets/{id}`. Tài nguyên demo có version cố định để dễ quan sát:

- Response đầu tiên trả `200 OK`, `Cache-Control`, `ETag` và `Last-Modified`.
- Request tiếp theo gửi `If-None-Match` với ETag cũ.
- Spring WebFlux nhận ra resource chưa đổi và trả `304 Not Modified` không có body.

### Cấu trúc thư mục

```text
http-cache-demo/
├── pom.xml
└── src/main/java/demo/Main.java
```

### File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>http-cache-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

### File `src/main/java/demo/Main.java`

```java
package demo;

import java.time.Duration;
import java.time.Instant;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class Main {

    public static void main(String[] args) {
        SpringApplication.run(Main.class, args);
    }
}

@RestController
@RequestMapping("/assets")
class AssetController {

    private static final Asset ASSET = new Asset(
            42L,
            "Spring WebFlux Guide",
            "\"asset-v3\"",
            Instant.parse("2025-03-15T10:00:00Z")
    );

    @GetMapping("/{id}")
    Mono<ResponseEntity<AssetView>> get(@PathVariable long id) {
        if (id != ASSET.id()) {
            return Mono.just(notFound());
        }

        AssetView view = new AssetView(
                ASSET.id(),
                ASSET.name(),
                "v3"
        );

        return Mono.just(
                ResponseEntity.ok()
                        .cacheControl(
                                CacheControl.maxAge(Duration.ofMinutes(1))
                                        .cachePrivate()
                        )
                        .eTag(ASSET.etag())
                        .lastModified(ASSET.updatedAt())
                        .body(view)
        );
    }

    private ResponseEntity<AssetView> notFound() {
        return ResponseEntity.status(404).build();
    }

    record Asset(
            long id,
            String name,
            String etag,
            Instant updatedAt
    ) {}

    record AssetView(long id, String name, String version) {}
}
```

Từ thư mục dự án, cần JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

### Request lần đầu

```bash
curl -i http://localhost:8080/assets/42
```

Các phần quan trọng của response:

```http
HTTP/1.1 200 OK
Cache-Control: max-age=60, private
ETag: "asset-v3"
Last-Modified: Sat, 15 Mar 2025 10:00:00 GMT
Content-Type: application/json

{"id":42,"name":"Spring WebFlux Guide","version":"v3"}
```

Các header phụ như `Date` hoặc `Content-Length` có thể khác theo runtime/server.

### Request có validator

```bash
curl -i \
  -H 'If-None-Match: "asset-v3"' \
  http://localhost:8080/assets/42
```

Response mong đợi:

```http
HTTP/1.1 304 Not Modified
Cache-Control: max-age=60, private
ETag: "asset-v3"
Last-Modified: Sat, 15 Mar 2025 10:00:00 GMT
```

Response 304 không có JSON body. Client sử dụng body đã lưu từ lần 200 trước.

**Đọc chương trình:**

1. `Asset` giữ ID, nội dung, ETag và thời điểm cập nhật.
2. `ResponseEntity.ok()` chọn status 200 cho representation hiện tại.
3. `.cacheControl(...)` đặt policy private với freshness 60 giây.
4. `.eTag(...)` và `.lastModified(...)` công bố hai validator.
5. Khi request mang `If-None-Match` phù hợp, WebFlux có thể trả 304 và bỏ qua body.
6. Method trả `Mono<ResponseEntity<AssetView>>`; không gọi `.block()` hoặc `.subscribe()` trong controller.

Ví dụ cố định version để response dễ dự đoán. Trong ứng dụng thực tế, ETag và `updatedAt` phải lấy từ version/timestamp đáng tin cậy của dữ liệu.

## 18. Kiểm thử conditional caching bằng `WebTestClient`

Có thể kiểm tra status và validator mà không mở cổng TCP:

```java
WebTestClient client = WebTestClient
        .bindToController(new AssetController())
        .build();

client.get()
        .uri("/assets/42")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
                "Cache-Control", "max-age=60, private"
        )
        .expectHeader().valueEquals("ETag", "\"asset-v3\"")
        .expectBody()
        .jsonPath("$.id").isEqualTo(42);

client.get()
        .uri("/assets/42")
        .header("If-None-Match", "\"asset-v3\"")
        .exchange()
        .expectStatus().isNotModified()
        .expectBody().isEmpty();
```

Đây là đoạn test cần `spring-test` (thường có qua `spring-boot-starter-test`) và import `WebTestClient`. Nếu test bằng `bindToController`, hãy bảo đảm controller có các dependency cần thiết hoặc dùng fixture phù hợp.

Các test nên bổ sung:

- ETag cũ không khớp thì nhận `200` với ETag mới.
- `If-Modified-Since` phù hợp thì nhận `304`.
- Request không có validator vẫn nhận representation.
- Resource không tồn tại trả `404`.
- Response cá nhân không bị cấu hình thành `public`.
- `Vary` phân biệt representation theo header liên quan.

## 19. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `no-cache` với ý nghĩ cấm lưu hoàn toàn | Cache vẫn có thể lưu body và revalidate | Dùng `no-store` khi không muốn cache lưu |
| Dùng `public` cho response cá nhân hóa | Shared cache có nguy cơ phục vụ nhầm dữ liệu | Dùng `private` hoặc `no-store` |
| Đặt `max-age` quá dài cho URL không version | Client giữ nội dung cũ sau deployment | Dùng versioned URL hoặc TTL ngắn |
| Chỉ đặt `Cache-Control` nhưng không có validator | Khi stale, server thường phải gửi lại body đầy đủ | Thêm ETag/Last-Modified khi phù hợp |
| ETag thay đổi mỗi request | Không có cơ hội trả 304 hiệu quả | Dùng version/hash ổn định |
| ETag không phản ánh representation | Cache có thể tái sử dụng body không đúng | Tính validator theo đúng representation |
| Bỏ `Vary` khi body phụ thuộc `Accept-Language` | Cache có thể dùng nhầm ngôn ngữ | Gửi `Vary: Accept-Language` |
| Coi `CacheControl` là Redis/Caffeine | Dữ liệu không được cache trong JVM như mong đợi | Dùng Spring Cache hoặc cache provider |
| Nghĩ `304` phải có body JSON rỗng | Sai semantics HTTP | 304 không có representation body; client dùng bản cache |
| Dùng `Last-Modified` cho dữ liệu đổi nhiều lần trong một giây | Timestamp có thể không phân biệt phiên bản | Dùng ETag hoặc kết hợp validator |
| Dùng `immutable` cho URL cố định bị ghi đè | Client có thể giữ bản cũ lâu | Chỉ dùng với URL versioned |
| Bỏ qua cache key và quyền truy cập | Rò dữ liệu giữa user/tenant | Thiết kế `private`, `Vary` và authorization đúng |
| Dùng cache header để thay authentication | Người không có quyền vẫn có thể gọi origin | Luôn kiểm tra authorization tại server |
| Chỉ test endpoint bằng một request 200 | Không phát hiện lỗi conditional request | Test `If-None-Match`, `If-Modified-Since` và 304 |
| Coi CDN luôn tuân theo origin | CDN có thể có rule override hoặc cache key riêng | Kiểm tra cấu hình CDN và response thực tế |

## 20. Checklist thiết kế chiến lược cache

1. Response công khai hay phụ thuộc user, tenant, role hoặc cookie?
2. Dữ liệu có thể stale trong bao lâu mà vẫn chấp nhận được?
3. Có nên cho cache lưu body không, hay cần `no-store`?
4. Nên dùng `max-age`, `no-cache` hay `no-store`?
5. Shared cache có được phép lưu không? Có cần `private`, `public` hoặc `s-maxage`?
6. Có ETag hoặc Last-Modified ổn định không?
7. Representation thay đổi theo `Accept`, `Accept-Language` hoặc `Accept-Encoding` không? Có cần `Vary`?
8. URL có version/hash để dùng `immutable` không?
9. Khi dữ liệu thay đổi, TTL, validator, versioned URL hay CDN purge sẽ cập nhật cache?
10. Conditional request có trả đúng 304/412 và không gửi body không cần thiết?
11. Response có token, dữ liệu nhạy cảm hoặc thông tin cá nhân không?
12. Có integration test kiểm tra headers và cache behavior qua proxy/CDN thực tế không?

## 21. Bài tập tự kiểm tra

**Câu 1.** `CacheControl.maxAge(Duration.ofMinutes(5))` tạo directive nào?

**Đáp án:** `max-age=300`. Cache có thể coi response fresh trong 300 giây theo HTTP caching rules.

**Câu 2.** `no-cache` và `no-store` khác nhau thế nào?

**Đáp án:** `no-cache` cho phép lưu nhưng yêu cầu revalidate trước khi dùng lại; `no-store` yêu cầu cache không lưu response.

**Câu 3.** `private` có ngăn browser lưu response không?

**Đáp án:** Không. Nó ngăn shared cache lưu response; private cache của user vẫn có thể lưu.

**Câu 4.** Vì sao response thay đổi theo `Accept-Language` cần `Vary: Accept-Language`?

**Đáp án:** Để cache phân biệt representation theo request header và không dùng nội dung của ngôn ngữ này cho request ngôn ngữ khác.

**Câu 5.** Khi `If-None-Match` khớp ETag hiện tại trong GET, server có thể trả gì?

**Đáp án:** `304 Not Modified` không có body; client dùng representation đã cache.

**Câu 6.** ETag có thể lấy từ version của bản ghi không?

**Đáp án:** Có, nếu version thay đổi mỗi khi representation liên quan thay đổi và đủ ổn định để nhận diện đúng phiên bản.

**Câu 7.** `immutable` có phù hợp với `/app.js` bị ghi đè mỗi lần deploy không?

**Đáp án:** Không. Dùng URL chứa content hash/version để nội dung mới có URL mới.

**Câu 8.** `CacheControl` có tự lưu response vào Redis không?

**Đáp án:** Không. Nó tạo HTTP response header; Redis/Spring Cache là application caching riêng.

**Câu 9.** Nếu endpoint trả dữ liệu cá nhân cho user đăng nhập, có nên dùng `public` không?

**Đáp án:** Không theo mặc định. Dùng private hoặc no-store tùy mức độ nhạy cảm và chính sách bảo mật.

**Câu 10.** `304 Not Modified` có nghĩa resource không tồn tại không?

**Đáp án:** Không. Nó có nghĩa representation mà client đã lưu vẫn phù hợp; 304 không mang body mới.

## 22. Quy tắc áp dụng

- Dùng `CacheControl` để tạo `Cache-Control` response header; đừng nhầm nó với application cache.
- Chọn `no-store` khi response không được lưu; chọn `no-cache` khi có thể lưu nhưng phải revalidate.
- Dùng `private` cho response theo user; chỉ dùng `public` khi shared cache được phép lưu.
- Đặt `max-age` theo mức chấp nhận stale; dùng `s-maxage` khi cần freshness riêng cho shared cache.
- Kết hợp `ETag` hoặc `Last-Modified` để conditional request có thể trả 304.
- Dùng `Vary` khi representation phụ thuộc request headers.
- Chỉ dùng `immutable` với URL versioned/hash.
- Kiểm thử status, headers, body và cache behavior qua `WebTestClient` và hạ tầng CDN thực tế.

**Ghi nhớ:** `Cache-Control` quyết định cache được lưu và tái sử dụng response thế nào; ETag/Last-Modified giúp xác thực representation; `Vary` giúp cache phân biệt các biến thể. `CacheControl` trong Spring WebFlux là builder cho HTTP response policy, không phải bộ lưu trữ dữ liệu của ứng dụng.

## 23. Tài liệu tham khảo chính thức

- [Spring Framework — HTTP Caching trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/caching.html)
- [Spring Framework 6.1 — `CacheControl` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/CacheControl.html)
- [Spring Framework 6.1 — `ServerWebExchange` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/server/ServerWebExchange.html)
- [Spring Framework 6.1 — `ServerResponse.HeadersBuilder` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.HeadersBuilder.html)
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 8246 — Immutable HTTP Responses](https://www.rfc-editor.org/rfc/rfc8246)
