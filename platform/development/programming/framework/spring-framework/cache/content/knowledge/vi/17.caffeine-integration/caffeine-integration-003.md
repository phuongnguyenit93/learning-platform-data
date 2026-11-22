# Giới hạn kích thước hoặc trọng lượng dữ liệu với Caffeine trong Spring Cache

> **Chủ đề:** Spring Framework – Cache · **Nhóm:** Tích hợp Caffeine.  
> **Bài toán:** Không thể để cache trong JVM tăng vô hạn. Khi các entry có kích thước gần giống nhau, nên giới hạn **số lượng entry** bằng `maximumSize`. Khi các entry tiêu thụ tài nguyên rất khác nhau, có thể giới hạn **tổng trọng lượng ước lượng** bằng `maximumWeight` kết hợp `weigher`. Bài này giải thích cơ chế, cấu hình chính xác cho Spring Cache, các giới hạn về bộ nhớ và ví dụ Java 17+ tự chạy.

## 1. Vì sao phải giới hạn cache Caffeine?

`@Cacheable` giúp tránh thực thi lại một method đắt đỏ khi có cache hit, nhưng cache giữ các object trong JVM. Nếu dữ liệu hoặc số lượng key tăng liên tục, ứng dụng có thể gặp các vấn đề:

- **Heap bị chiếm quá mức:** bản ghi truy vấn, JSON payload, hình ảnh nhỏ, collection và object graph giữ tham chiếu đến nhiều vùng bộ nhớ.
- **GC tăng áp lực:** nhiều object sống lâu qua các lần garbage collection, gây tăng CPU và độ trễ.
- **Cardinality không kiểm soát:** mỗi tham số filter/tenant/page tạo một cache key mới, khiến số entry tăng mạnh.
- **Dữ liệu kích thước không đồng nhất:** 1.000 bản ghi vài trăm byte khác xa 1.000 đồ thị có hàng triệu node.
- **Cold miss và cache churn:** đặt giới hạn quá thấp làm các key liên tục bị evict rồi lại nạp từ database, có thể gây quá tải nguồn.
- **Khác biệt giữa các instance:** nếu chạy nhiều pod với local Caffeine cache, mỗi pod có **ngân sách riêng**, không phải một ngân sách chung toàn cluster.

Spring Cache abstraction **không có thuộc tính annotation `@Cacheable(maximumSize=...)`**. Giới hạn kích thước hoặc trọng lượng được cấu hình ở **Caffeine provider / `CaffeineCacheManager`**, không nằm trong annotation caching của Spring.

Hai lựa chọn cơ bản:

```java
// A. Giới hạn số entry.
Caffeine.newBuilder().maximumSize(10_000);

// B. Giới hạn tổng trọng lượng ước lượng.
Caffeine.newBuilder()
        .maximumWeight(100_000)
        .weigher((Object key, Object value) -> estimateWeight(value));
```

Đây là snippet minh họa; `estimateWeight` là hàm nghiệp vụ phải được định nghĩa. **Không** khai báo đồng thời `maximumSize` và `maximumWeight` trên một builder. Mỗi phương án là một chính sách capacity riêng.

## 2. `maximumSize`: giới hạn theo số entry

### 2.1. Cách hiểu

`maximumSize(long maximum)` yêu cầu Caffeine giữ số lượng entry trong khoảng giới hạn đã cấu hình. Khi cache cần chỗ cho giá trị mới hoặc phải xử lý maintenance, Caffeine có thể evict những entry không được truy cập gần đây hoặc không được sử dụng thường xuyên.

Ví dụ:

```java
com.github.benmanes.caffeine.cache.Cache<String, String> catalog =
        Caffeine.newBuilder()
                .maximumSize(500)
                .build();
```

Đoạn trên cần import `com.github.benmanes.caffeine.cache.Caffeine`, nằm trong một class/method Java hợp lệ. Đây là **Caffeine native API**, chưa dùng Spring annotation.

Ở mức khái niệm, cache chỉ cố giữ khoảng 500 key; một entry chứa chuỗi dài 20 byte và một entry chứa object graph 20 MB **đều được tính là một entry**. Vì vậy `maximumSize` rất dễ cấu hình nhưng không đại diện trực tiếp cho mức sử dụng heap.

### 2.2. Điều nó không bảo đảm

- **Không phải giới hạn byte.** `maximumSize(500)` không đồng nghĩa với 500 KB hoặc 500 MB.
- **Không bảo đảm key cũ nhất bị xóa.** Caffeine có chính sách admission/eviction ưu tiên kết hợp tần suất và tính gần đây; không phải FIFO đơn giản.
- **Không phải giới hạn tuyệt đối tức thời ở mọi dòng lệnh.** Việc xử lý eviction/maintenance có thể được gom lại; kết quả `estimatedSize()` là ước lượng và có thể tạm thời chưa phản ánh toàn bộ việc dọn dẹp. Khi viết test, có thể gọi `cleanUp()` rồi quan sát thay vì chỉ kiểm tra ngay sau `put`.
- **Không kiểm soát bộ nhớ bên ngoài entry.** Heap còn chứa threads, buffers, framework, objects giữ bởi nơi khác, query results trong lúc load và overhead của chính cache.
- **Không phải TTL.** Entry có thể bị loại vì áp lực capacity dù chưa hết hạn; ngược lại nếu ít key và ít thay đổi, có thể còn đó rất lâu khi không có expire policy.

### 2.3. Khi nào `maximumSize` phù hợp?

- Các record có kích thước tương đối đồng đều: ví dụ profile nhỏ, số liệu tổng hợp đơn giản, metadata ngắn.
- Mục tiêu chính là tránh cardinality vô hạn, không cần mô hình chi phí từng entry.
- Ưu tiên cấu hình đơn giản, dễ quan sát hit rate và dễ điều chỉnh khi tải thay đổi.
- Chưa có cách đo trọng lượng đáng tin của value: **một giới hạn theo entry còn tốt hơn một bộ cân trọng lượng sai**.

Ví dụ có cả time-based expiration:

```java
Caffeine.newBuilder()
        .maximumSize(5_000)
        .expireAfterWrite(java.time.Duration.ofMinutes(10))
        .recordStats();
```

`maximumSize` bảo vệ capacity; `expireAfterWrite` ràng buộc tuổi entry; `recordStats` bật số liệu. Đây là **ba vai trò độc lập** và có thể được dùng chung.

## 3. `maximumWeight` và `weigher`: giới hạn theo trọng lượng ước lượng

### 3.1. Cách hoạt động

Khi các value chênh lệch lớn về kích thước, có thể cung cấp một **`Weigher<K,V>`** để xác định chi phí của từng entry, rồi đặt **`maximumWeight(long)`** làm tổng ngân sách.

Ví dụ native Caffeine với payload byte array:

```java
com.github.benmanes.caffeine.cache.Cache<String, byte[]> payloads =
        Caffeine.newBuilder()
                .maximumWeight(4L * 1024 * 1024)
                .weigher((String key, byte[] bytes) -> bytes.length)
                .build();
```

Đây là snippet yêu cầu import `Caffeine` và đặt trong class/method thích hợp. Quy ước trên tính **số byte trong payload array**, giới hạn tổng payload khoảng 4 MiB. Nhưng đây **không phải tổng heap thật** vì chưa tính key, headers, map nodes, Java object overhead, alignment, metadata và các tham chiếu khác.

Nếu object là đồ thị hoặc nhiều string, phải định nghĩa `weigher` dựa trên logic nghiệp vụ, ví dụ số node, số record, số bytes đã serialize, hoặc một đơn vị tài nguyên nhất quán.

### 3.2. Kiểu dữ liệu và quy tắc của `Weigher`

- Hàm nhận **key và value**, trả về số nguyên `int` **không âm**.
- Trọng lượng **có thể bằng 0**, nhưng nhiều entry trọng lượng 0 có thể gây hiểu sai ngân sách vì chúng không tiêu thụ quota trọng lượng.
- Không dùng giá trị âm: Caffeine không chấp nhận trọng lượng âm.
- `maximumWeight` là `long`, nhưng kết quả của từng lần `weigh` là `int`; với dữ liệu rất lớn hoặc đơn vị bytes, cần tránh phép tính tràn `int`.
- Hàm nên **nhanh, xác định, không có side effect, không gọi IO**. Caffeine phải tính weight khi entry được tạo/cập nhật; một `weigher` chậm làm đường ghi cache chậm.
- Nếu value có thể là `null` theo đường Spring Cache, cần xem chính sách `allowNullValues` và khả năng Caffeine wrapper sử dụng sentinel. Không ép cast thẳng tất cả value về kiểu nghiệp vụ khi chưa kiểm soát cấu hình.

### 3.3. Trọng lượng được tính lúc tạo hoặc cập nhật entry

Một điểm rất dễ bỏ sót: **trọng lượng được tính tại thời điểm entry được thêm/cập nhật và giữ nguyên cho tới lần cập nhật tiếp theo**. Caffeine không tự định kỳ đi đo lại những object đang nằm trong cache.

Ví dụ:

```java
java.util.List<String> items = new java.util.ArrayList<>();
items.add("A");
cache.put("products", items);   // weigher thấy size = 1
items.add("B");                 // object bị sửa nhưng không có put lại
```

Nếu `weigher` tính `value.size()`, hệ thống vẫn đang giữ trọng lượng được tính khi `put`; giá trị object có thể đã tăng kích thước thật. Đây là lý do ưu tiên các DTO **bất biến** hoặc chụp snapshot trước khi cache. Với trường hợp cần cập nhật value, đặt lại entry bằng value mới để Caffeine tính weight mới.

**Cũng cần phân biệt chi phí với chính sách chọn nạn nhân:** Caffeine sử dụng weight để quyết định tổng ngân sách, nhưng **tỷ lệ weight tương đối của từng entry không trực tiếp quyết định thứ tự ưu tiên eviction**. Không nên suy rằng entry nặng nhất luôn bị đuổi trước.

### 3.4. Entry có trọng lượng vượt ngân sách

Một value được weigher trả về trọng lượng lớn hơn `maximumWeight` không thể được giữ ổn định trong cache này. Khi `@Cacheable` gọi loader, method vẫn có thể trả value cho caller, nhưng value quá nặng có thể **không được lưu lại**; lần gọi sau cùng key lại miss và gọi loader.

Đây thường là một tín hiệu thiết kế: nếu phần lớn hot value đều lớn hơn quota, tăng ngân sách hoặc tách cache theo loại value. Đừng liên tục gọi backend để tính một object đắt đỏ nhưng không thể giữ trong cache.

### 3.5. “Weight” không mặc định là bytes hay MB

Một số chiến lược cân trọng lượng:

| Loại value | Weight gợi ý | Giới hạn của phép đo |
|---|---|---|
| `byte[]` | `bytes.length` | Chưa tính header, key và overhead |
| `String` | `string.length()` | Đếm UTF-16 code units, **không phải bytes hay heap size** |
| `List<Product>` | `list.size()` | Chỉ là số record, không phản ánh object khác kích thước |
| Đồ thị | Số vertices/edges | Tốt cho chi phí thuật toán, không phải heap thực |
| JSON đã serialize | Số bytes đầu ra serialization | Có chi phí serialize và thường chưa tính object graph |
| DTO lớn | Trọng lượng quy đổi theo nhóm hoặc buckets | Tương đối, phải hiệu chỉnh bằng đo đạc |
| Dữ liệu chia sẻ nhiều reference | Kích thước payload logic | Có thể đếm trùng bộ nhớ dùng chung |

**Tên đơn vị phải rõ ràng.** `maximumWeight(100_000)` với weigher đếm **record** không được giới thiệu là 100 KB. Một nhóm dùng units KiB thì cả capacity và weight đều phải theo KiB.

## 4. `maximumSize` và `maximumWeight` không được dùng cùng một cache

| Thuộc tính | `maximumSize` | `maximumWeight` + `weigher` |
|---|---|---|
| Đơn vị quota | Số entry | Tổng các trọng lượng do ứng dụng định nghĩa |
| Khi các value đồng đều | Dễ áp dụng | Có thể dư công sức |
| Khi value chênh lệch lớn | Không kiểm soát chặt tổng payload | Phù hợp hơn nếu weight hợp lý |
| Cần custom code | Không | Có: `Weigher` |
| Có thể mô tả bằng spec string đơn giản | Có | `maximumWeight` cần `weigher` thực; spec string không định nghĩa được logic Java custom |
| Chi phí tính quota | Thấp | Phụ thuộc chi phí của `weigher` |
| Nguy cơ do value mutable | Vẫn có rủi ro value thay đổi | **Đặc biệt nghiêm trọng** vì weight không tự được tính lại |
| Giới hạn heap tuyệt đối | Không | Cũng không |
| Thứ tự evict | Chính sách Caffeine | Chính sách Caffeine, weight không phải “ưu tiên xóa” |
| Dùng với TTL | Có | Có |

**Không hợp lệ trên một builder:**

```java
Caffeine.newBuilder()
        .maximumSize(1000)
        .maximumWeight(10_000)
        .weigher((Object key, Object value) -> 1);
```

Đây là cấu hình **chỉ để minh họa lỗi**, không đưa vào project chạy. Caffeine buộc chọn **một** giới hạn capacity chính: số lượng hoặc trọng lượng. Không có thuộc tính mặc định nào đảm bảo “tối đa 1.000 entry **và** tối đa 10 MB” trên cùng một instance bằng cách gọi cả hai builder methods.

Nếu cần hai ràng buộc độc lập cùng lúc, có thể đặt layer quota tại ứng dụng, chia thành nhiều cache theo loại dữ liệu hoặc tự thiết kế admission policy kết hợp, nhưng phải đo và kiểm tra concurrency. Đừng dựa vào API mà builder không hỗ trợ.

### 4.1. Điều gì xảy ra khi eviction được kích hoạt?

Caffeine không đơn giản xóa entry vừa cũ nhất hay entry lớn nhất. Chính sách eviction có xét gần đây/tần suất truy cập nhằm bảo vệ các giá trị được dùng thường xuyên; tài liệu Caffeine mô tả hành vi tương tự W-TinyLFU.

Ví dụ cache có quota 3 entry, mỗi phút nhận 100 truy cập key A, 50 truy cập B, và chỉ một lần với các key C, D, E. Thường hợp lý nếu A/B được ưu tiên giữ lại, nhưng **không hứa chính xác nạn nhân eviction cho mọi chuỗi thao tác**. Chính sách có thể ảnh hưởng bởi sample, maintenance, history và concurrency.

Vì vậy, kiểm thử nghiệp vụ nên xác nhận **ngân sách sau maintenance**, hit rate và loader count, thay vì viết test cứng kiểu “sau khi thêm D thì key C chắc chắn phải bị xóa” trong một policy adaptive.

## 5. Cấu hình Caffeine native trước khi tích hợp Spring

### 5.1. Dùng số entry

```java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Duration;

Cache<String, String> cache = Caffeine.newBuilder()
        .maximumSize(10_000)
        .expireAfterWrite(Duration.ofMinutes(15))
        .recordStats()
        .build();
```

Đây là đoạn khai báo trong scope Java có thể dùng local variables, không phải một source file standalone. Với giới hạn 10.000 entry, budget theo **số mapping**, không đo bytes.

### 5.2. Dùng trọng lượng tính theo bytes

```java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;

Cache<String, byte[]> bytesCache = Caffeine.newBuilder()
        .maximumWeight(64L * 1024 * 1024)
        .weigher((String key, byte[] value) -> value.length)
        .recordStats()
        .build();
```

Nếu một value chứa 50 MB payload và cache có ngân sách 64 MB, phần quota còn lại ít; eviction có thể diễn ra tùy số entry khác. Trường hợp value > 64 MB thường không được giữ lại. Đây là budget logic của **payload bytes**, không phải giới hạn RSS hay heap chính xác.

### 5.3. Weigher quy đổi theo KiB để tránh tràn `int`

Trong một hệ thống có payload có thể rất lớn, `int` weight tính theo bytes có nguy cơ tràn khi kết hợp nhiều phép tính. Có thể chọn đơn vị KiB:

```java
static int kibWeight(byte[] bytes) {
    long kib = (bytes.length + 1023L) / 1024L;
    return (int) Math.max(1L, Math.min(kib, Integer.MAX_VALUE));
}
```

Đây là hàm Java độc lập về mặt cú pháp nếu đặt trong class. Đơn vị KiB theo phép làm tròn lên; payload rất nhỏ vẫn chiếm tối thiểu một đơn vị. Ví dụ 1 byte → 1 KiB, 1.025 bytes → 2 KiB. Khi dùng hàm này, quota phải cũng tính bằng **KiB**: `maximumWeight(64L * 1024)` có nghĩa khoảng 64 MiB payload quy đổi, không phải 64 KiB hay 64 bytes.

### 5.4. Không dùng weigher nặng

Tránh:

```java
.weigher((key, value) -> {
    // Anti-pattern: serialize lại object và gọi dịch vụ ngoài
    // mỗi khi entry được thêm/cập nhật.
    return remoteSizingService.estimateBytes(value);
})
```

Hàm trên là **minh họa anti-pattern** vì `remoteSizingService` là dependency tưởng tượng, không phải code chạy độc lập. Weigher có IO mạng hoặc serialization lớn có thể làm chậm đường nạp cache. Nếu cần kích thước serialized thật, tốt hơn tạo metadata khi tạo value rồi cân bằng một phép đọc field ổn định.

## 6. Tích hợp vào Spring Framework qua `CaffeineCacheManager`

### 6.1. Dùng một builder làm chính sách chung

Khi Spring Cache dùng Caffeine, Spring Framework cung cấp `org.springframework.cache.caffeine.CaffeineCacheManager` trong module **`spring-context-support`**.

```java
@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {

    @Bean
    public CacheManager cacheManager() {
        CaffeineCacheManager manager =
                new CaffeineCacheManager("products", "categories");

        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(5_000)
                .expireAfterWrite(Duration.ofMinutes(10))
                .recordStats());

        return manager;
    }
}
```

Đoạn trên cần import `CacheManager`, `CaffeineCacheManager`, `Caffeine`, `Duration`, `@Configuration`, `@EnableCaching` và `@Bean`; ví dụ chạy độc lập ở mục 8.

Một điểm quan trọng: builder được truyền qua `setCaffeine` là **cấu hình chung cho các cache do manager tạo**. Mỗi vùng `products` và `categories` có ngân sách `maximumSize(5000)` riêng, không phải cả hai dùng chung quota 5.000 entry.

`@Cacheable` trên service giữ nguyên:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product load(String productId) {
    return repository.find(productId);
}
```

Service snippet này cần repository thực; method chỉ chọn vùng cache. **Không đặt `maximumSize` trong annotation** vì kích thước được quyết định bởi manager/provider.

### 6.2. Chính sách khác nhau cho từng vùng bằng `registerCustomCache`

Nếu `products` chỉ gồm vài nghìn record nhỏ còn `largeDocuments` có byte arrays rất lớn, một builder cho mọi cache có thể không hợp lý.

`CaffeineCacheManager.registerCustomCache(name, nativeCache)` cho phép đưa một native Caffeine cache được cấu hình riêng vào manager:

```java
CaffeineCacheManager manager = new CaffeineCacheManager("products");
manager.setCaffeine(Caffeine.newBuilder().maximumSize(5_000));

com.github.benmanes.caffeine.cache.Cache<Object, Object> documents =
        Caffeine.newBuilder()
                .maximumWeight(64L * 1024 * 1024)
                .weigher((Object key, Object value) ->
                        ((byte[]) value).length)
                .build();

manager.setAllowNullValues(false);
manager.registerCustomCache("largeDocuments", documents);
```

Đoạn này là Java snippet trong scope đã có imports; chỉ an toàn nếu các value thuộc vùng `largeDocuments` thật sự là `byte[]` không null. Cấu hình `setAllowNullValues(false)` giúp tránh wrapper sentinel cho null ở manager. Nếu method trả về type khác, cast trong `weigher` có thể gây `ClassCastException`.

Kết quả:

- `products`: quota theo **số entry**.
- `largeDocuments`: quota theo **tổng độ dài byte[]**.
- Hai cache có vòng đời và eviction độc lập.
- Quota không tự áp dụng cho các manager khác hoặc các pod khác.

### 6.3. Một manager cho nhiều cache names: tổng ngân sách không cộng gộp

Giả sử manager tạo:

```java
new CaffeineCacheManager("products", "categories", "users")
```

và dùng `maximumSize(5000)`. Đây không có nghĩa toàn JVM chỉ giữ tối đa 5.000 entry; **mỗi Cache** có policy riêng. Về mặt số entry, tổng có thể gần 15.000 nếu cả ba vùng đều đầy, chưa kể cache khác và overhead.

Khi lập ngân sách heap, hãy tính:

```text
Tổng bộ nhớ cache xấp xỉ
    ≈ Σ (số entry vùng i × chi phí trung bình entry i)
      + overhead cache, keys, JVM, object graphs, buffers ...
```

Ngay cả với `maximumWeight`, tổng của các cache regions khác nhau và nhiều Spring contexts phải được cộng riêng khi lập capacity plan.

## 7. Spring Boot: cấu hình nhanh và giới hạn của `spring.cache.caffeine.spec`

Trong ứng dụng Spring Boot đã bật `@EnableCaching` và dùng `spring-boot-starter-cache` cùng thư viện Caffeine, Boot có thể tự cấu hình `CaffeineCacheManager` nếu không có bean manager/resolver thay thế theo điều kiện auto-configuration.

### 7.1. Giới hạn theo số entry bằng properties

**`application.properties`:**

```properties
spring.cache.type=caffeine
spring.cache.cache-names=products,categories
spring.cache.caffeine.spec=maximumSize=5000,expireAfterWrite=10m,recordStats
```

Ở đây mỗi vùng trong `cache-names` dùng policy đã chỉ định; `recordStats` bật thống kê native. Đây là cách gọn cho giới hạn **maximumSize** cùng TTL.

**Quan trọng:** `spring.cache.caffeine.spec` không tạo một object `Weigher` Java tùy biến từ chuỗi. Nếu cần weight phụ thuộc value, phải cấu hình **Caffeine builder bean hoặc CaffeineCacheManager bean trong Java** với `weigher`, rồi kiểm tra precedence của Boot.

Theo tài liệu Boot, khi Caffeine auto-config được dùng, cấu hình được xét theo thứ tự: `spring.cache.caffeine.spec`, bean `CaffeineSpec`, bean `Caffeine`. Vì vậy một property `spec` có thể được ưu tiên hơn bean builder bạn đã khai báo. Đừng để `maximumSize` trong properties vô tình ghi đè ý định áp dụng `maximumWeight` từ builder.

### 7.2. Dùng builder bean trong Boot

Ví dụ chỉ dùng builder khi không có cấu hình spec ưu tiên hơn:

```java
@Configuration(proxyBeanMethods = false)
class CaffeinePolicyConfig {

    @Bean
    Caffeine<Object, Object> caffeine() {
        return Caffeine.newBuilder()
                .maximumWeight(20_000)
                .weigher((Object key, Object value) ->
                        ((CachePayload) value).unitWeight())
                .recordStats();
    }
}
```

Đây là snippet minh họa trong project có class `CachePayload` thực, không phải source file chạy độc lập. Nếu manager cần chứa nhiều kiểu value, một cast cứng thành `CachePayload` sẽ không phù hợp; nên chia cache/manager theo type hoặc dùng quy tắc weight an toàn.

Nếu ứng dụng **tự đăng ký bean `CacheManager`**, Spring Boot có thể không tạo manager tự động và các property `spring.cache.*` không mặc nhiên tác động đến bean bạn dựng thủ công. Đọc điều kiện auto-config và xác minh bean type trong context thay vì giả định.

### 7.3. Cẩn thận với `maximumWeight` trong CaffeineSpec

Giá trị `maximumWeight=100000` một mình **không mô tả cách tính weight cho value**. Caffeine cần một `Weigher` hợp lệ; không có syntax spec đơn giản để biểu diễn logic Java tùy biến như `v -> v.getPayloadBytes()`.

Không cố gắng dùng:

```properties
# Không phải cấu hình đầy đủ cho custom weighted eviction:
spring.cache.caffeine.spec=maximumWeight=100000
```

Đoạn này dùng để chỉ ra thiếu sót, **không phải cấu hình được khuyên chạy**. Hãy khai báo builder với `weigher`, chọn rõ backend, và test việc manager thực sự dùng weighted policy.

## 8. Demo Java 17+ chạy độc lập: size cache và weighted cache trong một Spring application

Ví dụ cố định **Java 17+**, **Spring Framework 6.2.12**, **Caffeine 3.2.2** và Maven. Nó chứng minh:

1. `maximumSize(2)` giới hạn vùng `boundedItems` theo số entry, đồng thời `@Cacheable` hit khi gọi lại.
2. `maximumWeight(5)` với weigher tính `String.length()` giữ A có trọng lượng 2 và B có trọng lượng 3.
3. Một giá trị có weight 6 vượt ngân sách 5 **không được giữ lại**; method vẫn trả dữ liệu nhưng gọi lại phải load lại.
4. Dùng `registerCustomCache` áp dụng chính sách khác nhau cho hai vùng trong cùng manager.
5. Quan sát `estimatedSize()` và `policy().eviction().weightedSize()` mà không phụ thuộc việc Caffeine chọn chính xác key nào khi có áp lực eviction.

### 8.1. Cấu trúc thư mục

```text
spring-caffeine-capacity/
├── pom.xml
└── src/main/java/dev/example/capacity/CaffeineCapacityDemo.java
```

### 8.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>spring-caffeine-capacity</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context-support</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>caffeine</artifactId>
            <version>3.2.2</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>dev.example.capacity.CaffeineCapacityDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context-support` kéo theo các thành phần Spring Context cần cho annotation caching, đồng thời chứa Caffeine integration. Project này không dùng Boot, database hoặc Redis.

### 8.3. Java source hoàn chỉnh

**`src/main/java/dev/example/capacity/CaffeineCapacityDemo.java`**

```java
package dev.example.capacity;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCache;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CaffeineCapacityDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(CacheConfig.class)) {

            SampleService service = context.getBean(SampleService.class);
            CacheManager manager = context.getBean(CacheManager.class);

            Cache boundedSpring =
                    Objects.requireNonNull(manager.getCache("boundedItems"));
            Cache weightedSpring =
                    Objects.requireNonNull(manager.getCache("weightedItems"));

            com.github.benmanes.caffeine.cache.Cache<Object, Object> bounded =
                    ((CaffeineCache) boundedSpring).getNativeCache();
            com.github.benmanes.caffeine.cache.Cache<Object, Object> weighted =
                    ((CaffeineCache) weightedSpring).getNativeCache();

            // Mỗi @Cacheable lookup có key là String argument đầu tiên.
            System.out.println("boundedA1=" + service.loadBounded("A"));
            System.out.println("boundedA2=" + service.loadBounded("A"));
            System.out.println("boundedLoadsBeforePressure=" +
                    service.boundedLoadCount());

            // Có ba key nhưng quota giữ tối đa hai entry.
            System.out.println("boundedB=" + service.loadBounded("B"));
            System.out.println("boundedC=" + service.loadBounded("C"));
            bounded.cleanUp();
            System.out.println("boundedEntriesAfterCleanup=" +
                    bounded.estimatedSize());

            // Trong weightedItems: A = 2 ký tự, B = 3 ký tự.
            System.out.println("weightedA=" + service.loadWeighted("A"));
            System.out.println("weightedB=" + service.loadWeighted("B"));
            weighted.cleanUp();
            long knownWeight = weighted.policy().eviction()
                    .orElseThrow().weightedSize().orElseThrow();
            System.out.println("weightedKnownWeight=" + knownWeight);

            // H có weight = 6, lớn hơn maximumWeight(5).
            System.out.println("heavy1=" + service.loadWeighted("H"));
            System.out.println("heavy2=" + service.loadWeighted("H"));
            weighted.cleanUp();
            System.out.println("heavyCached=" +
                    (weighted.getIfPresent("H") != null));
            System.out.println("heavyLoads=" + service.heavyLoadCount());

            System.out.println("weightedMaximum=" +
                    weighted.policy().eviction().orElseThrow().getMaximum());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class CacheConfig {

        @Bean
        public CacheManager cacheManager() {
            CaffeineCacheManager manager =
                    new CaffeineCacheManager("boundedItems");

            manager.setAllowNullValues(false);
            manager.setCaffeine(Caffeine.newBuilder()
                    .maximumSize(2)
                    .recordStats());

            com.github.benmanes.caffeine.cache.Cache<Object, Object>
                    weighted = Caffeine.newBuilder()
                    .maximumWeight(5)
                    .weigher((Object key, Object value) ->
                            ((String) value).length())
                    .recordStats()
                    .build();

            manager.registerCustomCache("weightedItems", weighted);
            return manager;
        }

        @Bean
        public SampleService sampleService() {
            return new SampleService();
        }
    }

    public static class SampleService {
        private final AtomicInteger boundedLoads = new AtomicInteger();
        private final AtomicInteger heavyLoads = new AtomicInteger();

        @Cacheable(cacheNames = "boundedItems", key = "#p0")
        public String loadBounded(String key) {
            return "bounded-" + key + "#" + boundedLoads.incrementAndGet();
        }

        @Cacheable(cacheNames = "weightedItems", key = "#p0")
        public String loadWeighted(String key) {
            return switch (key) {
                case "A" -> "AA";
                case "B" -> "BBB";
                case "H" -> {
                    heavyLoads.incrementAndGet();
                    yield "XXXXXX";
                }
                default -> "Z";
            };
        }

        public int boundedLoadCount() {
            return boundedLoads.get();
        }

        public int heavyLoadCount() {
            return heavyLoads.get();
        }
    }
}
```

Trong thư mục `spring-caffeine-capacity`, chạy:

```bash
mvn -q compile exec:java
```

**Stdout từ `System.out.println`** với context và cache mới (không tính log phụ của Maven):

```text
boundedA1=bounded-A#1
boundedA2=bounded-A#1
boundedLoadsBeforePressure=1
boundedB=bounded-B#2
boundedC=bounded-C#3
boundedEntriesAfterCleanup=2
weightedA=AA
weightedB=BBB
weightedKnownWeight=5
heavy1=XXXXXX
heavy2=XXXXXX
heavyCached=false
heavyLoads=2
weightedMaximum=5
```

### 8.4. Điều gì được chứng minh?

**Nhánh `boundedItems`:**

- `A` gọi lần hai hit, nên `boundedLoadsBeforePressure=1`.
- `B` và `C` làm tổng key từng được đưa vào cache lên ba, vượt quota 2.
- Sau `cleanUp()`, cache có **hai mapping**. Bài test không đoán A/B/C key nào còn vì thứ tự eviction phụ thuộc policy.

**Nhánh `weightedItems`:**

- `A` có value `"AA"`, trọng lượng 2; `B` có `"BBB"`, trọng lượng 3. Tổng trong quota 5, vì thế `weightedKnownWeight=5`.
- `H` tạo value `"XXXXXX"` có trọng lượng 6, vượt quota 5, nên entry này không được retained. Caller vẫn nhận value, nhưng lần gọi tiếp theo lại chạy method; `heavyLoads=2` và `heavyCached=false`.
- `weightedMaximum=5` xác nhận native eviction policy đang dùng quota trọng lượng 5, chứ không phải size 5.
- Hai vùng cache có chính sách độc lập dù được quản lý bởi cùng một `CaffeineCacheManager`.

**Lưu ý:** Chỉ dùng `cleanUp()` để khiến maintenance chạy trong bài test hoặc công tác vận hành có chủ đích; không gọi `cleanUp()` sau mọi request production. `estimatedSize()` vẫn là giá trị gần đúng, và không nên dựa vào thứ tự nạn nhân eviction để viết business logic.

### 8.5. Tại sao không có `new SampleService()` trong `main`?

`@Cacheable` được Spring xử lý qua proxy khi `@EnableCaching` được bật. `context.getBean(SampleService.class)` trả đối tượng Spring-managed để method invocation đi qua interceptor. Nếu bạn viết `new SampleService().loadBounded("A")` ngoài context hoặc gọi `this.loadBounded(...)` từ cùng bean trong proxy mode, caching có thể bị bỏ qua.

### 8.6. Vì sao `setAllowNullValues(false)` xuất hiện?

Ví dụ dùng `weigher((Object key, Object value) -> ((String) value).length())`. Nếu cache cho phép Spring bọc null thành một sentinel, cast sang `String` không còn hợp lệ. Bật `setAllowNullValues(false)` và đảm bảo các method cacheable trả String khác null giúp kiểu dữ liệu của `weigher` nhất quán. Với hệ thống thật cần cân nhắc chính sách null riêng, hoặc dùng weigher có logic rõ ràng cho mỗi loại value.

## 9. Quan sát capacity, eviction và hit rate

Để tuning tốt cần đo chứ không chỉ chọn một con số đẹp trên properties.

### 9.1. Native Caffeine stats

Bật `recordStats()` cho native cache và quan sát:

```java
com.github.benmanes.caffeine.cache.Cache<Object, Object> nativeCache =
        ((CaffeineCache) springCache).getNativeCache();

nativeCache.cleanUp(); // Chỉ dùng trong test/đo có chủ đích.
System.out.println(nativeCache.estimatedSize());
System.out.println(nativeCache.stats().hitRate());
System.out.println(nativeCache.stats().evictionCount());
System.out.println(nativeCache.stats().evictionWeight());
```

Đoạn này là snippet có biến `springCache` kiểu Spring `Cache`; các method trả số liệu native Caffeine. `hitRate()` chỉ mang ý nghĩa sau khi có nhiều lần lookup và recordStats; với ít sample, metric dễ nhiễu.

**`evictionCount` không phải số lượng lần gọi `@CacheEvict`**, và `evictionWeight` không phải mức dùng hiện tại. Các metric eviction mô tả số lần/chi phí loại entry theo chính sách; phân biệt chúng với explicit invalidation/removal và TTL.

### 9.2. Đọc ngân sách thực từ policy

`Caffeine` cho phép quan sát optional eviction policy:

```java
var policy = nativeCache.policy().eviction().orElseThrow();

long configuredMaximum = policy.getMaximum();
java.util.OptionalLong currentWeightedSize = policy.weightedSize();
```

- `getMaximum()` là quota hiện tại của policy, theo **entry count** nếu size-based hoặc theo **weight units** nếu weighted.
- `weightedSize()` chỉ có ý nghĩa khi policy là weighted; đối với cache `maximumSize`, thông tin weighted-size có thể không có.
- `estimatedSize()` là số mapping, không phải weight và không phải byte count.
- Với cache có nhiều vùng, lấy native cache riêng từng `cacheName`.

Hãy báo cáo **đơn vị** cùng mọi biểu đồ: `maximumWeight=50_000 records` khác hoàn toàn `maximumWeight=50_000 KiB`.

### 9.3. Metrics ứng dụng cần theo dõi

| Chỉ số | Vì sao hữu ích? |
|---|---|
| Cache hit rate / miss rate | Đo hiệu quả cache và tình trạng churn |
| Eviction count theo cause/policy | Phát hiện ngân sách quá nhỏ hoặc key cardinality tăng |
| Estimated entry count | Xem số key thực được giữ |
| Current weighted size nếu có | So sánh với budget trọng lượng đã định nghĩa |
| Load time và loader calls | Đo ảnh hưởng của miss lên database/API |
| GC pause/heap used/old-gen | Kiểm chứng giới hạn cache có giúp ổn định bộ nhớ không |
| Latency P95/P99 của method cacheable | Tìm ra hệ quả của eviction và stampede |
| Key cardinality theo tenant/query group | Phát hiện key vô hạn hoặc bị bỏ quên |
| Số instance/pod và mức dùng heap mỗi pod | Local cache nhân bản chi phí theo quy mô cluster |

Khi dùng Spring Boot Actuator + Micrometer với cấu hình phù hợp, có thể thu metrics cho cache, nhưng **không hứa tất cả metric weightedSize đều tự có**. Native policy introspection hoặc metric tùy chỉnh có thể cần thiết.

## 10. Chọn ngân sách và đánh đổi hiệu năng

### 10.1. Từ heap budget đến `maximumSize`

Một cách lập kế hoạch ban đầu:

1. Xác định giới hạn heap JVM, ví dụ `-Xmx`, và phần bộ nhớ cần dành cho phần còn lại của ứng dụng.
2. Đo chi phí trung bình của một entry **đang giữ** bằng profiler/heap dump/benchmark tương đối chính xác.
3. Đặt ngân sách cache phù hợp với phần heap an toàn; tính overhead của cả key/value và cache metadata.
4. Ước lượng số entry có thể giữ: `targetEntries ≈ budgetBytes / meanRetainedBytesPerEntry`.
5. Dùng `maximumSize` làm điểm xuất phát rồi load test với dữ liệu thật và phân phối key thật.

Ví dụ minh họa, không phải công thức sizing tuyệt đối:

```text
Ngân sách heap dự kiến cho một vùng: 128 MiB
Chi phí retained trung bình mỗi entry: 16 KiB
Số entry ước lượng: 128 × 1024 / 16 = 8192
Điểm bắt đầu thử nghiệm: maximumSize khoảng 8000
```

Tỷ lệ retained memory có thể lệch lớn nếu có object graph chia sẻ references, string deduplication, class metadata, direct buffers hoặc giá trị ngoại lệ rất nặng. Vì vậy bắt buộc đo lại dưới tải thực.

### 10.2. Từ payload distribution đến `maximumWeight`

Nếu 90% entry là 1 KiB nhưng 10% là 1 MiB, một giới hạn `maximumSize(1000)` có thể khiến heap rất khó dự đoán. Đặt `maximumWeight` và weigher theo kích thước payload logic thường hữu ích hơn.

Ví dụ:

```text
Weigher(value) = số KiB payload (làm tròn lên)
maximumWeight = 65536
Đơn vị ngân sách = 65536 KiB ≈ 64 MiB payload logic
```

Với một record 1 MiB, chi phí xấp xỉ 1024 units; record 1 KiB chi phí 1 unit. Đây là mô hình chi phí tốt hơn so với đếm mọi entry là 1, nhưng **không đo trực tiếp heap**.

### 10.3. Khi ngân sách quá nhỏ

Một cache có quota 10 entry nhưng luôn truy cập tuần tự 100 key sẽ gần như liên tục miss. Kết quả có thể tệ hơn không dùng cache vì có overhead quản lý mà database vẫn chịu tải.

Phân tích hit rate theo loại traffic: tỷ lệ miss ở key lạnh có thể chấp nhận được, nhưng miss ở key nóng do churn là dấu hiệu cần tăng quota, tách vùng hoặc tối ưu key granularity.

### 10.4. Khi ngân sách quá lớn

Tăng quota thường cải thiện hit rate tới một mức nào đó nhưng có thể kéo theo:

- Heap sử dụng gần `-Xmx` và GC pause tăng.
- Thời gian warmup hoặc thời gian restart tăng.
- Nhiều stale object bị giữ lâu nếu TTL không phù hợp.
- Tạo nhiều bản sao lớn khi scale ứng dụng từ 3 lên 30 pod.
- Khó phát hiện memory leak ở phần khác của ứng dụng.

Không chạy theo hit rate tối đa mà bỏ qua latency P99, memory pressure và downstream QPS.

## 11. Lưu ý về thread safety, mutation và những yếu tố kết hợp

### 11.1. Value mutable không phù hợp với weigher tĩnh

Nếu object `value` sau khi được cache lại tăng kích thước, `weigher` không được gọi lại chỉ vì mutation. Điều này khiến tổng weight thống kê **nhỏ hơn chi phí thực tế**.

Giải pháp:

- Dùng `record`/immutable DTO hoặc collection snapshot.
- Khi cần thay đổi value, tạo value mới rồi `put`/`@CachePut` để kích hoạt tính trọng lượng lại.
- Không chia sẻ object mutable rồi thay đổi nó từ một thread khác mà không có đồng bộ phù hợp.
- Nếu size thay đổi không kiểm soát và không thể snapshot, cân nhắc cache serialized form hoặc xây cache policy khác.

### 11.2. Key đúng vẫn quan trọng

`maximumSize` và `maximumWeight` chỉ tác động đến eviction, **không sửa lỗi cache key**. Nếu method trả dữ liệu theo tenant và user scope nhưng key chỉ là productId, cache có thể trả nhầm dữ liệu, bất kể quota là bao nhiêu.

Các request có filter/locale/page thay đổi liên tục khiến cardinality rất cao; thiết kế canonical keys giúp giảm false misses và tránh dùng quota vào các key tương đương.

### 11.3. Expiration và capacity eviction khác nhau

`expireAfterWrite` loại giá trị theo thời gian từ lần ghi; `expireAfterAccess` dựa vào khoảng thời gian không truy cập; `maximumSize`/`maximumWeight` dựa vào áp lực số entry hoặc weight. Một entry có thể bị loại theo **bất cứ nguyên nhân phù hợp nào**.

Một TTL dài không có nghĩa cache sẽ giữ value suốt TTL nếu đã vượt capacity. Ngược lại, quota lớn không có nghĩa dữ liệu sẽ tươi nếu không có expiry hoặc invalidation khi nguồn thay đổi.

### 11.4. Concurrency và hot key

Khi cache đầy và loại một key cực nóng, nhiều request có thể gặp miss đồng thời. `@Cacheable(sync=true)` yêu cầu provider phối hợp loader theo key khi hỗ trợ, nhưng không thay đổi quota và có giới hạn riêng: một cache per operation, không `unless`, không ghép các cache operations khác trên cùng method.

Ví dụ minh họa:

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public Product load(String id) {
    return repository.find(id);
}
```

Caffeine có các cơ chế atomic get/load trong phạm vi native cache instance. Nhưng nếu có nhiều JVM mỗi JVM có Caffeine cache riêng, `sync=true` **không** đảm bảo đúng một DB request cho cả cluster.

### 11.5. Caffeine local không phải shared distributed cache

- Mỗi JVM có cache instance và quota riêng.
- Pod A evict một key do capacity pressure không có nghĩa pod B cũng xóa key đó.
- Một pod restart tạo cache mới trống; warmup có thể gây tải nguồn.
- Nếu cần shared cache đa node, dùng provider phù hợp như Redis/JCache và thiết kế consistency/invalidation; Caffeine vẫn có thể là L1 cache nhưng không tự trở thành Redis.

### 11.6. `maximumWeight` không phải strict hard cap cho RSS

Ngay cả khi `weightedSize() <= maximumWeight`, heap/RSS có thể vượt ngân sách logic do overhead, objects chia sẻ, serialization buffers, các threads đang load, native memory và timing của maintenance. Với hệ thống có yêu cầu tránh OutOfMemory, đặt headroom, memory limit của container, heap monitoring và load testing; đừng coi weigher như một trình đo heap chính xác.

## 12. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra và sửa |
|---|---|---|
| `@Cacheable` có cache nhưng RAM tăng liên tục | Không có quota hoặc quá nhiều vùng cache | Xác minh `CaffeineCacheManager`, `maximumSize/Weight` và số cache names |
| `maximumSize(1000)` nhưng heap vẫn quá cao | Có entry rất lớn; quota đếm entry, không đếm bytes | Dùng weighted policy hoặc tách cache |
| Cấu hình đồng thời `maximumSize` và `maximumWeight` lỗi | Hai capacity policies loại trừ nhau | Chọn một policy trên mỗi cache |
| `maximumWeight` không hoạt động | Thiếu `weigher` hoặc cấu hình bị thay bởi spec khác | Kiểm tra builder thật, Boot precedence và native policy |
| Weigher thường xuyên ném `ClassCastException` | Spring cache chứa nhiều value types, null sentinel hoặc cast sai | Tách cache theo type, kiểm soát null, viết weigher an toàn |
| Cache trả value nhưng lần sau vẫn miss | Trọng lượng entry > quota; cache không giữ entry | Đo weight thực, tăng budget hợp lý hoặc tách dữ liệu |
| Weighted size báo rất thấp, heap lại cao | Object mutable tăng size sau put hoặc weight thiếu overhead | Chuyển sang snapshot/immutable; cải thiện ước lượng |
| Cấu hình `maximumWeight=100000` nhưng nói đó là 100 KB | Không xác định đơn vị của weigher | Ghi rõ unit (bytes, KiB, record, vertices) |
| Tăng size lên nhưng hit rate vẫn thấp | Key cardinality quá lớn hoặc TTL quá ngắn | Đo key distribution, expiration, query parameters |
| Test khẳng định key A phải bị loại nhưng thất bại | Caffeine chọn nạn nhân theo adaptive eviction | Test budget sau maintenance, không ép thứ tự |
| `estimatedSize()` tạm vượt target | Maintenance chưa hoàn tất | Dùng `cleanUp()` trong test, tránh khẳng định tức thời |
| Properties Boot không tác động bean đã cấu hình | Có custom `CacheManager` hoặc spec được ưu tiên | Kiểm tra type bean và điều kiện auto-config |
| Một vùng weighted, vùng khác bị thay đổi policy ngoài ý muốn | `setCaffeine` áp chung manager | Dùng `registerCustomCache` hoặc manager riêng |
| Khi thêm Caffeine dependency vẫn không cache | Chưa bật `@EnableCaching` hoặc self-invocation | Xác minh Spring proxy và bean lifecycle |
| Eviction nhiều làm DB tăng QPS | Quota quá nhỏ, key nóng bị thay thế thường xuyên | Tuning theo hit rate, đặt capacity phù hợp, sync/hạn tải |
| Nhiều pod cộng lại dùng nhiều heap | Caffeine local là quota **per-instance** | Lập ngân sách toàn cluster và theo số replica |
| `recordStats()` không có dữ liệu | Chưa bật stats trên native cache tương ứng | Xác nhận manager/backend đang dùng và bật recordStats |

## 13. Bài kiểm thử tự luyện

### Bài 1 — Chọn size hay weight

Hệ thống lưu hai loại dữ liệu:

- `Cache A`: profile String/DTO nhỏ, chi phí retained gần giống nhau.
- `Cache B`: file metadata hoặc binary payload, kích thước từ 1 KiB đến hàng MB.

**Hướng chọn:** với A thử `maximumSize`; với B cân nhắc `maximumWeight` và weigher dựa trên payload units. Vẫn cần đo heap thật, vì weight không phải bytes heap.

### Bài 2 — Mutable value

`weigher` tính `List.size()`, đã cache list có 10 phần tử. Caller thêm 500 phần tử vào cùng object mà không `put` lại. Hỏi `weightedSize()` có tự tăng theo size mới không?

**Trả lời:** Không. Weight được ghi nhận khi entry được tạo hoặc cập nhật qua cache; mutation object ngoài cache không kích hoạt cân lại. Dùng immutable snapshot/đặt lại value.

### Bài 3 — Quá ngân sách

Weighted cache có quota 5 units, entry mới có weight 6. Method `@Cacheable` được gọi hai lần. Hỏi có chắc lần hai hit không?

**Trả lời:** Không. Entry quá quota có thể bị từ chối giữ lại/evict; lần hai sẽ miss. Đừng đồng nhất việc method đã return với việc provider đã giữ entry.

### Bài 4 — Hai cache cùng một manager

Manager dùng `maximumSize(1000)` cho vùng `users` và `products`. Hỏi tổng hai vùng tối đa 1.000 entry hay mỗi vùng riêng 1.000 entry?

**Trả lời:** Chính sách áp dụng lên từng Cache được manager tạo; hai vùng có quota độc lập. Dự toán tổng capacity theo các vùng.

### Bài 5 — Thiết kế kiểm thử

Dùng `maximumSize(2)`; gọi A, B, C, rồi `cleanUp()`. Hỏi có nên assert A chắc chắn bị loại?

**Trả lời:** Không. Test nên kiểm tra số entry trong quota sau maintenance, số lần loader và hit/miss theo mục tiêu; Caffeine không cam kết thứ tự eviction kiểu FIFO cho trường hợp tổng quát.

## 14. Checklist áp dụng trong dự án

1. **Bài toán là cardinality hay memory footprint?** Nếu giá trị gần đồng đều, khởi đầu với `maximumSize`; nếu chênh lệch nhiều, nghiên cứu weighted policy.
2. **Mỗi cache region có ngân sách riêng chưa?** `setCaffeine` áp dụng chung cho các cache của manager; `registerCustomCache` dùng khi khác chính sách.
3. **Đơn vị weight là gì?** Bytes, KiB, số record hay chi phí tính toán? Ghi rõ trong code và dashboard.
4. **`Weigher` có nhanh và ổn định không?** Không IO, không giá trị âm, không overflow, không phụ thuộc mutation sau khi put.
5. **Value có bất biến không?** Nếu mutable, liệu weight bị stale không? Có cần snapshot không?
6. **Đã tránh hai giới hạn trên một builder?** `maximumSize` và `maximumWeight` không dùng đồng thời.
7. **Dependencies đúng chưa?** Spring Framework dùng `spring-context-support` cho `CaffeineCacheManager`; Boot starter cache có thể kéo module này.
8. **`@EnableCaching` và proxy đúng chưa?** Không đánh giá hiệu quả nếu annotation thực tế không được intercept.
9. **Boot precedence đúng chưa?** `spring.cache.caffeine.spec` có thể được ưu tiên hơn bean builder; custom manager không tự áp dụng mọi property.
10. **Đã kiểm tra provider và policy thực chưa?** Lấy native cache, gọi `policy().eviction()` và đo `estimatedSize()/weightedSize`.
11. **Đã đo hit rate + nguồn dữ liệu + GC chưa?** Không tuning chỉ bằng một con số quota.
12. **Đã test key quá nặng, 0 weight, null và mutable object chưa?** Bao phủ các edge cases theo model thực tế.
13. **Đã kiểm thử nhiều vùng và nhiều pod chưa?** Quota theo Cache instance, không phải tổng hệ thống.
14. **Đã thiết kế expiration và invalidation riêng chưa?** Capacity không thay TTL; TTL không giải quyết budget.
15. **Đã dự phòng hệ quả miss/stampede chưa?** Quota nhỏ có thể tạo churn; consider `sync=true`, load shedding và load test.

### Kết luận

**`maximumSize(N)` giới hạn số lượng entry; `maximumWeight(W)` kết hợp `weigher` giới hạn tổng chi phí ước lượng của entries.** Hai phương án không được dùng đồng thời trong cùng cache builder. Weight được tính khi thêm/cập nhật entry, không tự thay đổi khi object mutable bị sửa, và không phải phép đo heap chính xác. Khi tích hợp Spring, cấu hình chính sách tại `CaffeineCacheManager` hoặc custom native cache, để `@Cacheable` chỉ tập trung mô tả vùng cache và key. Hãy đánh giá với workload thực: hit rate, quota theo từng vùng, heap/GC, loader count và ảnh hưởng lên nguồn dữ liệu.

### Tài liệu đối chiếu

- Caffeine Wiki — Eviction, maximumSize, maximumWeight, weigher và weight semantics: https://github.com/ben-manes/caffeine/wiki/Eviction
- Caffeine Wiki — Statistics: https://github.com/ben-manes/caffeine/wiki/Statistics
- Caffeine Javadoc — Caffeine builder: https://javadoc.io/doc/com.github.ben-manes.caffeine/caffeine/3.2.2/com.github.benmanes.caffeine/com/github/benmanes/caffeine/cache/Caffeine.html
- Spring Framework 6.2 — `CaffeineCacheManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Spring Framework — Cache abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Boot — Caching / Caffeine configuration: https://docs.spring.io/spring-boot/reference/io/caching.html
