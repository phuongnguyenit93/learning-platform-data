# @CachePut: Luôn thực thi phương thức và cập nhật kết quả vào cache

## 1. @CachePut giải quyết bài toán gì?

Khi một ứng dụng Spring sử dụng cache để giảm các lần đọc dữ liệu, kết quả đọc có thể vẫn nằm trong cache ngay cả sau khi dữ liệu nguồn đã thay đổi. `@CachePut` giúp **ghi kết quả mới của một phương thức vào cache**. Điểm quan trọng là **phương thức được gọi thực sự vẫn chạy**: Spring không lấy giá trị cũ trong cache để bỏ qua lời gọi phương thức như cơ chế của `@Cacheable`.

Giả sử ứng dụng quản lý sản phẩm:

- `getProduct(7)` đọc sản phẩm có ID 7, có thể tận dụng cache ở lần đọc sau.
- `renameProduct(7, "Tên mới")` phải thực hiện logic cập nhật dữ liệu và trả về sản phẩm sau cập nhật.
- `@CachePut` trên `renameProduct` có thể ghi sản phẩm vừa trả về vào **đúng key mà `getProduct` sử dụng**.
- Lần `getProduct(7)` tiếp theo có thể lấy sản phẩm mới từ cache mà không đọc database.

Hãy nhớ hợp đồng của annotation: **thực thi phương thức trước, rồi đưa kết quả trả về vào cache khi điều kiện cho phép**. Mục đích chính là *đồng bộ/nạp một giá trị cache từ kết quả đã tính hoặc đã lưu*, không phải tránh chạy phương thức cập nhật.

## 2. So sánh @CachePut, @Cacheable và @CacheEvict

| Annotation | Khi cache đã có entry cùng key | Hành động với cache | Mục đích |
|---|---|---|---|
| `@Cacheable` | Có thể trả ngay giá trị cache, **không gọi thân phương thức** | Cache miss: chạy phương thức rồi có thể cache kết quả | Tối ưu các lần **đọc/tính toán lặp** |
| `@CachePut` | **Vẫn gọi thân phương thức** | Sau khi có kết quả, **ghi/thay thế** entry theo key nếu được phép | Làm mới hoặc nạp giá trị cache từ lần thực thi mới |
| `@CacheEvict` | Phương thức không bị bỏ qua chỉ vì có cache hit | Xóa một key hoặc toàn bộ cache theo cấu hình | Loại bỏ giá trị đã lỗi thời hoặc không còn dùng được |

Cùng một bộ dữ liệu có thể dùng cả ba annotation nhưng **trên những phương thức có trách nhiệm khác nhau**:

~~~text
READ:  @Cacheable
client ──► get(id) ──► cache hit ──► trả kết quả, có thể bỏ qua database
                   └─► cache miss ─► đọc database ─► ghi cache ─► trả kết quả

WRITE: @CachePut
client ──► update(id, newValue)
                ├─► luôn chạy logic cập nhật (kể cả cache có key id)
                ├─► trả về bản ghi đã lưu thành công
                └─► put(cacheName, key=id, value=result)

DELETE: @CacheEvict
client ──► delete(id) ─► thực hiện xóa ở nguồn ─► evict(cacheName, id)
~~~

**“Luôn chạy” có một điều kiện ngữ cảnh:** câu này mô tả **lời gọi phương thức được Spring cache interceptor xử lý**. Nếu một phương thức gọi một phương thức khác trên chính `this` trong chế độ proxy mặc định, annotation có thể không được intercept; thân phương thức vẫn thực thi như Java thông thường nhưng sẽ **không có thao tác cache tự động**.

## 3. Cơ chế của một lời gọi @CachePut

Giả sử annotation:

~~~java
@CachePut(cacheNames = "products", key = "#p0")
public Product renameProduct(long id, String newName) {
    return repository.save(new Product(id, newName));
}
~~~

Đoạn trên là **mã minh họa tích hợp vào Spring**. `Product` và `repository` đại diện cho domain và tầng lưu dữ liệu; cấu hình bean/cache sẽ được bổ sung ở phần sau.

Một lần gọi `renameProduct(7L, "Bản mới")` được hiểu theo các bước:

1. Client gọi phương thức **thông qua Spring bean/proxy**.
2. Logic của `renameProduct` vẫn chạy, **không tra cache để quyết định bỏ qua thân phương thức**.
3. Repository xử lý lưu dữ liệu. Phương thức trả về `Product` đã lưu.
4. Với lần thực thi thành công và điều kiện cache cho phép, Spring tính key bằng SpEL `#p0` = `7L`, chọn cache `products` và gọi thao tác ghi giá trị tương đương `Cache.put(7L, savedProduct)`.
5. Lời gọi trả về cùng giá trị kết quả của phương thức. Nếu trước đó có một entry cũ tại key 7, entry được thay bằng giá trị mới theo semantics của cache provider.

Ví dụ dưới đây minh họa trạng thái cùng một key:

| Thời điểm | Dữ liệu nguồn | Cache `products[7]` | Kết quả |
|---|---|---|---|
| Ban đầu | `Product(7, "Cũ")` | Không có | Chưa đọc |
| `getProduct(7)` lần đầu | `"Cũ"` | `"Cũ"` | Cache miss, nạp dữ liệu |
| `getProduct(7)` lần hai | `"Cũ"` | `"Cũ"` | Cache hit |
| `renameProduct(7, "Mới")` | `"Mới"` | `"Mới"` | Chạy phương thức và put giá trị mới |
| `getProduct(7)` tiếp theo | `"Mới"` | `"Mới"` | Có thể cache hit với giá trị mới |

Annotation không tự biết database nào phải cập nhật. **Mọi thay đổi nghiệp vụ nằm trong thân phương thức**; `@CachePut` chỉ làm việc với kết quả và cache theo chính sách đã khai báo.

## 4. Ví dụ tích hợp Spring: đọc bằng @Cacheable, cập nhật bằng @CachePut

Ví dụ dưới dùng hai phương thức khác nhau nhưng **cùng cache name** và **cùng cách tạo key**. Nó là phần mã minh họa cho ứng dụng có Spring Framework; muốn chạy cần implementation `ProductRepository` và cấu hình dependency/bean tương ứng.

~~~java
import java.util.Optional;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

record Product(long id, String name) {}

interface ProductRepository {
    Optional<Product> findById(long id);
    Product save(Product product);
}

@Service
class ProductService {
    private final ProductRepository repository;

    ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "products", key = "#p0")
    public Product getProduct(long id) {
        return repository.findById(id).orElseThrow();
    }

    @CachePut(cacheNames = "products", key = "#p0")
    public Product renameProduct(long id, String newName) {
        Product current = repository.findById(id).orElseThrow();
        return repository.save(new Product(current.id(), newName));
    }
}
~~~

Với `getProduct(7)`, `#p0` trỏ tới đối số `id`. Với `renameProduct(7, "Mới")`, `#p0` cũng là `id`, dù phương thức cập nhật có thêm tham số `newName`. **Vì cả hai key đều bằng 7 và cache name đều là `products`, phương thức ghi cập nhật đúng entry mà phương thức đọc tìm kiếm.**

Tại sao phải ghi rõ `key = "#p0"` trên phương thức cập nhật? Nếu bỏ thuộc tính `key`:

- `getProduct(long id)` có một tham số nên key mặc định thường là chính giá trị `id`.
- `renameProduct(long id, String newName)` có hai tham số nên key mặc định là `SimpleKey(id, newName)`.
- Hai key **khác nhau**. Cache có thể chứa entry với key tổng hợp trong khi `getProduct(7)` vẫn đọc entry cũ theo key `7`.

Cùng tên cache **chưa đủ**. Phải thống nhất **key, kiểu key, namespace/tenant và cache provider** giữa các phương thức tương tác cùng entry.

### Bật caching và cấu hình cache manager

Một cấu hình minh họa sử dụng cache in-memory của Spring:

~~~java
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
class CacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }
}
~~~

`@EnableCaching` kích hoạt hỗ trợ annotation cache; `CacheManager` quản lý cache có tên `products`. Khi chạy Spring Boot, cần dependency/cache provider phù hợp với dự án (ví dụ Spring cache abstraction thông qua starter tương ứng). `ConcurrentMapCacheManager` tiện cho ví dụ đơn giản nhưng giữ dữ liệu trong bộ nhớ từng instance và **không tự có TTL**. Hệ thống thực cần chọn provider (ví dụ Caffeine hoặc Redis), cấu hình thời hạn, dung lượng, serialization và chiến lược invalidation phù hợp.

### Cùng key cũng có nghĩa là cùng ý nghĩa dữ liệu

Ví dụ chỉ an toàn nếu dữ liệu `Product` theo ID 7 có ý nghĩa thống nhất trong các lần gọi. Nếu có multi-tenant, ngôn ngữ, phiên bản sản phẩm hoặc quyền truy cập ảnh hưởng kết quả, key phải chứa đủ ngữ cảnh. Không nên dùng key chỉ là ID khi hai tenant có thể cùng dùng ID 7 nhưng dữ liệu khác nhau.

## 5. CachePut ghi **giá trị trả về**, không mặc nhiên ghi tham số

Xét phương thức:

~~~java
@CachePut(cacheNames = "products", key = "#p0")
public Product renameProduct(long id, String proposedName) {
    return repository.renameAndReturnSaved(id, proposedName);
}
~~~

Database có thể chuẩn hóa tên, cập nhật timestamp hoặc tạo phiên bản mới. Giá trị đưa vào cache là **`Product` mà phương thức trả về**, không tự động là `proposedName` hoặc một entity cũ mà caller đã có.

Đây là lý do thường nên cho phương thức cập nhật trả về **trạng thái cuối cùng đã được lưu**. Nếu ghi vào database mà trả về giá trị chưa đồng bộ, cache cũng có thể nhận dữ liệu chưa đúng nghiệp vụ.

### Khi ID do database sinh ra: key có thể lấy từ kết quả

Đôi khi phương thức tạo dữ liệu không nhận ID vì database tạo ID sau khi lưu. Khi đó, `@CachePut` có thể dùng `#result` để xác định key sau khi method trả về:

~~~java
@CachePut(cacheNames = "products", key = "#result.id")
public Product createProduct(CreateProductCommand command) {
    return repository.insertAndReturnSaved(command);
}
~~~

Đây là mã minh họa tích hợp; `CreateProductCommand`, `Product` và repository là các kiểu/bean của ứng dụng. Ví dụ giả định `Product` trả về khác `null`, và Spring SpEL có thể đọc thuộc tính `id` của entity. Nếu dùng JavaBean, getter `getId()` là cách rõ ràng. Khi ID là `7`, entry được ghi dưới key 7 và có thể được đọc bởi `getProduct(7)`.

**Khác biệt thiết yếu:** `@CachePut` có thể dùng `#result` trong biểu thức tạo key vì việc put xảy ra sau khi kết quả đã có. `@Cacheable` phải xác định key để **tra cache trước khi quyết định chạy**; không dùng `#result` cho key theo cách này.

## 6. condition và unless: kiểm soát *việc ghi cache*, không kiểm soát *việc chạy phương thức*

`@CachePut` cũng hỗ trợ các thuộc tính SpEL như `condition` và `unless`.

~~~java
@CachePut(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 > 0",
    unless = "#result == null"
)
public Product refreshProduct(long id) {
    return repository.findById(id).orElse(null);
}
~~~

- **`condition`:** chỉ cho phép thao tác cache nếu biểu thức đúng. Với `@CachePut`, biểu thức điều kiện được đánh giá sau khi method được gọi theo bản chất của thao tác put; **không biến `@CachePut` thành `@Cacheable`**.
- **`unless`:** loại trừ việc ghi cache khi biểu thức đúng. Ở đây, trả về `null` thì bỏ qua put. Nếu không có `unless`, hành vi lưu `null` phụ thuộc cách cache/provider xử lý null và cấu hình cụ thể.
- **`key`:** tính key để ghi. `#p0` truy cập đối số đầu tiên theo chỉ số.
- **`#result`:** truy cập giá trị trả về sau khi method hoàn tất. Với các wrapper được hỗ trợ, như `Optional<T>`, Spring có thể dùng giá trị nghiệp vụ đã được unwrap theo quy tắc của cache abstraction.

Nếu `condition` là `false`, Spring không thực hiện cache put, nhưng **`refreshProduct` vẫn chạy**. Nếu `unless` là `true`, Spring cũng bỏ qua ghi cache nhưng không “hoàn tác” logic đã chạy. Không sử dụng các điều kiện này như cơ chế kiểm soát giao dịch, xác thực người dùng hoặc tránh thực thi thao tác cập nhật.

### Cú pháp tham số trong SpEL

| Biểu thức | Ý nghĩa | Phụ thuộc metadata tên tham số |
|---|---|---|
| `#id` | Tham số Java đặt tên `id` | Có, khi cần Spring khám phá được tên |
| `#p0` hoặc `#a0` | Tham số thứ nhất | Không |
| `#p1` hoặc `#a1` | Tham số thứ hai | Không |
| `#root.args[0]` | Tham số thứ nhất qua root object | Không |
| `#result` | Kết quả trả về sau thực thi, tại ngữ cảnh được hỗ trợ | Không phụ thuộc tên tham số |

Với Java, có thể cần biên dịch bằng `javac -parameters` để `#id` hoạt động tin cậy. Ví dụ trong bài ưu tiên `#p0` để không phụ thuộc metadata tên.

## 7. Khi phương thức lỗi, trả về void, trả về null hoặc chạy bất đồng bộ

**Ném exception:** nếu thân phương thức ném lỗi trước khi có kết quả thành công, Spring không có giá trị trả về thành công để ghi bằng `@CachePut`. Tuy vậy, cần kiểm tra chính xác thay đổi dữ liệu đã xảy ra trước exception: nếu logic cập nhật không được rollback nhưng cache cũ vẫn tồn tại, ứng dụng có thể thấy stale read. Exception không tự hoàn tác mọi side effect.

**Trả về `void`:** `@CachePut` không phù hợp để “ghi entity vừa lưu” vì không có giá trị entity trả về. Nếu phương thức chỉ báo hiệu thay đổi rồi không thể trả entity mới, cân nhắc `@CacheEvict` để xóa entry và tải lại ở lần đọc kế tiếp; hoặc thiết kế API cập nhật trả entity cuối cùng.

**Trả về `null`:** chính sách lưu null tùy provider và cấu hình; có provider lưu qua sentinel, có nơi không chấp nhận. Có thể dùng `unless = "#result == null"` nếu bài toán muốn bỏ qua cache với kết quả null. Tránh đặt key `#result.id` nếu kết quả có thể null mà chưa xử lý tình huống này một cách an toàn.

**Kết quả bất đồng bộ/reactive:** từ Spring Framework 6.1, cache annotations hỗ trợ thích ứng `CompletableFuture` và các kiểu trả về reactive được hỗ trợ; `@CachePut` thực hiện put khi giá trị được tạo ra, theo hỗ trợ và khả năng của provider. Không suy luận rằng gọi một phương thức trả `Mono<T>` luôn ghi trực tiếp chính object `Mono` vào cache. Cơ chế tùy kiểu trả về, version và cấu hình cache, nên cần test với stack thực tế.

## 8. Ví dụ Java 17 chạy độc lập: mô phỏng hành vi đọc và put

Ví dụ này **mô phỏng semantics** của `@Cacheable` và `@CachePut` bằng hai `Map`. Nó **không thực thi Spring proxy hay annotation thật**; mục đích là quan sát rõ việc **update luôn chạy** ngay cả khi key đã có trong cache, và kết quả update được ghi lại dưới cùng key.

Tạo tệp **`CachePutDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class CachePutDemo {
    record Product(long id, String name) {}

    private final Map<Long, Product> database = new HashMap<>();
    private final Map<Long, Product> cache = new HashMap<>();
    private int readFromDatabaseCount = 0;
    private int updateCount = 0;

    CachePutDemo() {
        database.put(7L, new Product(7L, "Bản gốc"));
    }

    Product findById(long id) {
        Product cached = cache.get(id);
        if (cached != null) {
            System.out.println("READ: cache hit");
            return cached;
        }
        System.out.println("READ: cache miss");
        readFromDatabaseCount++;
        Product result = database.get(id);
        if (result != null) {
            cache.put(id, result);
        }
        return result;
    }

    Product update(long id, String name) {
        updateCount++;
        System.out.println("UPDATE: method executed " + updateCount);
        Product saved = new Product(id, name);
        database.put(id, saved);
        cache.put(id, saved);
        return saved;
    }

    public static void main(String[] args) {
        CachePutDemo demo = new CachePutDemo();
        System.out.println("Name: " + demo.findById(7L).name());
        System.out.println("Name: " + demo.findById(7L).name());

        demo.update(7L, "Bản A");
        demo.update(7L, "Bản B");
        System.out.println("Name: " + demo.findById(7L).name());

        System.out.println("Database reads: " + demo.readFromDatabaseCount);
        System.out.println("Method updates: " + demo.updateCount);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 CachePutDemo.java
java CachePutDemo
~~~

Kết quả stdout chính xác:

~~~text
READ: cache miss
Name: Bản gốc
READ: cache hit
Name: Bản gốc
UPDATE: method executed 1
UPDATE: method executed 2
READ: cache hit
Name: Bản B
Database reads: 1
Method updates: 2
~~~

**Phân tích:**

1. Lần đọc thứ nhất phải tìm trong “database” mô phỏng và nạp cache. Lần đọc thứ hai lấy dữ liệu có sẵn.
2. Hai lần gọi `update(7, ...)` **đều thực thi**, in ra hai thông báo; code không dùng cache hit để bỏ qua update.
3. Mỗi lần update ghi dữ liệu mới vào nguồn và thay entry `cache[7]`; lần đọc cuối là cache hit nhưng trả **“Bản B”**.
4. Bộ đếm cho thấy database chỉ được đọc một lần, còn phương thức cập nhật đã chạy hai lần.
5. Đây là mô phỏng chạy một luồng, không thể hiện transaction, race condition, HTTP cache hay khả năng lưu bền của database thật.

## 9. Khi nào dùng @CachePut trong ứng dụng thực?

**Phù hợp:**

- Phương thức lưu/sửa entity **phải chạy** và trả về bản ghi sau khi persistence thành công.
- Phương thức refresh một giá trị quan trọng phải tính lại mọi lần được gọi, đồng thời nạp kết quả mới để các API đọc khác hưởng lợi.
- Phương thức tạo entity trả về ID mới; key của put được tính từ kết quả nếu hệ thống muốn warm cache ngay sau khi tạo.
- Luồng import hoặc đồng bộ trả về giá trị đã chuẩn hóa và bạn biết chắc cách ánh xạ nó vào key của cache đọc.

**Cân nhắc `@CacheEvict` thay thế:**

- Không có giá trị trả về đáng tin để nạp cache, hoặc nhiều dữ liệu liên quan có thể thay đổi mà chưa có bản đầy đủ.
- Thao tác xóa không còn entity để cache.
- Một cập nhật ảnh hưởng đến nhiều key/cache view, nhưng chưa có chiến lược put đầy đủ cho mọi biến thể; evict rồi tải lại có thể an toàn hơn.

**Cân nhắc chỉ dùng `@Cacheable`:**

- Mục đích chỉ là tối ưu việc đọc hoặc tính toán lặp, không cần buộc thực thi lại trên mỗi lần gọi.
- Muốn lấy kết quả cache hit thay vì truy vấn lại; `@CachePut` sẽ không giảm số lần tính toán của chính phương thức được gắn annotation.

Đặt `@Cacheable` và `@CachePut` **trên cùng một phương thức** thường gây xung đột ngữ nghĩa: một annotation có thể bỏ qua lời gọi khi hit, annotation còn lại cần gọi để cập nhật. Spring khuyến cáo tránh kết hợp này, trừ các trường hợp rất hẹp có điều kiện loại trừ lẫn nhau được thiết kế và kiểm thử rõ ràng.

## 10. Giới hạn về tính nhất quán, transaction và nhiều instance

`@CachePut` cập nhật một bản sao giá trị. Nó **không tự biến database và cache thành một giao dịch nguyên tử**.

- **Thứ tự commit:** nếu phương thức cập nhật dùng `@Transactional`, hãy xác nhận thời điểm ghi cache so với transaction commit và rollback; interceptor order hoặc transaction-aware cache có thể ảnh hưởng hành vi. Không mặc nhiên kết luận cache chỉ thay đổi sau commit chỉ vì phương thức có hai annotation.
- **Lỗi cache provider:** database lưu thành công nhưng thao tác put có thể thất bại; chiến lược retry, lỗi trả về và reconciliation cần được thiết kế cho nghiệp vụ.
- **Nhiều instance:** `ConcurrentMapCacheManager` có map riêng tại mỗi process. Một instance cập nhật entry không tự đồng bộ map của các instance khác. Cache phân tán hoặc cơ chế invalidation liên instance là lựa chọn kiến trúc riêng.
- **Đọc–ghi đồng thời:** một thao tác đọc miss có thể truy vấn dữ liệu cũ và put trễ **sau** khi một thao tác cập nhật đã put dữ liệu mới. Vì thế “có `@CachePut`” không bảo đảm mọi lần đọc đều nhất quán tuyến tính; có thể cần phiên bản dữ liệu, khóa, TTL/invalidation và thiết kế concurrency phù hợp.
- **TTL/eviction:** `@CachePut` là lệnh ghi theo API cache abstraction. Thời gian sống, chính sách thay thế, tính bền vững và serialization do provider quản lý; annotation không tự định nghĩa TTL.
- **Kết quả phân quyền:** cùng ID không đủ nếu kết quả còn phụ thuộc tenant, role, locale hoặc các option khác. Cache name/key phải phân biệt các ngữ cảnh thực sự khác nhau, tránh rò rỉ dữ liệu giữa người dùng.

Khi dữ liệu nhạy cảm về tính đúng như tồn kho, giá giao dịch hoặc quyền truy cập, cần xác định **mức độ stale chấp nhận được** và kiểm thử tình huống lỗi/đồng thời trước khi dựa vào cache.

## 11. Các lỗi thường gặp khi triển khai và cách kiểm tra

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
|---|---|---|
| Update chạy nhưng đọc vẫn thấy bản cũ | `@CachePut` ghi khác key so với `@Cacheable`; hoặc khác cache/provider | In/đối chiếu cache name, SpEL key và kiểu key của cả hai method |
| Gắn `@CachePut` nhưng cache không đổi | Chưa bật `@EnableCaching`, chưa có CacheManager, lời gọi không qua proxy | Kiểm tra bean, configuration và đường gọi thực tế |
| Gọi `this.renameProduct(...)` vẫn chạy nhưng không put | Self-invocation bypass proxy trong mode mặc định | Gọi qua Spring bean được intercept hoặc thiết kế lại ranh giới service |
| Cập nhật database nhưng cache được nạp giá trị cũ | Method trả về object trước khi lưu hoặc không phản ánh trạng thái cuối | Trả về entity/result đã được persistence xác nhận |
| Đổi từ `#p0` sang key mặc định thì cache đọc không được cập nhật | Phương thức ghi có nhiều tham số tạo `SimpleKey` khác phương thức đọc | Khai báo key tương thích theo ý nghĩa nghiệp vụ |
| Runtime báo lỗi key null hoặc lỗi SpEL | `#result`/`#id` không sẵn có hoặc giá trị null; tên tham số không giữ trong bytecode | Kiểm tra `-parameters`, dùng `#p0`, xử lý null phù hợp |
| Không thấy lợi ích tốc độ ở phương thức update | `@CachePut` **luôn chạy** logic update | Đo chi phí ở phía đọc; dùng `@Cacheable` cho truy vấn muốn tránh chạy |
| Lỗi tại cluster dù máy local đúng | Cache cục bộ mỗi instance, race condition hoặc provider khác | Kiểm tra topology, invalidation và quan sát log/cache metrics |

### Checklist kiểm thử tích hợp

Trong test Spring sử dụng **bean từ application context**, có thể thiết kế trình tự sau:

1. Khởi tạo nguồn `Product(7, "Cũ")` và cache `products` sạch.
2. Gọi `getProduct(7)` hai lần, xác nhận repository đọc một lần khi lần đầu cache miss và lần thứ hai hit.
3. Gọi `renameProduct(7, "Mới")`, xác nhận repository **thật sự save** một lần và method trả về bản mới.
4. Gọi `getProduct(7)` lần nữa; xác nhận kết quả **“Mới”** và không phát sinh truy vấn đọc ngoài dự kiến.
5. Gọi `renameProduct(7, "Mới hơn")` lần nữa; xác nhận save lại được thực hiện dù cache đã có key.
6. Kiểm tra riêng trường hợp exception/rollback, cache provider lỗi, nhiều instance và concurrency theo mức độ quan trọng của nghiệp vụ.

Không chỉ test giá trị method trả về: cần quan sát cache entry, số lần repository được gọi và ranh giới proxy/transaction. Tránh dùng self-invocation trong test nếu mục tiêu là chứng minh caching advice đang hoạt động.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `@CachePut(cacheNames="products", key="#p0")` có bỏ qua thân phương thức khi key đã tồn tại và trả cache hit không?

**Câu 2.** `getProduct(long id)` dùng key `#p0`, còn `renameProduct(long id, String name)` bỏ trống `key`. Có chắc `renameProduct` cập nhật cùng entry không?

**Câu 3.** Khi tạo entity có ID do database cấp, tại sao `@CachePut(key="#result.id")` có thể phù hợp hơn key dựa trên input?

**Câu 4.** `unless="#result == null"` làm phương thức không chạy khi dự đoán kết quả null đúng hay sai?

**Câu 5.** `@CachePut` trên phương thức `void delete(long id)` có phải lựa chọn tốt để xóa dữ liệu cache đã cũ không?

**Câu 6.** Trong một ứng dụng ba instance dùng cache in-memory độc lập, một instance gọi `@CachePut` có tự cập nhật entry trên hai instance còn lại không?

**Đáp án:**

1. **Không.** Method vẫn chạy; kết quả có thể được put sau khi chạy.
2. **Không.** Key mặc định của hai phương thức khác số tham số sẽ khác; cần thống nhất key.
3. Vì `#result` tham chiếu kết quả sau khi ID đã được tạo và method hoàn tất thành công.
4. **Sai.** `unless` chỉ veto put; logic phương thức vẫn thực thi.
5. Thường **không**. Dùng `@CacheEvict` phù hợp hơn để xóa một key sau khi xóa dữ liệu nguồn.
6. **Không.** Mỗi process sở hữu map riêng; muốn đồng bộ phải có thiết kế cache chia sẻ/invalidation.

## 13. Tài liệu tham khảo

- Spring Framework Reference — Declarative Annotation-based Caching (phần `@Cacheable`, `@CachePut`, `@CacheEvict`, SpEL, proxy): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Reference — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework Javadoc — `CachePut` và các thuộc tính của annotation: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CachePut.html
- Spring Framework Javadoc — `Cache`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html

**Ghi nhớ:** **`@CachePut` dùng khi phương thức bắt buộc thực thi và giá trị trả về cần được đưa vào cache**. Kết quả mới chỉ giúp các lần đọc sau đúng hơn khi phương thức đọc và ghi dùng **cùng cache, cùng key và cùng ý nghĩa dữ liệu**. Cần phối hợp với `@Cacheable` cho đọc, `@CacheEvict` cho xóa và xử lý riêng transaction, concurrency cùng cache provider.