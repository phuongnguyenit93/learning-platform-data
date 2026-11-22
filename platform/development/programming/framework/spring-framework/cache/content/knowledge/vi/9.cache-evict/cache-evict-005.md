# @CacheEvict: Thời điểm xóa cache khi phương thức phát sinh ngoại lệ

## 1. Vì sao ngoại lệ làm thay đổi kết quả xóa cache?

Trong Spring Framework, `@CacheEvict` đánh dấu một phương thức có khả năng **xóa dữ liệu đã cache**. Một tình huống quan trọng xuất hiện khi phương thức được gọi để sửa hoặc xóa dữ liệu nhưng **phát sinh ngoại lệ**: liệu entry cũ trong cache còn tồn tại hay đã bị xóa?

Câu trả lời phụ thuộc chủ yếu vào thuộc tính **`beforeInvocation`**:

- **Mặc định: `beforeInvocation = false`** — Spring thực hiện eviction **sau khi phương thức kết thúc thành công**. Nếu phương thức ném ngoại lệ ra ngoài, thao tác eviction sau lời gọi **không diễn ra**.
- **`beforeInvocation = true`** — Spring thực hiện eviction **trước khi gọi thân phương thức**. Nếu phương thức sau đó ném ngoại lệ, entry đã được yêu cầu xóa; Spring không phục hồi entry chỉ vì lời gọi thất bại.

Hai cách đều có giá trị. Chọn cách nào phụ thuộc vào việc **dữ liệu cache cũ còn đúng hay không khi nghiệp vụ thất bại**, chứ không chỉ phụ thuộc mong muốn “luôn xóa” hay “chỉ xóa khi thành công”.

> Phạm vi của cam kết trên là một lời gọi **được Spring caching interceptor xử lý**, thỏa `condition`, chọn được cache/key và thao tác cache tương ứng thực hiện được. Nếu lời gọi bỏ qua Spring proxy hoặc cache provider báo lỗi, hành vi quan sát được có thể khác.

## 2. Bảng hành vi cần thuộc

Giả sử cache `products` đã chứa key `7` với giá trị `Product(7, "Cũ")`. Phương thức `rename(7, "Mới")` có `@CacheEvict` cùng key.

| Cấu hình | Phương thức kết thúc | Thời điểm yêu cầu xóa | Entry cũ sau lời gọi* |
|---|---|---|---|
| `beforeInvocation=false` (mặc định) | Trả về bình thường | Sau khi phương thức hoàn tất | Bị xóa |
| `beforeInvocation=false` | Ném ngoại lệ ra ngoài | **Không thực hiện eviction sau lời gọi** | Vẫn còn |
| `beforeInvocation=true` | Trả về bình thường | Trước khi chạy thân phương thức | Đã bị xóa |
| `beforeInvocation=true` | Ném ngoại lệ ra ngoài | Trước khi chạy thân phương thức | Đã bị xóa |

\* Bảng giả định không có request khác ghi lại key, `condition` cho phép eviction, thao tác xóa thành công, không có transaction-aware cache trì hoãn thay đổi và cache không bị tác động bởi cơ chế khác.

Điểm rất dễ nhầm: **`beforeInvocation=false` không có nghĩa chờ đến khi database transaction commit thành công trong mọi cấu hình**. Nó mô tả thứ tự tương đối với lời gọi được Spring caching advice quan sát. Thứ tự advice với `@Transactional` và hành vi của `CacheManager` có thể ảnh hưởng thời điểm xóa vật lý.

## 3. Luồng thực thi khi dùng giá trị mặc định

Annotation:

~~~java
@CacheEvict(cacheNames = "products", key = "#p0")
public void rename(long id, String newName) {
    repository.rename(id, newName);
}
~~~

Đây là **mã minh họa để tích hợp Spring**, cần bean service, repository, cache manager và `@EnableCaching` thích hợp. `#p0` trỏ tới tham số đầu tiên (`id`); cú pháp này không yêu cầu giữ tên tham số Java bằng `-parameters`.

Luồng khi repository thành công:

~~~text
Client → Spring proxy
       → gọi rename(7, "Mới")
       → repository.rename(...) thành công
       → method trả về bình thường
       → @CacheEvict tìm products[7] và yêu cầu xóa
       → caller nhận kết quả thành công
~~~

Luồng khi repository ném ngoại lệ:

~~~text
Client → Spring proxy
       → gọi rename(7, "Mới")
       → repository.rename(...) ném ngoại lệ
       → ngoại lệ truyền ngược ra proxy/caller
       → KHÔNG chạy thao tác @CacheEvict sau lời gọi
       → products[7] có thể vẫn chứa bản cũ
~~~

Với phương thức chỉ **thay đổi dữ liệu theo transaction nguyên tử**, giá trị mặc định thường có lý: nếu update thực sự thất bại và dữ liệu nguồn giữ nguyên, bản cache cũ vẫn có thể đúng. Không xóa cache giúp tránh lần đọc lại database không cần thiết.

Nhưng đây **không phải bảo đảm dữ liệu cache luôn đúng** sau khi có lỗi. Ngoại lệ có thể xảy ra **sau một số side effect đã hoàn tất**, hoặc transaction/nguồn bên ngoài không rollback đồng bộ. Khi đó, phương thức ném lỗi nhưng dữ liệu nguồn đã thay đổi một phần; entry cũ được giữ lại có thể trở thành stale.

## 4. Luồng thực thi khi beforeInvocation=true

Annotation:

~~~java
@CacheEvict(
    cacheNames = "products",
    key = "#p0",
    beforeInvocation = true
)
public void synchronizeProduct(long id) {
    externalProductGateway.synchronize(id);
}
~~~

Đây cũng là **mã tích hợp**, trong đó `externalProductGateway` là dependency nghiệp vụ. Ví dụ phù hợp khi thao tác đồng bộ có thể thay đổi nguồn ở bên ngoài rồi thất bại ở bước sau, khiến giá trị cache trước đó không còn đáng tin.

Luồng:

~~~text
Client → Spring proxy
       → xác định key 7 và kiểm tra condition nếu có
       → yêu cầu xóa products[7]
       → gọi synchronizeProduct(7)
       → thực hiện thao tác đồng bộ
       → method thành công HOẶC ném ngoại lệ
       → không "hoàn tác" eviction vì method lỗi
~~~

Nếu đồng bộ thất bại, lần đọc kế tiếp có thể cache miss và truy vấn nguồn. Đây là lý do thực tế để dùng `beforeInvocation=true` khi yêu cầu **không tiếp tục phục vụ bản cache đã có nguy cơ sai**, kể cả tác vụ thất bại.

**Đổi lại**, xóa sớm có tác dụng phụ: nếu tác vụ thất bại hoàn toàn trước khi thay đổi nguồn, bạn đã bỏ một bản cache vẫn hợp lệ. Điều này có thể làm tăng truy vấn/độ trễ không cần thiết. Ngoài ra, một request đọc song song có thể cache miss ngay sau khi xóa, lấy dữ liệu cũ từ database **trong lúc tác vụ cập nhật chưa xong** rồi ghi dữ liệu cũ trở lại cache. `beforeInvocation=true` vì vậy **không phải giải pháp nhất quán tuyệt đối cho race condition**.

## 5. Minh họa Spring: hai chiến lược cho hai thao tác khác nhau

Ví dụ service dưới tách rời phương thức sửa dữ liệu được kỳ vọng thành công nguyên tử và phương thức đồng bộ bên ngoài có thể có side effect dở dang.

~~~java
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final ProductRepository repository;
    private final ExternalProductGateway gateway;

    public ProductService(ProductRepository repository,
                          ExternalProductGateway gateway) {
        this.repository = repository;
        this.gateway = gateway;
    }

    @Cacheable(cacheNames = "products", key = "#p0")
    public Product getProduct(long id) {
        return repository.findById(id);
    }

    // Chiến lược 1: chỉ evict nếu method không ném ngoại lệ.
    @CacheEvict(cacheNames = "products", key = "#p0")
    public void rename(long id, String name) {
        repository.rename(id, name);
    }

    // Chiến lược 2: evict trước cả khi gọi thao tác đồng bộ.
    @CacheEvict(cacheNames = "products",
                key = "#p0",
                beforeInvocation = true)
    public void syncFromExternal(long id) {
        gateway.synchronize(id);
    }
}
~~~

Các kiểu `Product`, `ProductRepository`, `ExternalProductGateway` là **phụ thuộc giả định**; đoạn này minh họa cơ chế Spring, không phải tệp Java độc lập. Trong project thật cần cài dependency và định nghĩa bean tương ứng, bật hỗ trợ caching:

~~~java
@Configuration
@EnableCaching
public class CachingConfiguration {
    // Cấu hình CacheManager/provider thích hợp tại đây.
}
~~~

Cần import `org.springframework.context.annotation.Configuration` và `org.springframework.cache.annotation.EnableCaching` trong lớp cấu hình thực tế. Với hai phương thức, chú ý rằng cache name `products` và key `#p0` phải phù hợp với cách `getProduct(id)` lưu kết quả.

Nếu service có nhiều tenant, chỉ `id` có thể không đủ làm key. Ví dụ hai tenant cùng dùng ID 7 thì cache phải được phân tách theo tenant hoặc sử dụng key chứa tenant. Việc xóa sai key có thể làm entry cũ tồn tại bất kể bạn chọn `beforeInvocation` nào.

## 6. Ví dụ Java 17 chạy độc lập: chứng minh khác biệt trong bốn tình huống

Để nhìn rõ thứ tự mà không phụ thuộc thiết lập Spring, chương trình dưới **mô phỏng** interceptor với một `HashMap`. Nó không chạy annotation thật, không mô phỏng transaction hoặc tình huống ghi lại cache đồng thời.

Tạo tệp **`CacheEvictTimingDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class CacheEvictTimingDemo {
    private static void update(boolean fail) {
        System.out.println("method: start");
        if (fail) {
            throw new IllegalStateException("update failed");
        }
        System.out.println("method: success");
    }

    private static void call(Map<Long, String> cache, boolean beforeInvocation, boolean fail) {
        long id = 7L;
        if (beforeInvocation) {
            cache.remove(id);
            System.out.println("evict: before");
        }
        try {
            update(fail);
            if (!beforeInvocation) {
                cache.remove(id);
                System.out.println("evict: after");
            }
        } catch (IllegalStateException exception) {
            System.out.println("caught: " + exception.getMessage());
        }
        System.out.println("cache[7]: " + cache.get(id));
    }

    private static void scenario(boolean beforeInvocation, boolean fail) {
        Map<Long, String> cache = new HashMap<>();
        cache.put(7L, "old");
        System.out.println("case: before=" + beforeInvocation + ", fail=" + fail);
        call(cache, beforeInvocation, fail);
    }

    public static void main(String[] args) {
        scenario(false, true);
        scenario(true, true);
        scenario(false, false);
        scenario(true, false);
    }
}
~~~

Biên dịch bằng Java 17+:

~~~bash
javac --release 17 CacheEvictTimingDemo.java
java CacheEvictTimingDemo
~~~

**Stdout chính xác:**

~~~text
case: before=false, fail=true
method: start
caught: update failed
cache[7]: old
case: before=true, fail=true
evict: before
method: start
caught: update failed
cache[7]: null
case: before=false, fail=false
method: start
method: success
evict: after
cache[7]: null
case: before=true, fail=false
evict: before
method: start
method: success
cache[7]: null
~~~

Diễn giải:

1. Mặc định + exception: lệnh remove nằm **sau** `update(fail)` nên không chạy; entry `"old"` còn trong map.
2. Xóa trước + exception: remove đã chạy trước khi update ném lỗi; đọc lại key cho kết quả `null`.
3. Mặc định + thành công: method chạy xong rồi mới remove, entry bị xóa.
4. Xóa trước + thành công: remove chạy trước và method vẫn được gọi.

Trong Java mô phỏng, exception được bắt ở bên ngoài lời gọi `update` để dễ tiếp tục in kết quả. Đối với annotation Spring thật, điều quan trọng là **ngoại lệ từ method có truyền ra caching interceptor hay không**. Phần sau làm rõ trường hợp exception bị bắt bên trong.

## 7. Exception bị bắt trong phương thức: Spring có nhìn thấy thất bại không?

Một lỗi phổ biến là nghĩ rằng “đã có lỗi xảy ra” thì `beforeInvocation=false` chắc chắn không evict.

~~~java
@CacheEvict(cacheNames = "products", key = "#p0")
public boolean tryRename(long id, String newName) {
    try {
        repository.rename(id, newName);
        return true;
    } catch (RuntimeException ex) {
        logger.warn("Rename failed", ex);
        return false;
    }
}
~~~

Đây là **mã minh họa tích hợp**, `logger` và `repository` do ứng dụng cung cấp. Trong trường hợp repository ném exception nhưng method **bắt và trả `false` bình thường**, đối với Spring caching advice, lời gọi **đã kết thúc mà không ném exception**. Vì vậy, eviction sau lời gọi vẫn có thể diễn ra dù nghiệp vụ trả trạng thái thất bại.

So sánh:

| Hành vi trong thân phương thức | Spring caching advice quan sát | Evict mặc định sau lời gọi |
|---|---|---|
| `repository.rename(...)` thành công, method trả về | Thành công | Có |
| `repository.rename(...)` ném exception, không bắt | Ngoại lệ truyền ra ngoài | Không |
| Bắt exception và `return false` | Method trả về bình thường | Có |
| Bắt exception rồi `throw` lại | Ngoại lệ truyền ra ngoài | Không |
| Bắt lỗi và trả object báo thất bại | Method trả về bình thường | Có |

Điều này đúng với **ngoại lệ checked lẫn unchecked** nếu ngoại lệ thực sự thoát khỏi lời gọi; tiêu chí của Spring cache interceptor là *lời gọi có kết thúc thành công hay không*, không phải loại exception được JVM ném.

Nếu API nghiệp vụ dùng giá trị trả về `boolean` hoặc một đối tượng trạng thái để biểu thị thành công, cần thiết kế eviction theo **kết quả nghiệp vụ**, không mặc nhiên dựa vào giả định “trả false thì không evict”. Annotation `@CacheEvict` có `condition` để ra quyết định dựa trên ngữ cảnh được hỗ trợ; nó **không có thuộc tính `unless`** như `@Cacheable`/`@CachePut`. Trường hợp cần hậu kiểm một kết quả phức tạp hoặc cần xử lý các nhánh lỗi cụ thể có thể dùng quản lý cache chương trình, tách service hoặc phát sự kiện sau commit.

## 8. condition, key, allEntries và #result liên quan thế nào?

### 8.1. `beforeInvocation=true` không có nghĩa “mọi lời gọi đều bị xóa”

~~~java
@CacheEvict(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 > 0",
    beforeInvocation = true
)
public void synchronize(long id) {
    gateway.synchronize(id);
}
~~~

Nếu `id <= 0`, `condition` là false: **không evict**, dù thuộc tính `beforeInvocation` bằng true. Đó là cách thêm điều kiện có chủ đích. Cần nhớ rằng `condition` điều khiển **thao tác cache**, không mặc nhiên ngăn logic phương thức chạy.

Khi điều kiện là true và metadata/cache provider hoạt động bình thường, eviction diễn ra trước lời gọi nên không phụ thuộc việc lời gọi sau đó ném exception hay trả về.

### 8.2. Chọn key từ đối số hay kết quả

- `#p0`, `#a0` và `#root.args[0]` tham chiếu đối số thứ nhất, luôn có thể dùng ở cả hai chế độ.
- `#id` tham chiếu tên tham số Java nếu Spring tìm được tên; cần build giữ tên phù hợp, ví dụ `javac -parameters`.
- `#result` chỉ có thể được dùng ở những **ngữ cảnh eviction sau lời gọi** được Spring hỗ trợ (`beforeInvocation=false`). Trước khi method chạy chưa có kết quả, nên không chọn key của eviction-before bằng `#result.id`.

Ví dụ xóa cache theo ID do kết quả trả về cung cấp:

~~~java
@CacheEvict(cacheNames = "products",
            key = "#result.id",
            beforeInvocation = false)
public Product updateAndReturn(long id, String name) {
    return repository.updateAndReturn(id, name);
}
~~~

Mã này giả định method trả về `Product` không null và SpEL truy cập được `id`. Nếu method ném exception, mặc định không có eviction sau lời gọi để đánh giá key. Nếu kết quả có thể null hoặc kiểu wrapper khác, phải xử lý và kiểm tra biểu thức phù hợp.

### 8.3. Xóa toàn cache với `allEntries=true`

~~~java
@CacheEvict(
    cacheNames = "productCatalog",
    allEntries = true,
    beforeInvocation = true
)
public void refreshCatalog() {
    catalogGateway.refresh();
}
~~~

Ở đây, mục tiêu là loại bỏ **mọi entry** trong cache `productCatalog` trước khi refresh. Khi refresh ném exception, thao tác làm rỗng đã được yêu cầu. Tuy nhiên, nếu các request khác truy cập trong lúc refresh, chúng vẫn có thể nạp dữ liệu cũ trở lại.

**Không kết hợp `allEntries=true` với biểu thức `key`**: xóa toàn vùng không có ý nghĩa chọn một key. Cũng phải đánh giá cẩn thận hậu quả xóa toàn bộ cache khi chỉ một record thay đổi, nhất là các hệ thống tải cao.

## 9. Transaction: “method thành công” và “commit thành công” khác nhau

Chọn `beforeInvocation` là quyết định quan trọng, nhưng **không tự bảo đảm đồng bộ cache với transaction**.

Xét luồng:

~~~text
@Transactional update
    ├─ sửa dữ liệu trong database transaction
    ├─ method có thể return bình thường
    ├─ transaction interceptor thực hiện commit hoặc rollback
    └─ caching interceptor evict theo thứ tự advice thực tế
~~~

Thứ tự thực sự giữa caching advice và transaction advice phụ thuộc cấu hình và thứ tự interceptor. Hơn nữa, với một `CacheManager` hỗ trợ transaction-aware hoặc wrapper phù hợp, thay đổi cache có thể được trì hoãn. Vì vậy:

- `beforeInvocation=false` chỉ bảo đảm eviction được lên lịch/thực hiện **sau khi phương thức do cache interceptor gọi hoàn tất thành công**, theo semantics của Spring Cache. Nó **không phải cam kết chung** rằng mọi eviction đã chờ database commit.
- Nếu transaction sau đó rollback nhưng cache đã bị evict, dữ liệu cache có thể được tải lại dù nguồn không đổi. Điều này thường chỉ làm mất hiệu năng; tuy nhiên tính đúng và concurrency vẫn cần được đánh giá.
- Nếu database đã thay đổi một phần rồi lỗi từ external system khiến method ném exception, `beforeInvocation=false` có thể giữ entry cũ không còn đúng.
- Với yêu cầu nghiêm ngặt “chỉ invalidate sau commit thành công”, hãy thiết kế cơ chế **after-commit** rõ ràng, transaction synchronization/event hoặc cache manager transaction-aware phù hợp; kiểm thử thứ tự và hành vi rollback trong project thật.

Đặc biệt, dùng `beforeInvocation=true` trên phương thức **còn đang chuẩn bị bắt đầu transaction** có thể tạo khoảng trống cache trước khi dữ liệu mới commit. Độc giả khác đọc trong khoảng này có thể nạp lại bản cũ. Khi cần tính nhất quán cao, cơ chế phiên bản, khóa theo key, invalidation sau commit, event/outbox hoặc phối hợp transaction/cache khác có thể phù hợp hơn.

## 10. Các trường hợp khiến khẳng định “xóa trước/sau” không diễn ra như kỳ vọng

### Proxy và self-invocation

Ở chế độ Spring proxy mặc định, annotation chỉ có tác dụng khi lời gọi **đi qua Spring proxy**. Ví dụ:

~~~java
@Service
class ProductService {
    public void caller(long id) {
        evictProduct(id); // lời gọi cùng instance: có thể bypass proxy
    }

    @CacheEvict(cacheNames = "products",
                key = "#p0",
                beforeInvocation = true)
    public void evictProduct(long id) {
        // Một thao tác nghiệp vụ.
    }
}
~~~

`caller` gọi trực tiếp `evictProduct` trên chính object; việc proxy advice bị bỏ qua không có nghĩa chọn sai `beforeInvocation`. Cần gọi qua bean đã được Spring intercept hoặc thiết kế lại ranh giới phương thức. AspectJ mode có đặc tính khác; nội dung trên áp dụng **proxy mode phổ biến**.

### Cache provider gặp lỗi

- Nếu eviction-before ném exception từ key resolution/cache provider **trước khi vào method**, lời gọi nghiệp vụ có thể chưa được thực hiện.
- Nếu method đã thành công nhưng eviction-after gặp lỗi, caller có thể quan sát lỗi cache sau khi dữ liệu nguồn đã được thay đổi; không tự suy luận rằng transaction hoặc database đã rollback.
- Một provider hoặc cache phân tán có cơ chế replication, transaction-awareness, eventual consistency khác nhau. `@CacheEvict` mô tả yêu cầu gửi tới cache abstraction; cần kiểm thử thời điểm entry thực sự không còn khả dụng.

### Nhiều cache, nhiều service, HTTP cache

`@CacheEvict(cacheNames="products")` chỉ tác động vào cache mà cache manager/resolver lựa chọn, không tự xóa browser HTTP cache, CDN, cache in-memory của mọi JVM khác hoặc entry trong region khác. Ngay cả eviction-before thành công, một caller khác có thể nạp lại bản cũ trong lúc cập nhật.

### Phương thức bất đồng bộ

Trong Spring Framework 6.1+, cache annotations có hỗ trợ đặc biệt cho `CompletableFuture` và các kiểu trả về reactive được hỗ trợ. Với eviction sau lời gọi, thời điểm xử lý có thể phụ thuộc quá trình hoàn thành bất đồng bộ, thay vì đơn giản là lúc method trả về một handle. Cần xác minh cụ thể cách xử lý **exceptional completion** cho phiên bản và cache provider đang dùng; đừng áp dụng máy móc thứ tự trong ví dụ đồng bộ vào reactive pipeline.

## 11. Chọn cấu hình nào theo mục tiêu nghiệp vụ?

| Tình huống | Cấu hình thường phù hợp | Lý do và giới hạn |
|---|---|---|
| Sửa entity trong transaction, lỗi bảo đảm rollback toàn bộ | Mặc định `beforeInvocation=false` | Nếu update thất bại mà nguồn giữ nguyên, cache cũ vẫn dùng được; vẫn kiểm tra timing commit |
| Thao tác đồng bộ ngoài DB có thể tạo side effect một phần trước khi báo lỗi | Cân nhắc `beforeInvocation=true` hoặc invalidation rõ ràng | Tránh giữ bản cũ có nguy cơ sai; vẫn phải xử lý race/refill |
| Xóa resource, chỉ muốn xóa cache khi xóa ở nguồn thành công | Mặc định `false` | Hạn chế cache miss do xóa không thành công |
| Muốn xóa cache dù method fail vì cache đã không còn tin cậy | `true` khi chính sách cho phép | Eviction xảy ra trước; gây miss ngay cả khi method chưa thay đổi nguồn |
| Method nuốt exception và trả trạng thái thất bại | Thiết kế lại result/error handling và logic cache | Spring nhìn thấy return bình thường nên sau lời gọi vẫn có thể evict |
| Cần invalidate đúng lúc database commit | After-commit/invalidation theo transaction rõ ràng | `beforeInvocation=false` một mình không bảo đảm đúng thời điểm commit |
| Chỉ muốn xóa một sản phẩm, không phải toàn danh mục | `key` đúng, `allEntries=false` | Tránh tác động không cần thiết tới các entry khác |

**Câu hỏi quyết định:** “Nếu thao tác này thất bại, dữ liệu cũ trong cache còn đáng tin không?” Nếu **còn đúng** và không có side effect, xóa sau khi method thành công thường hợp lý. Nếu **không chắc đúng** ngay cả khi thất bại, cần kế hoạch invalidation sớm/hậu kiểm theo nghiệp vụ, kết hợp chiến lược đảm bảo nhất quán để ngăn tái nạp bản cũ.

## 12. Kiểm thử @CacheEvict khi có ngoại lệ

Để xác nhận hành vi **Spring thật** (khác ví dụ Java mô phỏng), hãy dùng test nạp Spring application context, bật caching, lấy service bean qua context và dùng một cache manager có thể kiểm tra entry.

Chuỗi kiểm thử gợi ý:

1. Nạp `products[7] = "old"`.
2. Với `beforeInvocation=false`, cho repository ném `IllegalStateException` ra khỏi method. Xác nhận caller nhận lỗi, đồng thời `products[7]` vẫn còn.
3. Reset cache về `"old"`. Với `beforeInvocation=true`, cho method ném lỗi. Xác nhận caller vẫn nhận lỗi nhưng entry đã bị xóa.
4. Chạy cả hai phương thức thành công, xác nhận entry bị xóa sau/before tương ứng; dùng spy/mock cache nếu muốn kiểm tra **thứ tự**.
5. Kiểm tra trường hợp method **bắt ngoại lệ và return false**: mặc định vẫn eviction vì invocation trả về bình thường.
6. Bổ sung `condition=false`, trường hợp key sai, `allEntries` và self-invocation để phân biệt lỗi cấu hình với timing.
7. Nếu dùng `@Transactional`, kiểm tra cả commit và rollback; nếu dùng nhiều instance hoặc async, kiểm tra provider và concurrency thực tế.

Ví dụ assertion chỉ kiểm tra key đã mất sau khi method xong **không đủ chứng minh before/after** trong trường hợp cả hai đều thành công. Muốn chứng minh timing, hãy quan sát ngay trong method hoặc ghi nhận thứ tự invocation/`Cache.evict` qua spy. Đối với ngoại lệ, sự khác biệt còn/thất lạc key sau lời gọi là bằng chứng dễ quan sát nhất khi điều kiện thử nghiệm được kiểm soát.

## 13. Lỗi thường gặp

- **Cho rằng `@CacheEvict` luôn xóa, kể cả method throw exception:** mặc định là **không**, vì `beforeInvocation=false`.
- **Cho rằng `beforeInvocation=true` đợi tới sau khi method lỗi mới xóa:** thực tế việc xóa đã diễn ra **trước khi method bắt đầu**.
- **Xem kết quả trả về `false` là exception:** Spring vẫn xem invocation là thành công nếu method trả bình thường.
- **Nhầm `condition` với việc bỏ qua phương thức:** nó chỉ điều khiển eviction, không ngăn phương thức chạy.
- **Nhầm `#result` có thể dùng khi xóa trước:** trước method chưa có kết quả; hãy dùng tham số hoặc key ổn định từ request.
- **Quên key/cache name:** eviction thành công trên key khác key đọc không giúp loại bỏ dữ liệu stale.
- **Dùng `allEntries=true` không cân nhắc hậu quả:** lỗi một tác vụ có thể làm mất toàn bộ cache nếu eviction-before.
- **Giả định cache và transaction tự đồng bộ:** phải kiểm tra advice order, commit, rollback và khả năng trì hoãn của provider.
- **Dùng eviction-before như giải pháp duy nhất cho race:** concurrent read có thể nạp lại bản cũ giữa lần xóa và lần cập nhật.
- **Tự gọi method trong cùng bean:** ở proxy mode, annotation có thể không được áp dụng.
- **Bỏ qua lỗi cache provider:** exception trong thao tác eviction và exception từ logic nghiệp vụ là **hai nguồn lỗi khác nhau**, có hậu quả và timing khác nhau.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `@CacheEvict(cacheNames="products", key="#p0")` nằm trên `void rename(long id)`. Method ném `IllegalStateException` ra ngoài. Nếu key đã tồn tại, eviction mặc định có chạy sau method không?

**Câu 2.** Đổi sang `beforeInvocation=true`, method vẫn ném exception. Có thể khẳng định entry đã được yêu cầu xóa trước khi method chạy trong điều kiện proxy/provider hoạt động đúng không?

**Câu 3.** Method bắt ngoại lệ database rồi trả `false`. Với eviction mặc định và không có `condition`, cache có bị xóa không?

**Câu 4.** `beforeInvocation=true` kết hợp `condition="#p0 > 0"`, gọi với id bằng `-1`. Cache có bị xóa không? Method có bị bỏ qua không?

**Câu 5.** Vì sao `beforeInvocation=false` không có nghĩa chắc chắn “database đã commit xong rồi mới xóa”?

**Câu 6.** Một request đã xóa cache trước, request thứ hai đọc DB khi transaction cập nhật chưa commit và nạp lại bản cũ. `beforeInvocation=true` có ngăn được hiện tượng này không?

**Đáp án giải thích:**

1. **Không.** Method ném lỗi ra caching interceptor thì eviction sau invocation không diễn ra.
2. **Có, theo semantics của annotation**, nếu điều kiện và cache operation được thực hiện thành công; exception sau đó không phục hồi entry.
3. **Có thể có**: method trả bình thường (dù `false`), nên advice có thể thực hiện eviction sau invocation.
4. `condition` là false nên **không evict**. Phương thức vẫn chạy theo logic Java thông thường.
5. Vì còn thứ tự caching/transaction advice, thời điểm commit/rollback và transaction-aware cache behavior.
6. **Không.** Một eviction sớm không chặn concurrent refill; cần cách phối hợp chặt hơn nếu tính nhất quán yêu cầu.

## 15. Tài liệu tham khảo

- Spring Framework Reference — Annotation-based Caching, `@CacheEvict` và `beforeInvocation`: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Javadoc — `CacheEvict.beforeInvocation`, `condition`, `allEntries`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CacheEvict.html
- Spring Framework Reference — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html

**Ghi nhớ:** Với `@CacheEvict`, **mặc định chỉ xóa cache sau khi phương thức hoàn tất không ném exception**. `beforeInvocation=true` xóa **trước** nên method có lỗi sau đó vẫn không tự khôi phục entry. Để chọn đúng, phải xét tính nguyên tử của cập nhật, việc exception có thoát khỏi method hay bị bắt, transaction commit, key/cache name và khả năng đọc–ghi đồng thời.