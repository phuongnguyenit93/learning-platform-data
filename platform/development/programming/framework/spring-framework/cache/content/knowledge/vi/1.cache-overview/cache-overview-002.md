# Phân biệt cache với buffer, cơ sở dữ liệu và HTTP cache trong Spring Framework

## 1. Bốn khái niệm giải quyết bốn nhu cầu khác nhau

Trong ứng dụng Spring, cùng một dữ liệu có thể đi qua **database**, **cache trong ứng dụng**, **buffer** và **HTTP cache**. Chúng có thể cùng tồn tại nhưng phục vụ những mục đích khác nhau:

- **Cache (bộ nhớ đệm kết quả):** giữ bản sao hoặc kết quả tính toán có thể tái tạo để lần truy cập sau nhanh hơn, giảm công việc cho nguồn dữ liệu/giai đoạn xử lý gốc.
- **Buffer (vùng đệm luồng):** giữ tạm dữ liệu đang được truyền hoặc xử lý để gom các thao tác I/O, điều hòa tốc độ bên sản xuất và bên tiêu thụ, hoặc xử lý dữ liệu theo từng khối.
- **Cơ sở dữ liệu (database):** quản lý dữ liệu theo mô hình, truy vấn và ràng buộc nhất quán; thường là **nguồn dữ liệu có thẩm quyền** (source of truth) của nghiệp vụ.
- **HTTP cache:** là **một loại cache ở tầng giao thức HTTP**. Trình duyệt, proxy hoặc CDN lưu bản biểu diễn của HTTP response và quyết định khi nào được tái sử dụng hoặc phải xác thực lại theo HTTP headers.

Điểm cốt lõi: **cache** nói về *tái sử dụng kết quả*, **buffer** nói về *dòng dữ liệu đang di chuyển*, **database** nói về *quản lý trạng thái nghiệp vụ*, còn **HTTP cache** nói về *tái sử dụng HTTP response*. HTTP cache thuộc họ cache nhưng có quy tắc và vị trí hoạt động khác với cache phương thức của Spring.

| Tiêu chí | Cache trong ứng dụng | Buffer | Database | HTTP cache |
|---|---|---|---|---|
| Mục tiêu chính | Giảm truy vấn hoặc phép tính lặp | Giảm chi phí I/O, điều tiết luồng | Lưu trữ, truy vấn, bảo đảm quy tắc dữ liệu | Giảm tải mạng, độ trễ và yêu cầu tới origin |
| Đơn vị thường gặp | Key → value/kết quả | Byte, ký tự, phần tử đang chờ xử lý | Bản ghi, hàng, tài liệu, quan hệ | HTTP response/representation gắn với request và quy tắc cache |
| Cách sử dụng | Tìm bằng key; hit/miss | Đọc/ghi tuần tự hoặc theo khối | Query, transaction, CRUD | Dùng response còn fresh hoặc revalidate |
| Khi cũ/đầy | TTL, eviction, cập nhật/xóa | Flush, tiêu thụ, backpressure | Ghi/sửa/xóa theo nghiệp vụ | Freshness lifetime, validator, invalidation/purge |
| Vai trò về tính đúng | Thường có thể bỏ và tái tạo | Không thay thế nguồn dữ liệu | Thường là nguồn có thẩm quyền | Phụ thuộc response gốc và HTTP cache policy |
| Ví dụ | Spring `@Cacheable`, Caffeine, Redis | `BufferedInputStream`, `ByteBuffer` | PostgreSQL, MySQL, MongoDB | Browser cache, CDN, `Cache-Control`, `ETag` |

**Lưu ý:** database cũng có thể sử dụng buffer pool/cache nội bộ; một cache cũng có thể được lưu trên đĩa hoặc Redis. Phân loại dựa trên **vai trò và cam kết của dữ liệu**, không chỉ dựa trên nơi nó nằm (RAM hay ổ đĩa).

## 2. Cache trong ứng dụng Spring hoạt động thế nào?

Giả sử API lấy sản phẩm theo ID. Một lần đọc không dùng cache đi theo luồng:

~~~text
HTTP request → Controller → Service → Repository → Database → Response
~~~

Khi áp dụng cache ở tầng service:

~~~text
HTTP request → Controller → Service → [Cache theo productId]
                                         │
                       hit: trả kết quả ─┤
                                         └─ miss: Repository → Database
                                                    │
                                              ghi vào cache
                                                    │
                                                trả kết quả
~~~

- **Cache hit:** key đã có giá trị phù hợp, service có thể trả kết quả mà không chạy truy vấn gốc.
- **Cache miss:** chưa có key (hoặc entry bị hết hạn/xóa), phải đọc từ nguồn rồi có thể nạp kết quả vào cache.
- **Cache key:** định danh duy nhất cho điều kiện truy vấn. Chỉ dùng `productId` là sai nếu kết quả còn phụ thuộc tenant, locale, quyền truy cập, giá vùng miền hoặc phiên bản dữ liệu.
- **Invalidation/eviction:** sau khi nguồn thay đổi, phải làm giá trị cache không còn được tái sử dụng sai; có thể xóa, cập nhật entry hoặc đợi TTL khi nghiệp vụ cho phép dữ liệu hơi cũ.
- **TTL (time to live):** thời gian entry được giữ là hợp lệ theo chính sách của cache provider; TTL không tự giải quyết mọi vấn đề nhất quán hay dữ liệu nhạy cảm.

### Cách dùng Cache Abstraction của Spring

Spring cung cấp abstraction để khai báo thao tác cache tại phương thức. Đoạn dưới là **mã minh họa tích hợp**, cần Spring Framework, các lớp domain/repository và cấu hình ứng dụng tương ứng; **không phải chương trình Java độc lập**.

~~~java
@Configuration
@EnableCaching
class CacheConfig {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }
}

@Service
class ProductService {
    private final ProductRepository repository;

    ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "products", key = "#id")
    public Product findById(long id) {
        return repository.findById(id).orElseThrow();
    }

    @CacheEvict(cacheNames = "products", key = "#id")
    public void rename(long id, String newName) {
        repository.rename(id, newName);
    }
}
~~~

Ở đây, `Product` và `ProductRepository` là các kiểu nghiệp vụ giả định. `@EnableCaching` bật cơ chế cache annotation; `CacheManager` chọn nơi chứa cache. `@Cacheable` cho phép dùng kết quả đã lưu theo key `id` và bỏ qua phần thân phương thức khi có hit. `@CacheEvict` mặc định xóa entry **sau khi phương thức chạy thành công**, để lần đọc tiếp theo lấy dữ liệu mới. `@CachePut` là lựa chọn khác khi muốn **luôn chạy phương thức** và đưa kết quả trả về vào cache.

`ConcurrentMapCacheManager` là implementation trong bộ nhớ, tiện cho học tập hoặc tình huống đơn giản; nó không tự cung cấp TTL như một cache provider có chính sách hết hạn. Khi ứng dụng chạy nhiều instance, cache trong RAM của từng instance không tự đồng bộ. Có thể dùng Caffeine để quản lý bộ nhớ/TTL cục bộ hoặc Redis và provider thích hợp cho cache dùng chung; cấu hình timeout, serialization, version và invalidation phụ thuộc hệ thống thực tế.

**Những giới hạn thường bị bỏ sót:**

1. Annotation cache kiểu proxy thường chỉ phát huy tác dụng khi đi **qua Spring proxy**; tự gọi `this.findById(id)` từ một phương thức trong cùng object có thể bỏ qua interception.
2. Cập nhật database và thay đổi cache không tự nhiên là một giao dịch nguyên tử. Với thao tác có transaction, phải xem thời điểm commit, rollback và invalidation; đừng mặc nhiên cho rằng `@CacheEvict` giải quyết mọi race condition.
3. Không cache mù quáng kết quả phụ thuộc người dùng/quyền nếu key không phân biệt ngữ cảnh. Xóa hoặc thay đổi quyền cũng cần làm mất hiệu lực dữ liệu đã cache.
4. Hit ratio cao không đồng nghĩa dữ liệu đúng. Cần theo dõi stale read, mức dùng bộ nhớ, thời gian tải lại, lỗi provider và số lần truy cập nguồn khi cache miss.

## 3. Buffer: giữ dữ liệu trên đường đi, không phải kho kết quả truy vấn

Buffer phục vụ quá trình **truyền hoặc xử lý luồng**. Ví dụ, khi đọc tệp từng byte, `BufferedInputStream` có thể đọc nhiều byte từ nguồn vào một vùng nhớ rồi phục vụ nhiều lần `read()` nhỏ. Nhờ vậy giảm số lần chạm nguồn I/O đắt hơn. `BufferedWriter` thường gom dữ liệu ghi và chuyển xuống đích khi đủ chỗ, khi gọi `flush()` hoặc khi đóng đúng cách.

~~~text
Nguồn I/O → [buffer chứa một khối byte] → bên đọc tiêu thụ lần lượt
Bên ghi   → [buffer gom nhiều lần write] → đích I/O
~~~

Khác với cache theo key, một buffer thường không có khái niệm **hit/miss cho cùng một truy vấn nghiệp vụ**. Dữ liệu được tiêu thụ, ghi ra hoặc thay thế theo tiến trình luồng. Trong pipeline bất đồng bộ, buffer/queue có giới hạn dung lượng có thể hấp thụ chênh lệch tốc độ tạm thời; khi bên nhận chậm kéo dài, cần backpressure, giới hạn kích thước hoặc chính sách xử lý quá tải. Buffer **không làm database bền vững hơn** và cũng không bảo đảm response của người dùng được lưu để dùng ở request kế tiếp.

Ví dụ phân biệt:

- Đọc một tệp lớn bằng `BufferedInputStream`: buffer tiết kiệm thao tác đọc nhỏ; lần gọi tải tệp khác không tự nhận kết quả cũ từ buffer.
- Cache nội dung tệp theo đường dẫn/phiên bản: lần yêu cầu tiếp theo có thể dùng kết quả đã giữ, nhưng phải kiểm tra file thay đổi.
- Spring MVC/Servlet có cơ chế ghi response hoặc đọc request theo buffer; việc HTTP response được *truyền qua buffer* không có nghĩa trình duyệt hay CDN được phép *cache* response đó.

## 4. Database: nơi giữ sự thật nghiệp vụ

Với hệ thống bán hàng, database thường là nơi lưu tên sản phẩm, đơn hàng, tồn kho, các thay đổi được xác nhận và các ràng buộc. Nó hỗ trợ các chức năng mà cache không thay thế được: cập nhật theo nghiệp vụ, truy vấn linh hoạt, khóa/ràng buộc, transaction và thường là khả năng phục hồi sau lỗi.

Một cache chứa `products:42 → "Java"` không cho phép suy ra database đã đổi khi cache bị chỉnh. Nếu cache bị xóa và hệ thống được thiết kế đúng, ứng dụng phải còn khả năng lấy hoặc tái tạo thông tin từ nguồn có thẩm quyền. Ngược lại, xóa nhầm bản ghi database thường là thay đổi nghiệp vụ cần xử lý bằng backup hoặc cơ chế phục hồi.

Không phải mọi database đều lưu bền trên đĩa, và không phải mọi cache đều mất khi khởi động lại: có database in-memory và cache phân tán có persistence. Tiêu chí là **hợp đồng dữ liệu**. Một hệ thống có thể dùng Redis làm primary data store nếu thiết kế như vậy; khi đó gọi nó là “cache có thể xóa thoải mái” sẽ sai.

**Luồng cập nhật thường thấy:**

~~~text
Ghi thay đổi → Database xác nhận theo nghiệp vụ
            → cập nhật/xóa application cache tương ứng
            → HTTP cache hết hạn, revalidate hoặc được purge theo policy
~~~

Đây là các trách nhiệm riêng. Thay đổi ở database **không tự động** làm browser cache hay mọi cache của từng service bị xóa. Nếu tồn kho đòi hỏi độ mới cao, nên chọn một chính sách phù hợp và xử lý giao dịch/đồng thời cẩn thận; không dựa vào TTL tùy tiện.

## 5. HTTP cache: cache response theo quy tắc HTTP

Trong kiến trúc web, response có thể được tái sử dụng **trước khi request chạm đến Spring Controller**:

~~~text
Browser → [browser HTTP cache] → [CDN/proxy cache] → Spring Controller
                                                        ↓
                                                  Spring service cache
                                                        ↓
                                                     Database
~~~

HTTP cache đánh giá response dựa trên thông tin request và chỉ dẫn HTTP; nó không đọc trực tiếp annotation `@Cacheable` hay biết key nội bộ của `CacheManager`.

Các chỉ dẫn/validator thường gặp:

| HTTP header | Ý nghĩa thực tế |
|---|---|
| `Cache-Control: max-age=60` | Response có thể được coi là fresh trong khoảng 60 giây theo quy tắc tính tuổi của HTTP cache. |
| `Cache-Control: private` | Response dành cho private cache, chẳng hạn cache trình duyệt; shared cache không được lưu. |
| `Cache-Control: public` | Cho phép shared cache lưu response khi các điều kiện khác cũng hợp lệ; phải cân nhắc dữ liệu có phân quyền. |
| `Cache-Control: no-cache` | Có thể lưu response, **nhưng phải xác thực lại trước khi tái sử dụng**. |
| `Cache-Control: no-store` | Chỉ dẫn không lưu response vào cache; không phải lệnh xóa mọi bản đã cache từ trước. |
| `ETag` và request `If-None-Match` | Validator so phiên bản representation; nếu không đổi, origin có thể trả `304 Not Modified`. |
| `Last-Modified` và `If-Modified-Since` | Cách revalidate dựa trên mốc sửa đổi; cần nguồn timestamp đáng tin. |
| `Vary` | Khai báo request headers ảnh hưởng representation để cache phân biệt biến thể đúng. |

Ví dụ một endpoint trả thông tin không dành cho shared cache:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, max-age=60
ETag: "product-42-v7"

{"id":42,"name":"Java"}
~~~

Trong khi response còn fresh, trình duyệt có thể dùng bản lưu mà không gửi request mới. Khi cần revalidate, trình duyệt có thể gửi:

~~~http
GET /products/42 HTTP/1.1
Host: example.test
If-None-Match: "product-42-v7"
~~~

Nếu representation ở server **chưa đổi**, phản hồi hợp lệ có thể là:

~~~http
HTTP/1.1 304 Not Modified
Cache-Control: private, max-age=60
ETag: "product-42-v7"
~~~

`304` **không mang response body**; client tiếp tục dùng body đã lưu theo metadata cập nhật. Nếu resource đã đổi, server thường trả `200 OK` với body và validator mới. Đây là quá trình **revalidation HTTP**, khác với hit/miss của `@Cacheable`. API muốn xử lý conditional request phải có cơ chế thiết lập validator và đánh giá điều kiện; chỉ thêm `ETag` như một chuỗi văn bản không tự tạo ra toàn bộ quy trình.

**Vấn đề an toàn và tính đúng:** response mang dữ liệu người dùng không được vô tình đưa vào shared cache. Dùng chính sách phù hợp như `private` hoặc `no-store`, đồng thời thiết kế đúng phân quyền, cookie/Authorization và `Vary`. `max-age=60` có thể cho phép người dùng thấy dữ liệu cũ trong thời gian còn fresh; xóa application cache ở server không làm browser lập tức quên bản HTTP đã lưu.

## 6. Minh họa Java 17 chạy độc lập: cache theo key và buffer theo luồng

Ví dụ này chỉ dùng JDK 17+, không cần Spring. `Map database` mô phỏng **nguồn có thẩm quyền trong chương trình**, **không phải database thật hay cơ chế lưu bền**. `Map cache` mô phỏng bộ nhớ đệm đọc theo key. `BufferedInputStream` minh họa cách đọc một luồng byte qua buffer; nguồn `ByteArrayInputStream` chỉ dùng để giữ ví dụ tự chạy, không dùng đo hiệu năng I/O.

Lưu tệp `CacheBufferDemo.java`:

~~~java
import java.io.BufferedInputStream;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

public class CacheBufferDemo {
    private static final Map<Long, String> database = new HashMap<>();
    private static final Map<Long, String> cache = new HashMap<>();

    private static String findProduct(long id) {
        if (cache.containsKey(id)) {
            System.out.println("CACHE HIT");
            return cache.get(id);
        }
        System.out.println("CACHE MISS -> DATABASE");
        String result = database.get(id);
        if (result == null) {
            throw new IllegalArgumentException("Unknown product: " + id);
        }
        cache.put(id, result);
        return result;
    }

    private static void renameProduct(long id, String newName) {
        database.put(id, newName);
        cache.remove(id);
    }

    public static void main(String[] args) throws IOException {
        database.put(1L, "Java");

        System.out.println(findProduct(1L));
        System.out.println(findProduct(1L));

        renameProduct(1L, "Java 21");
        System.out.println(findProduct(1L));

        byte[] bytes = "AB".getBytes(StandardCharsets.US_ASCII);
        try (BufferedInputStream buffer =
                 new BufferedInputStream(new ByteArrayInputStream(bytes))) {
            System.out.println("BUFFER READ: " + (char) buffer.read());
            System.out.println("BUFFER READ: " + (char) buffer.read());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CacheBufferDemo.java
java CacheBufferDemo
~~~

Stdout chính xác:

~~~text
CACHE MISS -> DATABASE
Java
CACHE HIT
Java
CACHE MISS -> DATABASE
Java 21
BUFFER READ: A
BUFFER READ: B
~~~

Giải thích: lượt `findProduct(1L)` đầu tiên miss, lần hai hit; `renameProduct` cập nhật nguồn và xóa cache nên lượt tiếp theo phải đọc nguồn lần nữa. Hai lần `read()` lấy hai byte nối tiếp từ stream, không phải hai lượt truy vấn có key. Demo chạy một luồng và không xét tranh chấp đồng thời; ứng dụng thật cần cơ chế cache thread-safe, chính sách hết hạn/đồng bộ và xử lý lỗi nguồn.

## 7. Chọn đúng công cụ theo tình huống

| Câu hỏi nghiệp vụ/kỹ thuật | Nên nghĩ đến | Vì sao |
|---|---|---|
| Cùng danh mục sản phẩm bị đọc nhiều lần; truy vấn DB tốn thời gian? | Application cache (`@Cacheable` + provider phù hợp) | Tránh tính toán/truy vấn lại; cần key, TTL và invalidation. |
| Đọc tệp mạng/tệp đĩa theo nhiều lần đọc nhỏ? | Buffer | Gom I/O và quản lý luồng dữ liệu. |
| Đơn hàng phải được xác nhận, ghi vết và truy vấn đúng trạng thái? | Database/transaction | Đây là nguồn trạng thái nghiệp vụ; cache chỉ tối ưu phần đọc nếu hợp lý. |
| Người dùng tải lại ảnh hoặc response GET giống nhau? | HTTP cache | Giảm round trip và có thể tránh chạm backend; dùng validator/cache policy. |
| Dữ liệu API sau đăng nhập có thể khác theo từng người? | Thiết kế key cache và HTTP policy theo quyền | Tránh trả nhầm dữ liệu giữa người dùng; tránh shared caching không phù hợp. |
| Backend đã evict nhưng trang vẫn hiện bản cũ? | Kiểm tra thêm HTTP cache và frontend state | Các tầng lưu bản sao độc lập, không tự invalidation dây chuyền. |

### Trường hợp có nhiều tầng cache

Một request `GET /products/42` có thể:
1. Được browser trả từ HTTP cache: **không có HTTP request tới backend**.
2. Đi qua HTTP cache nhưng được CDN trả: **Spring không nhận request**.
3. Tới Spring nhưng `@Cacheable` hit: **không truy vấn repository**.
4. Tới Spring và application cache miss: **đọc database rồi nạp cache**.

Vì vậy, quan sát “DB không bị query” **chưa đủ để xác định** tầng nào cache đã hoạt động. Khi debug, hãy kiểm tra network/request headers và status (`200`/`304`), log Controller/Service, thống kê cache hit/miss và truy vấn database tương ứng. Tránh nhầm “buffered response” trong server với “response đã được browser cache”.

## 8. Lỗi thường gặp và nguyên tắc ghi nhớ

- **Dùng cache thay database:** cache có thể bị eviction, hết hạn hoặc mất dữ liệu; nguồn có thẩm quyền và trách nhiệm giao dịch phải rõ ràng.
- **Nhầm buffer là cache truy vấn:** buffer phục vụ luồng đọc/ghi; nó không tự tái sử dụng kết quả nghiệp vụ theo key giữa các request.
- **Tưởng HTTP cache và `@Cacheable` là một:** chúng hoạt động tại hai tầng, key và invalidation riêng.
- **Tưởng `no-cache` nghĩa là cấm lưu:** thực tế nó yêu cầu revalidate trước khi tái sử dụng; `no-store` mới là chỉ dẫn không lưu.
- **Quên invalidation:** DB đã cập nhật nhưng application cache hoặc HTTP cache vẫn có thể chứa bản cũ.
- **Bỏ sót dữ liệu ảnh hưởng key:** ID giống nhau nhưng tenant, quyền, locale hoặc tham số khác nhau có thể cần các entry khác nhau.
- **Bỏ qua tài nguyên và đồng thời:** cache quá lớn gây áp lực bộ nhớ; hot key/cache stampede có thể làm nhiều request cùng rơi về DB khi miss; buffer không giới hạn có thể gây tràn RAM.
- **Cho rằng có annotation là bảo đảm hit:** phải bật caching, có `CacheManager` phù hợp, gọi qua proxy khi dùng proxy mode và đo thống kê thực tế.

**Tự kiểm tra:** (1) Trong một thao tác upload tệp, byte đang chờ ghi thuộc buffer hay cache truy vấn? (2) Nếu response được browser phục vụ mà Spring Controller không chạy, tầng nào có thể chịu trách nhiệm? (3) Khi giá sản phẩm thay đổi, việc xóa entry `@Cacheable` có đủ để xóa bản đã lưu trong CDN hay không? (4) Vì sao một kết quả phân quyền theo tenant không nên dùng cache key chỉ có ID?

**Đáp án gợi ý:** (1) Buffer. (2) HTTP cache phía browser hoặc cache trung gian. (3) Không; HTTP cache có chính sách và cơ chế quản lý riêng. (4) Dễ dùng nhầm dữ liệu giữa các tenant vì key thiếu ngữ cảnh.

## 9. Tài liệu tham khảo

- Spring Framework Reference — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework Reference — Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- MDN — HTTP Caching: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching
- MDN — Cache-Control: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control

**Ghi nhớ cuối bài:** **database** giữ trạng thái nghiệp vụ có thẩm quyền; **buffer** giúp dữ liệu đi qua luồng hiệu quả; **application cache** giúp kết quả xử lý/truy vấn được tái sử dụng; **HTTP cache** giúp response web được tái sử dụng theo quy tắc HTTP. Chọn đúng tầng và thiết kế **key, độ mới, invalidation, phân quyền** trước khi tối ưu tốc độ.