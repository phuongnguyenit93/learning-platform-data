# Phân biệt bộ nhớ đệm HTTP với Spring Cache ở tầng nghiệp vụ

> **Ngữ cảnh:** Spring Boot web-runtime, trong chủ đề “Cache và nén HTTP”. Bài học giải thích hai loại cache dễ bị nhầm trong ứng dụng Java: **HTTP caching** ở trình duyệt/proxy/CDN và **Spring Cache** ở service/repository. Ví dụ dùng Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+ với Spring MVC; phần cuối chỉ rõ điểm khác khi triển khai Spring WebFlux. Các giá trị TTL trong ví dụ chỉ dành cho thực hành.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Chỉ ra **cache nằm ở đâu**, **đang lưu đối tượng gì** và **khi nào có thể bỏ qua tầng ứng dụng** trong một request.
2. Giải thích các chỉ thị HTTP `Cache-Control`: `max-age`, `s-maxage`, `public`, `private`, `no-cache`, `no-store`, `must-revalidate` và `Vary` theo RFC 9111.
3. Phân biệt **fresh response** được tái sử dụng ngay với **conditional GET** dùng `If-None-Match` / `ETag` hoặc `If-Modified-Since` / `Last-Modified` có thể nhận `304 Not Modified`.
4. Dùng Spring Cache với `@EnableCaching`, `@Cacheable`, `@CacheEvict`, `@CachePut` và một `CacheManager`, hiểu cache key, TTL, invalidation, cache stampede và giới hạn proxy.
5. Hiểu vì sao cache business hit **không đồng nghĩa** HTTP cache hit, và việc xóa Spring Cache **không tự xóa** browser/CDN cache.
6. Chạy ứng dụng Spring MVC Java 17+ có cả hai tầng cache; kiểm tra service load count, ETag và thay đổi dữ liệu qua `curl`.
7. Thiết kế đúng cache cho nội dung công khai, nội dung cá nhân, dữ liệu thay đổi thường xuyên, tài nguyên tĩnh nén gzip/br, đồng thời đo hiệu quả và tránh trả dữ liệu cũ.

## 2. Hai cache ở hai vị trí khác nhau

Tưởng tượng client truy cập `GET /products/1`. Có thể có **cache ở bên ngoài app** và **cache bên trong app**:

~~~text
Browser
  |  (1) browser HTTP cache: có response fresh?
  |
  v
CDN / reverse proxy / shared HTTP cache
  |  (2) CDN cache: có representation hợp lệ?
  |
  v
Spring Boot HTTP server / Controller
  |  (3) controller xử lý HTTP request
  v
@Service / @Cacheable
  |  (4) business cache: có Product(id=1)?
  |
  v
Database / downstream API
~~~

- **HTTP cache** giữ một hoặc nhiều *HTTP response representations* cùng metadata của chúng (status, response headers, validators và body theo cách triển khai). Client/CDN quyết định có thể dùng lại hay phải hỏi origin, dựa trên HTTP semantics và chính sách.
- **Spring Cache** giữ *kết quả một phép gọi method* trong `Cache` do `CacheManager` quản lý, thường theo cache name + key. Đây có thể là một `Product`, DTO, danh sách hoặc kết quả tính toán; nó không mặc định giữ nguyên HTTP status, ETag, Content-Type và body representation.
- **HTTP cache hit hợp lệ** có thể ngăn request đi tới Spring Boot, nên controller/service/database **đều không chạy** cho request đó.
- **Spring Cache hit** chỉ xảy ra **khi request đã tới ứng dụng** và một lời gọi đi qua proxy caching của Spring. Controller, authorization, serialization, response filters và network vẫn có thể thực thi.

Ví dụ: trình duyệt đang giữ `200 OK` của `/products/1` còn fresh 30 giây. Lần GET tiếp theo có thể dùng lại body ngay tại browser, không gọi server. Khi hết freshness, browser có thể gửi GET với `If-None-Match`. Request này tới server, controller đọc Product từ Spring Cache để tính validator; nếu không đổi, server trả `304` và browser dùng lại body đã lưu. Hai tầng cache cùng phối hợp nhưng **không có cơ chế tự động đồng bộ thời hạn hay invalidation**.

### Bảng đối chiếu nhanh

| Tiêu chí | HTTP cache | Spring Cache ở tầng nghiệp vụ |
|---|---|---|
| Nơi thực thi | Browser, CDN, reverse proxy, HTTP client hoặc cache HTTP khác | Trong ứng dụng qua Spring cache abstraction và provider |
| Đơn vị lưu | HTTP response/representation kèm metadata giao thức | Kết quả lời gọi method, theo cache name và key |
| Khóa | URI/method, cùng các dimension do `Vary` và cache implementation xét đến | Cache name + key do `KeyGenerator`/SpEL |
| Điều khiển | `Cache-Control`, `ETag`, `Last-Modified`, `Vary`, quy tắc RFC | `@Cacheable`, `@CacheEvict`, `@CachePut`, `CacheManager`, TTL provider |
| Tránh phần việc nào? | Có thể tránh request tới origin, truyền body và toàn bộ xử lý server | Có thể tránh truy vấn DB/HTTP downstream hoặc tính toán trong method |
| Thời hạn | HTTP freshness như `max-age`, `s-maxage`, revalidation | TTL/TTI/size/eviction theo Redis/Caffeine/provider hoặc logic ứng dụng |
| Xóa/chỉnh cache | Theo HTTP rules, purge CDN, đổi URL, revalidation hoặc chính sách khác | Evict/update key, expire TTL hoặc invalidation event |
| Rủi ro điển hình | Trả response cũ, cache dữ liệu cá nhân ở shared cache, thiếu `Vary` | Key thiếu tenant/user, dữ liệu cũ, cache stampede, memory exhaustion |
| Mối quan hệ với nén | Representation có thể khác theo `Accept-Encoding` và `Vary` | Kết quả domain object thường chưa phải HTTP bytes nén |

**Kết luận quan trọng:** Hai cơ chế cùng gọi là “cache” nhưng tối ưu hóa các đoạn khác nhau trong hành trình request. Chúng có thể được bật độc lập hoặc kết hợp.

## 3. HTTP cache lưu gì, và ai được dùng lại?

RFC 9111 mô tả HTTP cache là nơi lưu response và các quy tắc sử dụng lại. Cần phân biệt:

- **Private cache:** dành cho một người dùng, ví dụ cache của một trình duyệt.
- **Shared cache:** phục vụ nhiều người dùng, ví dụ CDN hoặc proxy cache.
- **Origin server:** server nguồn tạo response (Spring Boot hoặc một hệ thống phía sau gateway).

Một response chỉ nên được coi là cacheable khi đáp ứng điều kiện của RFC, không chỉ vì app trả `200`. Phương thức request, status, directive, Authorization, metadata và chính sách cache đều ảnh hưởng. Ví dụ response GET công khai có `Cache-Control: public, max-age=60` thường có thể được HTTP cache lưu, nhưng không hứa mọi browser/proxy bắt buộc lưu: cache có quyền và điều kiện triển khai riêng.

### Khi response còn fresh

~~~http
GET /products/1 HTTP/1.1
Host: api.example.test

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=60
ETag: W/"product-1-v4"

{"id":1,"name":"Sổ tay","version":4}
~~~

Trong 60 giây theo freshness semantics (có thể tính cả `Age`, thời điểm lưu, policy và các yếu tố khác), HTTP cache đủ điều kiện có thể dùng lại representation mà **không cần liên hệ origin**. Tầng Spring Cache bên trong không nhận lượt gọi tương ứng.

### Khi representation stale và cần revalidate

~~~http
GET /products/1 HTTP/1.1
Host: api.example.test
If-None-Match: W/"product-1-v4"

HTTP/1.1 304 Not Modified
ETag: W/"product-1-v4"
Cache-Control: public, max-age=60
~~~

`304 Not Modified` không chứa representation body để thay thế; client giữ nội dung cũ và cập nhật metadata theo quy tắc HTTP. **304 không phải Spring Cache hit.** 304 là một kết quả giao thức trả về từ origin hoặc cache trung gian khi validator khớp; Spring Cache có thể hỗ trợ server xác định version mà không truy vấn DB.

Nếu resource đã đổi, server thường trả `200 OK` với body mới và ETag mới, chứ không trả 304.

### Vary làm thay đổi cách dùng lại representation

Nếu response thay đổi theo ngôn ngữ:

~~~http
Vary: Accept-Language
~~~

cache phải xem request header đó khi chọn representation được lưu. Nếu response khác theo gzip hoặc Brotli:

~~~http
Vary: Accept-Encoding
~~~

cache phải phân biệt khả năng mã hóa của client theo Vary. Bỏ `Vary` có thể khiến cache gửi sai ngôn ngữ hoặc mã hóa cho một client. `Vary` **không thay thế** bảo vệ dữ liệu cá nhân: response dành riêng user nên thường dùng `private` hoặc `no-store` tùy mức nhạy cảm.

## 4. Đọc chính xác Cache-Control và validator

| Directive/header | Ý nghĩa thực tế | Lỗi hiểu thường gặp |
|---|---|---|
| `max-age=60` | Response fresh tối đa theo freshness lifetime 60 giây (kèm quy tắc Age và cache policy). | Tưởng origin tự khóa dữ liệu 60 giây hoặc DB cache có TTL 60 giây. |
| `s-maxage=120` | Freshness riêng của **shared cache**, ưu tiên hơn max-age cho shared caches theo RFC. | Tưởng browser private cache cũng buộc dùng 120 giây. |
| `public` | Cho phép shared cache lưu trong các trường hợp RFC cho phép; thường dùng nội dung công khai. | Gắn vào response chứa dữ liệu user/token để “tăng tốc CDN”. |
| `private` | Shared cache không được lưu response theo nghĩa directive không tham số; private cache có thể lưu nếu các điều kiện khác đáp ứng. | Nghĩ private là mã hóa hoặc cơ chế bảo mật dữ liệu. |
| `no-cache` | Cache có thể lưu nhưng **phải revalidate thành công** trước khi dùng lại response. | Nghĩ no-cache luôn tương đương “cấm lưu” (sai). |
| `no-store` | Cache tuân thủ không được lưu request/response theo quy tắc directive; phù hợp dữ liệu rất nhạy cảm. | Nghĩ bảo đảm xóa mọi bản sao cũ ở mọi hệ thống (không bảo đảm). |
| `must-revalidate` | Khi stale, cache không được tự dùng lại trong những trường hợp không đủ điều kiện; cần revalidate theo RFC. | Nghĩ luôn phải gọi server ngay cả khi response còn fresh. |
| `ETag` | Validator cho một representation (strong/weak), thường dùng If-None-Match. | Coi ETag là TTL hoặc luôn là checksum byte mạnh. |
| `Last-Modified` | Thời điểm sửa được origin xác định, có thể dùng với If-Modified-Since. | Coi timestamp chính xác tuyệt đối mọi thay đổi trong cùng giây. |
| `Vary` | Chỉ ra các request header cần được cache xem khi chọn representation. | Dùng Vary như giải pháp tự động tách tenant/user an toàn. |
| `Age` | Thông tin tuổi response trong cache, ảnh hưởng cách tính freshness. | Lấy max-age trừ thời gian trên đồng hồ client mà bỏ qua Age. |

Ngoài các directive trên, HTTP cache còn có heuristic freshness, status/method-specific rules, `immutable`, stale controls và proxy-specific policy. Với dữ liệu nghiệp vụ quan trọng, **đặt chính sách rõ** thay vì phụ thuộc heuristic.

### ETag mạnh và ETag yếu

- **Strong ETag**, ví dụ `"abc123"`, có ngữ nghĩa mạnh về representation bytes theo quy tắc validator. Nếu representation nén gzip khác bản identity, không được sử dụng cùng strong validator tùy tiện như thể bytes hoàn toàn giống nhau.
- **Weak ETag**, ví dụ `W/"product-1-v4"`, biểu thị nội dung có thể coi là tương đương về ngữ nghĩa cho revalidation, nhưng không đủ mạnh cho một số thao tác đòi byte-range consistency hoặc optimistic concurrency dựa trên strong comparisons.
- HTTP `If-None-Match` với GET dùng phép so khớp phù hợp cho conditional retrieval, nên weak ETag là lựa chọn hợp lý khi validator gắn với **business version** thay vì hash chính xác response bytes.
- HTTP `If-Match` dành cho điều kiện cập nhật có ngữ nghĩa strong comparison; nếu dùng optimistic concurrency thực, thiết kế validator mạnh/version contract riêng.

`ETag` và `Last-Modified` có thể cùng xuất hiện; khi request có `If-None-Match`, HTTP có quy tắc ưu tiên so với `If-Modified-Since`. Không tự viết logic xử lý như “nếu một trong hai bằng thì 304” mà bỏ quy tắc giao thức.

## 5. Spring MVC tạo Cache-Control, ETag và 304

Spring Framework có `CacheControl`, `ResponseEntity` và `WebRequest.checkNotModified(...)` giúp ứng dụng làm việc với HTTP validators. Ví dụ một endpoint tạo response:

~~~java
CacheControl policy =
        CacheControl.maxAge(java.time.Duration.ofSeconds(30))
                    .cachePublic();

return ResponseEntity.ok()
        .cacheControl(policy)
        .eTag("W/\"product-1-v4\"")
        .body(product);
~~~

Đoạn trên chỉ là **mảnh controller**, với `product` đã được tạo trước. `CacheControl` thiết lập response header; `eTag` đặt validator; khi framework xử lý conditional request tương ứng, response có thể được chuyển thành 304 theo điều kiện HTTP. Với mã cần điều khiển rõ việc tạo body và trả về, controller cũng có thể dùng `WebRequest.checkNotModified(etag)` để dừng trước khi render.

Một số API HTTP caching không yêu cầu `@EnableCaching`. `@EnableCaching` kích hoạt **Spring method caching**, hoàn toàn khác với việc cấu hình response HTTP.

### ShallowEtagHeaderFilter không phải business cache

`ShallowEtagHeaderFilter` có thể tạo ETag “shallow” dựa trên nội dung response sau khi đã render, để client revalidate và tiết kiệm **băng thông** khi body không đổi. Nó không tự bảo đảm tránh controller/service/DB làm việc hoặc loại bỏ chi phí render/serialize response, và có thể đệm nội dung để tính ETag. Khi body lớn/streaming, cần đánh giá chi phí bộ đệm và độ tương thích trước khi thêm filter.

Nếu app có sẵn **version/updatedAt** tin cậy, kiểm tra conditional request sớm có thể tránh phần xử lý/serialization không cần thiết. Nhưng nếu phải gọi DB để lấy version, có thể vẫn có chi phí origin; đó là nơi Spring Cache hoặc dữ liệu metadata nhẹ hỗ trợ.

## 6. Spring Cache là abstraction của lời gọi method

Spring Framework định nghĩa cache abstraction theo cache name/key và `CacheManager`. Nó **không bắt buộc** một provider cụ thể và không tự quyết định TTL hay hệ phân tán. Các annotation chính:

| Annotation | Hành vi | Dùng khi |
|---|---|---|
| `@Cacheable` | Tra cache trước; khi hit có thể trả giá trị lưu sẵn, không chạy method; khi miss thực thi và lưu kết quả theo quy tắc. | Đọc product, cấu hình, danh mục hoặc tính toán đắt tiền. |
| `@CacheEvict` | Xóa một entry hoặc toàn bộ entries theo key/cache; mặc định sau method thực thi thành công. | Cập nhật/xóa dữ liệu làm kết quả đọc cũ không còn hợp lệ. |
| `@CachePut` | Vẫn chạy method và đặt kết quả mới vào cache, không bỏ qua method. | Cập nhật cache cùng mutation khi key và result nhất quán. |
| `@Caching` | Gộp nhiều cache operation trên method. | Một mutation ảnh hưởng nhiều cache/key. |
| `@CacheConfig` | Đặt cấu hình cache chung ở cấp class. | Nhiều method dùng cache name/key generator tương tự. |
| `@EnableCaching` | Bật infrastructure diễn giải các cache annotations. | Cấu hình application. |

`@Cacheable` không có nghĩa “cache mọi HTTP GET”. Cache chỉ được đọc khi **đúng method annotation** được gọi qua cơ chế Spring hỗ trợ. Một HTTP request có thể gọi nhiều method đã cache, hoặc không gọi method cache nào.

### Cache provider và CacheManager

Spring Cache hỗ trợ các backend khác nhau. Ví dụ thường gặp:

- **Simple/ConcurrentMapCacheManager:** lưu trong map bộ nhớ nội bộ JVM. Dễ học nhưng không có TTL/size cap tích hợp như Caffeine, không chia sẻ giữa replicas, mất khi restart.
- **Caffeine:** in-process cache có giới hạn kích thước, expiration và thống kê theo cấu hình. Phù hợp dữ liệu đọc nhiều, không yêu cầu đồng bộ ngay giữa các replicas; cần cơ chế invalidation nếu có nhiều instance.
- **Redis:** kho cache bên ngoài có thể chia sẻ giữa service instances, TTL, network cost và consistency/invalidation theo thiết kế.
- **JCache hoặc provider khác:** hỗ trợ tùy classpath/cấu hình, không suy ra cùng một TTL semantics cho mọi provider.

Spring Boot có cache auto-configuration khi infrastructure cần thiết tồn tại. Trong một project có `spring-boot-starter-cache` và `@EnableCaching`, nếu không có provider đặc biệt/CacheManager user-defined, Boot có thể chọn simple cache manager cho demo. Khi thêm Caffeine/Redis, Boot có quy tắc phát hiện provider và cấu hình riêng. **Đừng mặc định rằng `@Cacheable` tự có TTL 60 giây.**

### Cache key là dữ liệu nghiệp vụ, không phải HTTP URL

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product findProduct(long id) { ... }
~~~

`#p0` là tham số thứ nhất (id). Khóa thực tế ở đây là cache `products` + product id. Với user-scoped data:

~~~java
@Cacheable(cacheNames = "accountPreferences",
           key = "#p0 + ':' + #p1")
public Preferences preferences(String tenantId, String userId) {
    // Chỉ là minh họa; Preferences và repository do ứng dụng định nghĩa.
    return repository.loadPreferences(tenantId, userId);
}
~~~

Nếu key chỉ chứa `userId` trong hệ multi-tenant có IDs trùng nhau, có nguy cơ trả dữ liệu của tenant khác. Nếu kết quả phụ thuộc currency, locale, pricing group, permissions hay version, những dimension đó cũng phải được xem xét. Không dùng toàn bộ authentication token làm key/log.

## 7. Ví dụ chạy được: Spring Cache và HTTP Cache cùng một Spring Boot app

Ứng dụng lab sau cung cấp:

- `GET /products/1`: response công khai có `Cache-Control: public, max-age=30` và weak `ETag` dựa trên version; gọi service `@Cacheable`.
- `GET /debug/load-count`: xem số lần method thực sự đọc “database” giả lập, response đặt `no-store`.
- `PUT /products/1?name=TenMoi`: cập nhật dữ liệu, tăng version và `@CacheEvict` entry của Spring Cache.
- Không cần DB thực: `ConcurrentHashMap` đóng vai trò storage để minh họa. Trong hệ thống thật, phép query chậm là lý do cache kết quả method.

### 7.1. Dependencies và project

Cần một dự án **Spring Boot 3.3, Java 17+**, đã cấu hình Gradle Spring Boot plugin, repositories, dependency management. Thêm vào `build.gradle` (Groovy DSL):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

Đây là đoạn dependencies, **không phải toàn bộ build script**. Không thêm cache provider khác trong lab để giữ hành vi simple cache. Trong dự án đã thêm Redis hoặc Caffeine, auto-config có thể chọn provider khác, nên tạo project test độc lập nếu muốn đúng kết quả.

### 7.2. Tạo một file Java hoàn chỉnh

Đặt `src/main/java/example/twocaches/TwoCachesApplication.java`:

~~~java
package example.twocaches;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableCaching
public class TwoCachesApplication {
    public static void main(String[] args) {
        SpringApplication.run(TwoCachesApplication.class, args);
    }

    public record Product(long id, String name, long version) { }

    @Service
    public static class CatalogService {
        // Storage giả lập: không phải cache của Spring.
        private final Map<Long, Product> database =
                new ConcurrentHashMap<>();
        private final AtomicInteger loads = new AtomicInteger();

        public CatalogService() {
            database.put(1L, new Product(1L, "Sổ tay", 1L));
        }

        @Cacheable(cacheNames = "products", key = "#p0")
        public Product find(long id) {
            Product result = database.get(id);
            if (result == null) {
                throw new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Unknown product");
            }
            loads.incrementAndGet();
            return result;
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public Product rename(long id, String newName) {
            return database.compute(id, (key, previous) -> {
                if (previous == null) {
                    throw new ResponseStatusException(
                            HttpStatus.NOT_FOUND, "Unknown product");
                }
                return new Product(
                        previous.id(), newName,
                        previous.version() + 1);
            });
        }

        public int loadCount() {
            return loads.get();
        }
    }

    @RestController
    public static class CatalogController {
        private final CatalogService service;

        public CatalogController(CatalogService service) {
            this.service = service;
        }

        @GetMapping("/products/{id}")
        public ResponseEntity<Product> get(
                @PathVariable long id,
                WebRequest request) {

            Product product = service.find(id);

            // Weak ETag phản ánh version nghiệp vụ, không khẳng định
            // từng byte JSON sau content negotiation là bất biến.
            String etag = "W/\"product-" + product.id()
                    + "-v" + product.version() + "\"";

            CacheControl policy = CacheControl
                    .maxAge(Duration.ofSeconds(30))
                    .cachePublic();

            if (request.checkNotModified(etag)) {
                return ResponseEntity
                        .status(HttpStatus.NOT_MODIFIED)
                        .cacheControl(policy)
                        .eTag(etag)
                        .build();
            }
            return ResponseEntity.ok()
                    .cacheControl(policy)
                    .eTag(etag)
                    .body(product);
        }

        @GetMapping("/debug/load-count")
        public ResponseEntity<Map<String, Integer>> count() {
            return ResponseEntity.ok()
                    .cacheControl(CacheControl.noStore())
                    .body(Map.of("loads", service.loadCount()));
        }

        @PutMapping("/products/{id}")
        public ResponseEntity<Product> rename(
                @PathVariable long id,
                @RequestParam String name) {

            if (name.isBlank()) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "Blank name");
            }
            Product updated = service.rename(id, name);
            return ResponseEntity.ok()
                    .cacheControl(CacheControl.noStore())
                    .body(updated);
        }
    }
}
~~~

**Vì sao class có thể chạy trên Java 17?** Code dùng Java records, `Map.of`, `ConcurrentHashMap`, `AtomicInteger`, `Duration` và Spring Boot APIs tương ứng. Nested classes là `static`; `CatalogService` là Spring `@Service` được controller inject bằng constructor, giúp lời gọi `service.find(...)` và `service.rename(...)` đi qua Spring proxy caching. Không gọi các method cache từ chính instance `CatalogService` bằng `this.find(...)`.

`@EnableCaching` đặt trên application class kích hoạt cache interception. Nếu không có CacheManager custom hay provider cache khác, Boot có thể cung cấp simple cache. Cache này **không tự hết hạn** và chỉ tồn tại trong bộ nhớ của process.

### 7.3. Chạy và kiểm tra bằng curl

Chạy ở thư mục gốc dự án:

~~~bash
./gradlew bootRun
~~~

Trên Windows dùng `gradlew.bat bootRun`; với Maven wrapper trong dự án Boot đã cấu hình Maven dùng `./mvnw spring-boot:run`. Kiểm tra bằng các lệnh sau, gọi từng lệnh theo thứ tự.

**Bước A – GET lần đầu:**

~~~bash
curl -i http://localhost:8080/products/1
curl -s http://localhost:8080/debug/load-count
~~~

Kỳ vọng status `200 OK` cho product, JSON tương đương `{"id":1,"name":"Sổ tay","version":1}`, `Cache-Control` công khai có max-age 30 giây và `ETag: W/"product-1-v1"`. Endpoint đếm trả:

~~~json
{"loads":1}
~~~

**Bước B – gọi lại cùng URL bằng curl:**

~~~bash
curl -i http://localhost:8080/products/1
curl -s http://localhost:8080/debug/load-count
~~~

Kỳ vọng `{"loads":1}` vẫn không đổi: controller đã chạy nhưng `@Cacheable` trả Product từ **Spring Cache** nên method `find` không chạy nữa. **curl thông thường không tự giữ HTTP cache giữa các lần gọi**; đừng xem đây là bằng chứng browser/CDN HTTP cache hit.

**Bước C – gửi conditional GET:**

~~~bash
curl -i -H 'If-None-Match: W/"product-1-v1"' \
  http://localhost:8080/products/1

curl -s http://localhost:8080/debug/load-count
~~~

Với shell hỗ trợ single quotes (Linux/macOS), kết quả GET có thể là `304 Not Modified`, body rỗng, ETag vẫn tương ứng version 1, `loads` vẫn là 1. Với Windows PowerShell, quote theo shell hoặc dùng `curl.exe`; nếu nghi vấn quoting, dùng một dòng và kiểm tra request bằng `curl -v`.

**Bước D – cập nhật dữ liệu:**

~~~bash
curl -i -X PUT "http://localhost:8080/products/1?name=So%20moi"
curl -s http://localhost:8080/debug/load-count
~~~

Response update trả Product version 2. `@CacheEvict` xóa entry key 1 của Spring Cache **sau khi mutation thành công**. Tuy nhiên count có thể vẫn 1 ngay sau PUT, vì mutation không gọi method `find`.

**Bước E – GET lại với ETag cũ:**

~~~bash
curl -i -H 'If-None-Match: W/"product-1-v1"' \
  http://localhost:8080/products/1

curl -s http://localhost:8080/debug/load-count
~~~

Vì service cache bị evict, lần GET này đọc storage mới và tạo ETag version 2, nên kỳ vọng `200 OK`, body có `"version":2`, ETag `W/"product-1-v2"` và count lên:

~~~json
{"loads":2}
~~~

**Điểm dễ bị bỏ qua:** Browser hoặc CDN đã giữ response v1 **còn fresh 30 giây** có thể dùng lại v1 cho GET bình thường ngay cả khi PUT đã thay backend/Spring Cache. Demo dùng curl để chủ động yêu cầu origin; không chứng minh browser cache tự biến mất sau mutation. Nếu sản phẩm yêu cầu đọc mới ngay, cần đổi cache policy, cache key/versioned URL, purge/invalidation hoặc revalidation theo hợp đồng hệ thống.

### 7.4. Kiểm chứng status và response headers

Trong thực tế, thứ tự header, JSON whitespace, kiểu charset, Date và connection headers do Spring/container quyết định. Không dựa vào việc response raw có thứ tự byte y hệt ví dụ; kiểm **semantics**: status, ETag, Cache-Control, body, method load count.

Trên một hệ có proxy/CDN, `Age`, `Via`, `X-Cache` (nếu cấu hình có) và server access logs có thể giúp phân biệt HTTP cache hit. Không mặc định mọi CDN đều có `X-Cache` hoặc cú pháp hit/miss giống nhau. Với browser, DevTools Network có thể hiển thị `from memory cache`, `from disk cache`, conditional revalidation hay network response tùy trình duyệt.

## 8. Bản chất của invalidation: mỗi cache có đồng hồ riêng

Hãy xét một timeline giả định:

| Thời điểm | HTTP cache | Spring Cache | Database | Hệ quả |
|---|---|---|---|---|
| t = 0 | Browser lưu response v1, fresh 60 giây | Service lưu Product v1 | v1 | GET đầu trả v1 |
| t = 10 | Browser vẫn giữ v1 fresh | Một mutation evict Product v1 | v2 | Backend mới nhưng browser có thể vẫn thấy v1 |
| t = 20 | Browser dùng lại v1 mà không hỏi origin | Cache business không được gọi | v2 | Không thể chỉ evict Spring Cache để xóa bản HTTP |
| t = 61 | Browser hết freshness, revalidate ETag v1 | Service tải/cache Product v2 | v2 | Origin trả 200 v2 thay vì 304 |

**Chiều ngược lại cũng nguy hiểm:** nếu HTTP response có `no-cache` (buộc revalidate) nhưng Spring Cache vẫn giữ Product v1 khi DB đã đổi v2 mà không evict/expire, origin có thể tiếp tục gửi weak ETag v1 và trả `304` sai theo dữ liệu nguồn. HTTP revalidation **không làm sạch** business cache stale. Cần chiến lược invalidation/TTL nhất quán.

Mối quan hệ giữa hai TTL không có công thức mặc định. TTL của business cache phải theo mức stale mà nghiệp vụ chấp nhận và cơ chế mutation; HTTP TTL phụ thuộc khả năng chấp nhận stale tại client/shared cache. Ngay cả khi đặt hai TTL giống nhau, các thời điểm tạo entry và điều kiện revalidation khác nhau nên **không bảo đảm** chúng tự hết hạn cùng lúc.

### Các chiến lược cập nhật thường gặp

- **Cache-aside:** service đọc theo `@Cacheable`; sau mutation thành công, evict key liên quan. Hợp khi điểm cập nhật được quản lý tập trung và chấp nhận cửa sổ stale nhỏ theo concurrency.
- **Write-through/update cache:** sau mutation, cập nhật cache theo record mới (có thể `@CachePut`), nhưng phải bảo đảm giá trị được cache đúng với dữ liệu đã commit và tránh race giữa các request.
- **TTL + eviction:** TTL là lưới an toàn cho những mutation từ nguồn khác; TTL không thay thế invalidation nếu cần dữ liệu cập nhật ngay.
- **Event-driven invalidation:** khi nhiều services/replicas thay đổi dữ liệu, publish invalidation/version change, chú ý thứ tự sự kiện, retry, idempotency và eventual consistency.
- **HTTP versioned URLs:** tài nguyên tĩnh có tên chứa hash/version được phục vụ với freshness dài; khi nội dung đổi dùng URL mới.
- **CDN purge/invalidation:** dùng cơ chế chính thức của CDN nếu cần xóa/refresh bản shared cache; event Spring `@CacheEvict` tự nó không ra lệnh CDN purge.

## 9. Khi nào dùng no-store, private, public hoặc no-cache?

Phân loại theo **độ nhạy** và **độ cũ cho phép**, không theo việc endpoint là GET hay POST một cách máy móc.

| Response | Chính sách HTTP thường phù hợp | Spring Cache tầng nghiệp vụ |
|---|---|---|
| JS/CSS/ảnh có filename chứa content hash | `public, max-age` dài và có thể `immutable`, tùy hạ tầng | Thường không cần `@Cacheable` cho binary static resource |
| Danh mục sản phẩm công khai, stale vài chục giây được | `public, max-age=30` hoặc chính sách CDN rõ ràng | `@Cacheable` cho sản phẩm; evict khi cập nhật |
| Tin tức công khai cập nhật nhanh | `max-age` ngắn, `ETag`/Last-Modified để revalidate | TTL/invalidation phù hợp tốc độ cập nhật |
| Hồ sơ cá nhân | `private` nếu cho phép browser lưu; `no-store` nếu nhạy cảm | Nếu cache service, key phải gắn user/tenant/permission context và bảo vệ dữ liệu |
| Access token, thông tin thanh toán, bí mật | Thường `Cache-Control: no-store` cùng các biện pháp bảo vệ thích hợp | Tránh lưu những dữ liệu nhạy cảm trong cache nếu không thật sự cần; có encryption/access policy/TTL |
| Response khác theo ngôn ngữ | `Vary: Accept-Language`, cộng chính sách freshness | Cache key service có thể phải gắn locale |
| Response khác theo gzip/br | `Vary: Accept-Encoding` khi representations phụ thuộc request encoding | Domain Product object có thể dùng cùng một cache entry độc lập encoding |
| Dữ liệu gần thời gian thực / quota | `no-store` hoặc `no-cache` + validator đáng tin theo yêu cầu | Hạn chế caching stale; invalidation/versioning chặt |

`private` không đồng nghĩa dữ liệu đã được mã hóa hoặc chỉ user có quyền mới đọc được. `no-store` cũng không xóa tự động những bản đã tồn tại ở nơi khác hoặc ngăn logging; bảo mật cần authentication, authorization, TLS và chính sách lưu dữ liệu.

### Authorization và shared caches

RFC 9111 đặt điều kiện đặc biệt với request có `Authorization`: shared cache không được tự ý dùng lại response trừ khi response có directive phù hợp cho phép theo quy tắc đặc biệt. Vì thế **không gắn `public` vô điều kiện** vào endpoint dùng Authorization chỉ vì thấy khả năng tăng cache hit. Nếu representation riêng từng user, mặc định nên tránh shared caching và thử nghiệm với nhiều tài khoản để phát hiện cache leakage.

Nếu response phụ thuộc session cookie, tenant, role hoặc feature flag, các dimension này cũng có thể ảnh hưởng representation, nhưng chỉ thêm `Vary: Cookie` không phải phương án tự động an toàn và có thể gây phân mảnh cache rất lớn. Ưu tiên no-store/private hoặc URL/key phân quyền đúng và policy rõ ràng.

## 10. Spring Cache: chọn provider, TTL và memory budget

### 10.1. Simple cache cho lab

Với default simple `ConcurrentMapCacheManager`, cache có thể giữ entry vô thời hạn cho tới khi evict, clear hoặc restart JVM; memory dùng tăng theo số key/value nếu không có giới hạn thích hợp. **Không dùng simple cache như một chiến lược production mặc định cho tập key không giới hạn.**

### 10.2. Caffeine: TTL và giới hạn dung lượng trong một JVM

Nếu muốn cache in-process có size cap và TTL trên Spring Boot, thêm dependency Caffeine:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
~~~

Trong `application.properties` của **một dự án đã có starter-web**:

~~~properties
spring.cache.type=caffeine
spring.cache.cache-names=products
spring.cache.caffeine.spec=maximumSize=10000,expireAfterWrite=60s
~~~

Đây là cấu hình provider, không sửa Spring `@Cacheable`. Khi entry cũ hết TTL, lần gọi tiếp có thể tính lại. Caffeine là cache **per instance**: nếu chạy ba replicas, mỗi replica có nội dung/timing riêng. TTL không cam kết dữ liệu được làm mới ngay nếu không có request, và không tự thông báo browser/CDN khi có mutation.

### 10.3. Redis: cache chung và giới hạn tải

Trong môi trường nhiều application instances, Redis có thể làm cache provider chia sẻ, với TTL theo cấu hình provider/Boot và connection pool. Ví dụ property thường gặp:

~~~properties
spring.cache.type=redis
spring.cache.redis.time-to-live=60s
~~~

Đây **không phải** cấu hình Redis chạy được độc lập: project còn phải có Redis starter/driver, Redis server, kết nối và serialization phù hợp. Giá trị TTL áp dụng cho cache entries theo provider, không phải `Cache-Control` của HTTP.

Dùng Redis cache cho Java objects cần kiểm tra serializer, phiên bản schema/DTO, key namespace, tenant isolation, tính bền vững của backend và failure mode. Nếu Redis down, ứng dụng có thể chậm/lỗi do cache dependency; không mặc định cache luôn “free”.

### 10.4. Cache stampede và concurrency

Khi entry hot hết hạn, nhiều request đồng thời có thể cùng miss rồi cùng truy vấn DB. Một số provider hỗ trợ `@Cacheable(sync = true)` để đồng bộ việc tính value cho cùng key **trong phạm vi provider hỗ trợ**, nhưng không suy ra điều này luôn đồng bộ xuyên nhiều JVM hoặc giải quyết mọi refresh race. Cần đo DB load và cache miss spikes; với dữ liệu rất hot có thể cân nhắc TTL jitter, refresh-ahead, per-key coordination hoặc single-flight ở tầng thích hợp.

TTL quá dài gây stale; TTL quá ngắn làm miss nhiều và tăng tải backend. Chọn dựa trên cost của DB query, update frequency, freshness requirement, hot keys và traffic pattern. Không “tối ưu” bằng cách tăng tất cả TTL lên nhiều giờ.

## 11. Giới hạn proxy: vì sao @Cacheable đôi khi không chạy?

Cache annotation trong chế độ mặc định của Spring thường được áp dụng qua **Spring AOP proxy**.

~~~java
@Service
public class CatalogService {
    @Cacheable("products")
    public Product find(long id) {
        return repository.load(id);
    }

    public Product anotherMethod(long id) {
        return this.find(id); // Gọi trong cùng instance -> có thể bypass proxy
    }
}
~~~

Đây là **mảnh code minh họa**: `Product` và `repository` do ứng dụng định nghĩa, không phải file Java runnable độc lập. Khi method khác gọi `this.find(id)` trong cùng object, lời gọi không đi qua Spring proxy bên ngoài, nên caching annotation có thể không được áp dụng. Các tình huống khác cần kiểm tra: object tạo bằng `new` thay vì bean được container quản lý, method visibility/proxy type, final methods/classes, cache infrastructure chưa bật, hoặc method không được gọi trên bean/proxy như dự định.

Ví dụ đầy đủ ở mục 7 dùng **controller gọi service bean riêng** để tránh self-invocation. Đừng tự sửa bằng cách chuyển mọi method sang static hoặc gọi proxy trong chính object; thiết kế service boundary rõ sẽ dễ test và bảo trì hơn.

### @Cacheable, @CachePut, @CacheEvict không thể thay thế nhau

- `@Cacheable`: có thể bỏ qua thực thi method khi hit.
- `@CachePut`: **luôn chạy** method, dùng kết quả để cập nhật entry. Nếu method trả response DTO khác thực thể cần cache, dùng `@CachePut` không đúng cách có thể gây cache chứa sai kiểu.
- `@CacheEvict`: xóa entry, thường sau khi method chạy thành công. Nếu database transaction chưa commit hoặc publish event trễ, có thể xuất hiện race; cần thiết kế thứ tự invalidation với transaction.
- `allEntries=true`: xóa cả cache, có thể gây cache stampede lớn; chỉ dùng khi thay đổi thật sự ảnh hưởng toàn bộ keys.
- `beforeInvocation=true`: có ý nghĩa nghiệp vụ khác default (evict cả khi method lỗi); không bật tùy tiện.

Một mutation có thể ảnh hưởng thêm cache danh sách, category và search. Evict `products[id]` không tự xóa `productSearch[query]`. Cần map phụ thuộc cache keys theo logic domain.

## 12. HTTP conditional requests và validator nhất quán

### ETag dựa trên version

Trong app demo, weak ETag là `W/"product-1-v1"` vì version 1. Khi mutation nâng version lên 2, validator đổi. Cách này nhanh, nhưng chỉ đúng nếu mọi thay đổi ảnh hưởng **representation được phục vụ** đều khiến version thay đổi. Nếu JSON phản ánh tồn kho từ nguồn khác mà version không cập nhật, server có thể trả 304 khi nội dung thực đã đổi.

### Last-Modified

`Last-Modified` phản ánh thời điểm sửa của resource theo chuẩn thời gian HTTP. Cần có source timestamp tin cậy; độ phân giải header có thể thấp hơn số lần update trong cùng giây. Spring `WebRequest.checkNotModified(lastModifiedMillis)` hoặc `ResponseEntity.lastModified(...)` có thể hỗ trợ conditional request. Nếu hai thay đổi liên tiếp trong cùng giây, chỉ dựa vào Last-Modified có thể thiếu độ chính xác; ETag version đáng tin thường phù hợp hơn.

### 304 và HTTP status khác

- `304 Not Modified` dùng cho conditional GET/HEAD khi validator cho thấy có thể tái sử dụng representation cũ; response **không có body**.
- `412 Precondition Failed` thường liên quan điều kiện cập nhật như `If-Match` không đạt, không phải cách diễn đạt “cache miss”.
- `200 OK` với body mới là bình thường khi validator không khớp, hoặc request không có conditional headers.
- `206 Partial Content` là response cho range requests hợp lệ; ETag mạnh và byte representation chính xác quan trọng khi ghép nhiều ranges.

Không tự thay đổi status thành 304 chỉ vì business cache hit: cache hit không chứng minh browser có body trước đó. Chỉ trả 304 khi **HTTP conditional request** và validator thực sự đáp ứng semantics.

## 13. Bộ nhớ đệm HTTP và nén gzip/br

Vì chủ đề cha là “Cache và nén HTTP”, cần nắm quan hệ giữa **representation caching** và **content encoding**.

Client có thể gửi:

~~~http
GET /assets/app.js HTTP/1.1
Accept-Encoding: gzip, br
~~~

Origin hoặc CDN có thể chọn representation mã hóa gzip/br hoặc identity, tùy capability/config. Nếu response nén khác nhau theo `Accept-Encoding`, policy thường cần `Vary: Accept-Encoding` để cache chọn đúng bản cho từng client. **Mỗi representation mã hóa có thể có byte sequence khác nhau**. Điều này liên quan cách tạo ETag mạnh; không gắn cùng strong validator cho hai representation khác bytes rồi mặc nhiên dùng trong range/validator semantics.

Trong Spring Boot MVC, server-side response compression có thể được cấu hình bằng các property liên quan:

~~~properties
server.compression.enabled=true
server.compression.min-response-size=2KB
server.compression.mime-types=text/html,text/css,application/javascript,application/json
~~~

Đây là **đoạn cấu hình minh họa**; engine/container, MIME types, HTTP negotiation, proxy và mức nén có thể khác theo triển khai. Đừng dùng nén cho mọi content type khi file đã được nén (ảnh JPEG/PNG, video, archives), vì có thể không tiết kiệm băng thông và tăng CPU.

**Nén không phải cache.** Nén làm body truyền trên mạng nhỏ hơn; HTTP cache có thể loại bỏ cả lần truy cập origin/transfer nếu representation còn fresh; Spring Cache tránh công việc bên trong method. Ba cơ chế tối ưu các tài nguyên khác nhau: bandwidth/CPU nén, network + origin requests, và DB/compute.

Một byte-count/correlation test hữu ích: đo response headers `Content-Encoding`, `Vary`, `ETag`, `Cache-Control` và body size từ client; sau đó so sánh cùng endpoint khi gửi `Accept-Encoding: identity` với khi cho phép gzip/br. Nếu representation khác, cần xác định validator và cache key ở tầng proxy. Không dùng `Content-Length` của uncompressed JSON làm số bytes của response compressed.

## 14. Spring Boot static resources: HTTP cache thường hữu ích hơn @Cacheable

JS, CSS, icon và ảnh tĩnh thường được phục vụ bởi Spring Boot static resource handling từ classpath, ví dụ `src/main/resources/static`. Khi dùng tên file chứa content hash/version (ví dụ `app.8f0a21.js`), có thể đặt freshness dài cho những URLs bất biến: khi nội dung đổi, build tạo URL mới. Đây là mô hình “cache busting” có kiểm soát.

Với Spring Boot 3.3, các property liên quan static resource caching như:

~~~properties
spring.web.resources.cache.cachecontrol.max-age=365d
spring.web.resources.cache.cachecontrol.cache-public=true
~~~

Cấu hình trên chỉ thích hợp **khi URLs của tài nguyên thực sự immutable/versioned** và cách deploy đảm bảo không phục vụ bytes mới dưới URL cũ. Nếu ghi đè `/app.js` mà vẫn để fresh một năm, client có thể tiếp tục dùng JS cũ rất lâu.

Ở mức Spring MVC, có thể dùng `ResourceHandlerRegistry` và `CacheControl` để cấu hình riêng resource mappings. Đây là HTTP response caching; không cần `@Cacheable` trên một service Java chỉ để cache file JavaScript.

## 15. Spring WebFlux có HTTP caching và Spring Cache không?

Có. Spring WebFlux hỗ trợ HTTP caching qua `CacheControl`, ETag/Last-Modified, conditional requests và `ServerWebExchange.checkNotModified(...)`. Spring Cache abstraction cũng có thể dùng trong service layer của ứng dụng WebFlux, nhưng **đường thực thi non-blocking** cần được đánh giá theo cache provider và Spring Framework version.

Một ví dụ logic (mã **minh họa bên trong WebFlux controller**, không tự biên dịch độc lập):

~~~java
@GetMapping("/reactive-products/{id}")
public Mono<ResponseEntity<Product>> get(@PathVariable long id,
                                          ServerWebExchange exchange) {
    return productService.findReactive(id)
            .map(product -> {
                String etag = "W/\"product-" + id
                        + "-v" + product.version() + "\"";
                CacheControl policy =
                        CacheControl.maxAge(Duration.ofSeconds(15))
                                    .cachePublic();

                if (exchange.checkNotModified(etag)) {
                    return ResponseEntity
                            .status(HttpStatus.NOT_MODIFIED)
                            .cacheControl(policy)
                            .eTag(etag)
                            .build();
                }
                return ResponseEntity.ok()
                        .cacheControl(policy)
                        .eTag(etag)
                        .body(product);
            });
}
~~~

Cần controller class/imports, reactive service và Product type tương ứng. Ví dụ này minh họa HTTP conditional handling, không áp đặt cách triển khai cache provider. Spring Framework 6.1 có xử lý riêng với reactive return types ở cache abstraction; behavior của `Mono`/`Flux`, asynchronous cache retrieval và compatibility phụ thuộc version/provider. Không giả định “bọc một `RedisTemplate` blocking trong `Mono`” sẽ khiến cache I/O non-blocking.

Trong WebFlux, blocking cache client, database call hoặc serialization nặng chạy trên Netty event loop có thể làm chậm nhiều requests. Nếu dùng cache provider blocking, offload công việc phù hợp hoặc chọn API/adapter reactive thực sự. HTTP cache policy vẫn là semantics của client/proxy như ở MVC.

## 16. Đo hiệu quả từng tầng riêng biệt

Không nên xem một con số “cache hit ratio” rồi kết luận cả hệ thống đã hiệu quả. Cần đo **mỗi tầng**.

| Quan sát | Cách đo | Kết luận hợp lệ |
|---|---|---|
| Browser HTTP cache | DevTools Network, transfer size, conditional GET | Có thể giảm request đến origin hoặc giảm bandwidth ở client |
| CDN shared cache | CDN analytics/response metadata, origin logs | Shared cache có đang phục vụ request đúng policy hay không |
| Spring Cache hit/miss | Metrics của provider, method invocation count, trace | Method nặng có bị bỏ qua khi hit không |
| DB query rate | DB/query metrics, downstream spans | Cache có giảm công việc backend không |
| Serialization/CPU | Profiling/trace trên server | Business cache hit vẫn có thể serialize lại DTO |
| HTTP `304` | Access logs, client traces, response status | Revalidation tiết kiệm body bandwidth; không chứng minh method không chạy |
| p95/p99 latency | Client/proxy/server metrics theo đường đi | Tác động thực tới trải nghiệm, cần tách cache hit/miss |
| Cache memory usage | Caffeine/Redis/JVM metrics | Key cardinality/entry size/TTL có phù hợp budget không |

### Công thức đo quan trọng

Business cache hit ratio:

~~~text
hit_ratio = cache_hits / (cache_hits + cache_misses)
~~~

Trong đó hit/miss phải được lấy từ provider theo định nghĩa nhất quán, không suy ra từ HTTP 200/304. HTTP cache hit ratio lại tính theo requests/representations phục vụ từ browser/proxy; hai tỷ lệ có **mẫu số khác nhau**.

Để đo tác động tới database:

~~~text
DB queries per second (before) = 1000
DB queries per second (after)  = 150
Reduction = (1000 - 150) / 1000 = 85%
~~~

Đây chỉ là ví dụ công thức, không phải số liệu đã đo của ứng dụng demo. Cần kiểm soát traffic mix, read/write ratio, cache warm-up, TTL, CDN hit rate và số replicas trước khi so sánh.

### Một quy trình benchmark ngắn có kiểm soát

1. Xác định workload: ví dụ 90% GET sản phẩm công khai, 10% PUT cập nhật; tỷ lệ keys hot/cold, kích thước JSON và số unique users.
2. Chạy baseline khi Spring Cache off (hoặc không annotation) và HTTP cache bị buộc revalidate, ghi DB load, CPU, network bytes, p95/p99.
3. Bật **riêng Spring Cache**; đo cache hit, DB load và p95/p99 tại origin. Để HTTP cache không che mất request, dùng client thử nghiệm gửi requests tới origin theo cách có chủ đích.
4. Bật **HTTP cache** tại browser/CDN theo policy; đo origin request rate, transfer bytes, Age và số 304, kiểm tra dữ liệu không rò rỉ giữa users.
5. Chạy mutation, TTL expiration, cache purge, concurrent miss và failover; xác nhận độ mới dữ liệu theo SLO.
6. Thử nén bật/tắt ở cùng một traffic profile; đo bandwidth và CPU thay đổi, kiểm tra Vary/ETag correctness.

Không so lượt 1 khi cache cold với lượt 2 khi cache warm rồi khẳng định cache nào tốt hơn; cần ghi điều kiện và lặp thử nghiệm.

## 17. Các lỗi phổ biến và nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Gọi GET hai lần bằng curl đều có 200, nhưng DB không bị query lại | Curl không tái dùng HTTP cache; Spring Cache hit | Đọc load count/metrics; test If-None-Match riêng |
| Browser vẫn thấy sản phẩm cũ sau khi @CacheEvict | Browser/CDN còn response fresh | Giảm max-age, revalidation hoặc purge/version URL theo nhu cầu |
| HTTP 304 nhưng data backend đã đổi | ETag/version tính từ business cache stale, không invalidated | Kiểm tra nguồn validator và evict/TTL ở service |
| no-cache vẫn thấy response được lưu | no-cache cho phép lưu nhưng yêu cầu revalidate | Dùng no-store khi phải cấm lưu theo giao thức |
| Có @Cacheable nhưng method vẫn chạy mỗi lần | Self-invocation, bean không qua proxy, key khác, @EnableCaching/provider thiếu | Kiểm tra proxy, key, bean wiring và instrumentation |
| @CachePut thay đổi DB nhưng GET vẫn cũ | Key không đồng nhất, mutation chưa commit, cache khác | Quy định key namespace, eviction/update sau commit |
| CPU/heap tăng dù cache hit cao | Cache lưu object lớn, key cardinality cao, TTL/size cap thiếu | Giới hạn size/TTL, đo memory và object graph |
| Caffeine cache hit khác nhau giữa replicas | Cache nằm trong từng JVM | Chấp nhận eventual consistency hoặc dùng distributed invalidation/cache |
| CDN trả nội dung của user A cho user B | public/shared policy sai, key không bao gồm context, auth response cacheable | no-store/private, access tests và thiết kế shared cache an toàn |
| Response tiếng Việt/Anh bị dùng nhầm | Thiếu Vary: Accept-Language hoặc key dimension | Thêm Vary đúng và kiểm tra cache variants |
| Client nhận gzip khi không hỗ trợ | Vary: Accept-Encoding/cache config sai | Sửa representation variants, proxy và compression negotiation |
| Strong ETag giống nhau giữa gzip và identity khác bytes | Validator không tuân theo representation semantics | Dùng strong per representation hoặc weak khi thích hợp |
| Tăng s-maxage mà browser không giữ lâu hơn | s-maxage điều khiển shared cache | Cấu hình max-age cho private browser riêng |
| Cấu hình TTL của Redis nhưng HTTP vẫn cache nhiều phút | Redis TTL không thay đổi Cache-Control | Thiết kế TTL từng tầng; header HTTP độc lập |
| Bật ShallowEtagHeaderFilter rồi CPU không giảm | Filter thường cần render body mới có hash | Dùng version-based conditional handling / business cache |
| Bật cache mọi chỗ làm p99 tăng | Cache server quá tải, miss stampede, Redis latency, serialize lớn | Đo từng layer, concurrency, backend và cache provider |

## 18. Thiết kế một chính sách cache có thể kiểm thử

Trước khi bật cache cho một endpoint, trả lời đủ các câu hỏi:

1. **Ai sở hữu dữ liệu?** Công khai, theo user, tenant, role hay authorization scope?
2. **Độ mới cần bao nhiêu?** Chấp nhận stale 30 giây, 1 phút hay bắt buộc “read-your-writes” ngay?
3. **Điều gì đổi representation?** Version, locale, currency, feature flag, personalized pricing, content encoding?
4. **Tầng nào cần tối ưu?** Giảm bandwidth/CDN origin requests hay giảm DB/CPU trong service?
5. **Cache key nào đầy đủ?** HTTP variants theo Vary, Spring key theo domain identity + context.
6. **Có mutation ngoài ứng dụng không?** Admin console, batch jobs, events, downstream systems có cập nhật cùng dữ liệu?
7. **Invalidation thực hiện thế nào?** Evict, @CachePut, TTL, event, CDN purge, version URL hay combination?
8. **Nếu cache lỗi hoặc không dùng được?** Fallback DB, timeout, overload control, consistency và quan sát lỗi.
9. **Giới hạn tài nguyên?** Cache entry count/size, network round trips, Redis memory, serialization, max stale.
10. **Bằng chứng test nào đủ?** HTTP headers, GET conditional 304, no-store on sensitive, cache provider metrics, mutation correctness và multi-user isolation.

Khi có thể, ghi các điều kiện thành **integration tests**: sau khi mutate, product version phải đổi; ETag mới phải khác; GET với ETag cũ phải trả 200; GET với ETag mới trả 304; sensitive endpoint phải có policy đúng; cache key không gây rò rỉ giữa tenants. Khi dùng CDN thật, test riêng origin và shared cache trong môi trường được phép, vì test controller không mô phỏng đầy đủ RFC caching behavior.

## 19. Tự kiểm tra

**Câu 1.** Spring service trả từ @Cacheable, browser có tự nhận HTTP 304 không?  
**Đáp:** Không. 304 chỉ có khi HTTP request có điều kiện và validator phù hợp; Spring Cache hit chỉ biểu thị method result reuse bên trong ứng dụng.

**Câu 2.** Server trả Cache-Control: public, max-age=60, browser còn response fresh. GET tiếp theo có chắc controller chạy không?  
**Đáp:** Không. HTTP cache có thể phục vụ response mà không gửi request tới origin.

**Câu 3.** no-cache có nghĩa cấm lưu response không?  
**Đáp:** Không. Cache có thể lưu, nhưng phải revalidate thành công trước khi sử dụng lại. no-store mới là directive cấm lưu theo HTTP semantics.

**Câu 4.** Sau @CacheEvict, CDN có tự purge bản response không?  
**Đáp:** Không. Cần policy HTTP/TTL/revalidation, version URL hoặc cơ chế CDN invalidation riêng.

**Câu 5.** Có thể dùng Spring Cache TTL = 5 phút và HTTP max-age = 10 giây không?  
**Đáp:** Có, nhưng phải đánh giá stale consistency: sau 10 giây browser revalidate, origin có thể vẫn lấy dữ liệu 5 phút cũ từ Spring Cache nếu không có invalidation đáng tin.

**Câu 6.** @CachePut khác @Cacheable ở đâu?  
**Đáp:** @CachePut luôn thực thi method rồi cập nhật cache từ kết quả; @Cacheable có thể bỏ qua method khi hit.

**Câu 7.** Một method @Cacheable được gọi bằng this.method() trong cùng bean có chắc qua proxy không?  
**Đáp:** Không trong proxy mode mặc định. Self-invocation có thể bypass caching advice.

**Câu 8.** User-specific response được đánh public chỉ vì có authorization token thì an toàn không?  
**Đáp:** Không. Phải thiết kế shared cache policy dựa trên nội dung và Authorization rules, tránh rò rỉ dữ liệu cá nhân; no-store/private thường phù hợp hơn.

**Câu 9.** Vary: Accept-Encoding dùng để điều khiển gì?  
**Đáp:** Cho HTTP cache phân biệt response variants theo request Accept-Encoding, tránh dùng bản gzip/br/identity không phù hợp.

**Câu 10.** Dùng weak ETag từ version có phù hợp để revalidate JSON không?  
**Đáp:** Có thể phù hợp nếu version thay đổi với mọi thay đổi ngữ nghĩa của representation. Nó không thay thế strong validator cho những tác vụ đòi byte identity.

**Câu 11.** ShallowEtagHeaderFilter có tự loại bỏ chi phí truy vấn DB và render không?  
**Đáp:** Không. Filter thường tạo ETag từ body đã render, có lợi về bandwidth, còn service/serialization vẫn có thể chạy.

**Câu 12.** Nếu chỉ đo hit ratio Spring Cache cao, đã chứng minh CDN hoạt động tốt chưa?  
**Đáp:** Chưa. HTTP cache hit/miss là thước đo độc lập ở browser/proxy, có mẫu số và network behavior riêng.

## 20. Tài liệu chuẩn

- [RFC 9111 – HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html): private/shared caches, freshness, storage và Cache-Control directives.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): ETag, Last-Modified, conditional requests và representation semantics.
- [Spring Framework – HTTP Caching in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): CacheControl, ResponseEntity, conditional request và ShallowEtagHeaderFilter.
- [Spring Framework – HTTP Caching in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/caching.html): HTTP validators và CacheControl trong reactive stack.
- [Spring Framework – Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): cache name, key, CacheManager, semantics và provider integration.
- [Spring Framework – Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): @Cacheable, @CacheEvict, @CachePut, sync và proxy-related behavior.
- [Spring Boot 3.3 – Caching](https://docs.spring.io/spring-boot/3.3/reference/io/caching.html): cache auto-configuration và các providers trong Spring Boot.
- [Spring Boot 3.3 – Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): properties cho cache providers, static resources và response compression.
