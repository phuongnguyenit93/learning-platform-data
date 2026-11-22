# `put` và `putIfAbsent` trong Spring Cache — thao tác ghi bằng API lập trình

## 1. Bài toán: ghi đè hay chỉ tạo khi key chưa tồn tại?

Spring Framework có hai phong cách làm việc với cache:

- **Declarative caching:** đặt `@Cacheable`, `@CachePut`, `@CacheEvict` trên phương thức, Spring interceptor phụ trách thao tác.
- **Programmatic caching:** lấy một đối tượng `org.springframework.cache.Cache` rồi chủ động gọi `get`, `put`, `putIfAbsent`, `evict` trong code.

Bài này tập trung vào hai thao tác trực tiếp trên `Cache`:

```java
cache.put("P100", product);                      // Ghi hoặc ghi đè.
Cache.ValueWrapper previous =
        cache.putIfAbsent("P100", anotherProduct); // Chỉ thêm khi chưa có.
```

Giả sử hai request đều muốn lưu dữ liệu tại key `P100`:

- Với `put`, request ghi sau có thể **thay thế** giá trị của request ghi trước.
- Với `putIfAbsent`, khi key đã có mapping, ứng dụng **giữ nguyên** giá trị cũ và nhận thông tin về mapping ấy.

Khác biệt này quan trọng khi khởi tạo cache một lần, cạnh tranh giữa nhiều thread, muốn tránh ghi đè, hoặc cần mô hình “first writer wins” đối với **entry cache**. Nhưng `putIfAbsent` không tự tạo giao dịch cho database và không bảo đảm loại trừ ghi giữa nhiều node nếu provider không hỗ trợ atomic operation ở phạm vi đó.

## 2. Đối tượng `Cache` và cách lấy một vùng cache

Spring định nghĩa `org.springframework.cache.Cache` như API chung cho cache provider. Mỗi vùng có **tên cache** và tập ánh xạ **key → value**.

```java
import java.util.Objects;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;

Cache cache = Objects.requireNonNull(
        cacheManager.getCache("products"),
        "products cache is not configured");
```

Đây là một **mảnh minh họa** trong code đã có biến `cacheManager`. Ví dụ hoàn chỉnh ở mục 6 tạo `ConcurrentMapCacheManager` thật và không cần cấu hình Spring proxy.

`CacheManager.getCache("products")` có thể trả `null` khi manager không quản lý tên đó; riêng một số manager có thể tự tạo cache động. Không gọi `cache.put(...)` khi biến `cache` có thể null.

Cũng cần phân biệt:

- **Tên cache:** `products` xác định vùng.
- **Key:** `P100` xác định entry bên trong vùng.
- **Value:** đối tượng được lưu dưới key.
- **Cache provider:** triển khai lưu trong JVM, Caffeine, Redis, JCache hoặc backend khác; quyết định atomicity, null handling, TTL và tính bền vững.

Hai vùng khác nhau có thể sử dụng cùng key mà không có cùng value. Hai manager khác nhau có thể cùng quản lý tên vùng nhưng dùng hai kho dữ liệu độc lập.

## 3. `Cache.put(key, value)`: ghi hoặc thay thế không điều kiện

Chữ ký chính:

```java
void put(Object key, @Nullable Object value);
```

Về mặt hợp đồng, `put` **gắn giá trị được cung cấp với key**. Nếu key đã tồn tại, mapping cũ bị thay bằng giá trị mới.

```java
cache.put("P100", "Bút");
cache.put("P100", "Bút xanh"); // Ghi đè.
System.out.println(cache.get("P100", String.class)); // Bút xanh
```

Đoạn trên đúng khi provider đã áp dụng các put tức thời như `ConcurrentMapCache`; một số decorator/provider có thể trì hoãn việc ghi, được giải thích ở mục 8.

Những đặc tính chính:

1. `put` không kiểm tra giá trị cũ trước khi quyết định thay thế. Đây là lựa chọn khi **chủ ý cập nhật** cache theo trạng thái mới.
2. `put` trả `void`, vì vậy caller không nhận được thông tin “key có sẵn hay chưa” hoặc “value cũ là gì” từ chính lời gọi đó.
3. `put` không tự gọi database, không kiểm tra dữ liệu còn mới và không phát sinh TTL nếu provider chưa cấu hình.
4. `put` có thể được thực hiện bất đồng bộ hoặc **deferred** trong một số implementation, vì vậy đừng mặc định rằng một thread khác lập tức quan sát được value mới chỉ sau khi lời gọi `put` trả về.
5. Khi nhiều writer cùng `put` một key, việc caller nào viết sau và giá trị cuối cùng phụ thuộc vào thứ tự thực tế do provider xử lý. `put` không phải compare-and-set.

**Khi nên dùng:** chủ động cập nhật cache sau khi xác định dữ liệu mới chính xác, làm mới snapshot, hoặc thay entry cũ theo sự kiện cập nhật đã được xử lý nhất quán.

**Cảnh báo:** đừng dùng `put` như nguồn dữ liệu có giao dịch. Nếu database transaction rollback sau khi đã ghi cache, cache có thể chứa value chưa từng được commit. Cần xét transaction awareness và thứ tự invalidation.

## 4. `Cache.putIfAbsent(key, value)`: thêm nếu trước đó chưa có mapping

Chữ ký:

```java
@Nullable
Cache.ValueWrapper putIfAbsent(Object key, @Nullable Object value);
```

Hợp đồng lý tưởng: **kiểm tra và thêm như một thao tác nguyên tử**. Nếu key chưa được ánh xạ, đưa value vào; nếu key đã được ánh xạ, không ghi đè.

```java
Cache.ValueWrapper first = cache.putIfAbsent("P100", "Bút");
Cache.ValueWrapper second = cache.putIfAbsent("P100", "Bút xanh");

System.out.println(first == null); // true: key chưa có, đã thêm "Bút".
System.out.println(second.get());  // Bút: giữ nguyên entry cũ.
```

Đoạn trên giả định cache ban đầu rỗng và implementation hỗ trợ chính xác ngữ nghĩa `putIfAbsent`.

### 4.1. Giá trị trả về phải được diễn giải đúng

| Kết quả trả về | Ý nghĩa theo hợp đồng |
| --- | --- |
| `null` (chính đối tượng wrapper là null) | Không có mapping trước lời gọi; value được chấp nhận thêm |
| `ValueWrapper` khác null, `get()` khác null | Đã có mapping; **không** thay value cũ |
| `ValueWrapper` khác null, `get() == null` | Đã có entry mang **cached null** (nếu provider hỗ trợ); không coi là key chưa tồn tại |

Ví dụ phải kiểm tra wrapper trước khi đọc:

```java
Cache.ValueWrapper previous =
        cache.putIfAbsent("P200", newProduct);

if (previous == null) {
    System.out.println("Tạo entry cache mới");
} else {
    System.out.println("Entry đã tồn tại: " + previous.get());
}
```

`newProduct` là biến của một service thực tế, còn phương thức `putIfAbsent` **không trả boolean**. Nếu muốn biết thao tác đã chèn hay không, kiểm tra **`previous == null`**, không lấy kết quả `previous.get() == null` làm điều kiện.

Điểm này đặc biệt quan trọng khi provider cho phép cache giá trị Java `null`.

### 4.2. Không thay thế `putIfAbsent` bằng hai lệnh `get` rồi `put`

Mẫu sau có race condition:

```java
// KHÔNG an toàn khi nhiều thread cùng chạy.
if (cache.get("P100") == null) {
    cache.put("P100", value);
}
```

Hai thread có thể cùng thấy `get` trả null, rồi lần lượt `put`, khiến một writer ghi đè writer khác. Đó là lỗi **check-then-act / TOCTOU**.

`putIfAbsent` được thiết kế để gom hai ý “kiểm tra” và “đặt value nếu thiếu” thành một thao tác. Tuy nhiên **khả năng nguyên tử thực tế phụ thuộc implementation**, xem mục 5; không suy ra chắc chắn chỉ từ tên phương thức.

### 4.3. Cached-null khác với cache miss

`Cache.get(Object key)` trả:

- **`null` wrapper:** không có mapping.
- **`ValueWrapper` với `get() == null`:** có mapping, value là null.

Ví dụ:

```java
Cache.ValueWrapper wrapper = cache.get("P100");
boolean absent = wrapper == null;
boolean cachedNull = wrapper != null && wrapper.get() == null;
```

Biến thể `cache.get(key, SomeClass.class)` thường **không phân biệt được** hai trường hợp đó vì nó trả value đã unwrap. Việc cho phép null và cách chuyển đổi sang giá trị native là thuộc cache provider/cấu hình.

Trong `ConcurrentMapCacheManager`, mặc định cho phép null bằng cách chuyển đổi nội bộ sang một sentinel; `ConcurrentHashMap` tự thân không chấp nhận value null. Một entry cached-null vẫn **đã tồn tại**, nên `putIfAbsent(key, nonNullValue)` không được ghi đè nó.

## 5. Tính nguyên tử: kỳ vọng API và giới hạn implementation

Javadoc của `Cache.putIfAbsent` mô tả thao tác thêm khi chưa có một cách nguyên tử. Nhưng cùng Javadoc cảnh báo: **default implementation của interface `Cache`** có thể triển khai bằng `get` rồi `put`, tức là hai bước **không nguyên tử**. Các `CacheManager` có sẵn do Spring cung cấp được tài liệu mô tả là có khả năng thực hiện atomic put, nhưng vẫn phải kiểm tra provider/cache adapter đang dùng.

| Tình huống | `put` | `putIfAbsent` với implementation atomic |
| --- | --- | --- |
| Key chưa có | Ghi value | Ghi value, trả null wrapper |
| Key đã có `"V1"` | Thay bằng `"V2"` | Giữ `"V1"`, trả wrapper của `"V1"` |
| Key đang chứa cached-null | Thay bằng value mới | Giữ cached-null, trả wrapper có `get() == null` |
| Hai writer cùng cố thêm key trống | Writer nào được xử lý sau có thể thay trước | Chỉ một writer thêm thành công trong cuộc cạnh tranh đó |
| Entry bị evict/expire sau lần thêm | Lần ghi mới có thể xảy ra | Một lượt `putIfAbsent` sau có thể lại thêm vì key đã vắng mặt |

Một implementation có thể bảo đảm atomic trên **một instance** nhưng không có khả năng loại trừ cạnh tranh giữa nhiều JVM. Ví dụ, `ConcurrentMapCache` dựa trên cấu trúc dữ liệu concurrent trong một JVM; điều đó không có nghĩa nó là kho cache phân tán.

Với Redis/JCache/Caffeine hoặc custom adapter, cần đọc document và kiểm thử đúng phiên bản, nhất là các câu hỏi:

- Phép check-and-set là atomic **trong provider** hay chỉ trong một wrapper Java?
- Khi hai app instance ghi cùng key, chúng có dùng cùng vùng khóa/atomic operation không?
- Khi bị lỗi kết nối hoặc timeout, callback nhận thông báo gì? Có thể thao tác đã ghi thành công nhưng client không nhận phản hồi không?
- Backend có hỗ trợ cached-null và serialization key/value giống nhau trên mọi node không?
- Nếu có TTL/eviction, kết quả cuối cùng sau khi key hết hạn và được thêm lại là gì?

**Không dùng `putIfAbsent` làm cơ chế lock phân tán mặc định.** Nó đặt một entry khi chưa có; không cung cấp lease ownership, token, timeout an toàn hay cách giải phóng khóa phù hợp. Cache có thể bị xóa/expire trong khi tác vụ vẫn chạy.

## 6. Ví dụ Java 17 + Spring 6.2.9 chạy được

Ví dụ này sử dụng API `Cache` **trực tiếp**, không phụ thuộc `@EnableCaching` hay Spring AOP. Mục tiêu là kiểm tra từng trạng thái key, giá trị trả về của `putIfAbsent` và cuộc cạnh tranh giữa hai thread.

**Cấu trúc thư mục:**

```text
cache-put-demo/
├── pom.xml
└── src/main/java/CachePutDemo.java
```

**Nội dung `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cache-put-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**Nội dung `src/main/java/CachePutDemo.java`:**

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.springframework.cache.Cache;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;

public class CachePutDemo {

    private static String oldValue(Cache.ValueWrapper wrapper) {
        return wrapper == null
                ? "ABSENT"
                : String.valueOf(wrapper.get());
    }

    public static void main(String[] args) throws Exception {
        var manager = new ConcurrentMapCacheManager("products");
        manager.setAllowNullValues(true);
        Cache cache = Objects.requireNonNull(
                manager.getCache("products"));

        System.out.println("A initially: "
                + oldValue(cache.get("A")));

        cache.put("A", "Alpha");
        System.out.println("A after put: "
                + cache.get("A", String.class));

        cache.put("A", "Alpha-v2");
        System.out.println("A after replace: "
                + cache.get("A", String.class));

        Cache.ValueWrapper priorA =
                cache.putIfAbsent("A", "Ignored");
        System.out.println("A previous: "
                + oldValue(priorA));
        System.out.println("A after putIfAbsent: "
                + cache.get("A", String.class));

        Cache.ValueWrapper priorB =
                cache.putIfAbsent("B", "Beta");
        System.out.println("B previous: "
                + oldValue(priorB));
        System.out.println("B after insert: "
                + cache.get("B", String.class));

        cache.put("N", null);
        Cache.ValueWrapper priorN =
                cache.putIfAbsent("N", "Replacement");
        System.out.println("N previous entry exists: "
                + (priorN != null));
        System.out.println("N previous value null: "
                + (priorN != null && priorN.get() == null));
        Cache.ValueWrapper currentN = cache.get("N");
        System.out.println("N remains cached null: "
                + (currentN != null && currentN.get() == null));

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch go = new CountDownLatch(1);
        try {
            List<Future<Boolean>> results = new ArrayList<>();
            for (int i = 1; i <= 2; i++) {
                String candidate = "writer-" + i;
                results.add(pool.submit(() -> {
                    ready.countDown();
                    go.await();
                    return cache.putIfAbsent("R", candidate) == null;
                }));
            }
            ready.await();
            go.countDown();

            int inserted = 0;
            for (Future<Boolean> result : results) {
                if (result.get()) {
                    inserted++;
                }
            }

            String stored = cache.get("R", String.class);
            System.out.println("R successful inserts: " + inserted);
            System.out.println("R stores a candidate: "
                    + ("writer-1".equals(stored)
                        || "writer-2".equals(stored)));
        } finally {
            go.countDown();
            pool.shutdownNow();
        }
    }
}
```

**Chạy trong thư mục chứa `pom.xml`** (JDK 17+ và Maven):

```bash
mvn -q compile exec:java -Dexec.mainClass=CachePutDemo
```

**Các dòng do chương trình in ra**, không tính log Maven/SLF4J nếu môi trường có thêm:

```text
A initially: ABSENT
A after put: Alpha
A after replace: Alpha-v2
A previous: Alpha-v2
A after putIfAbsent: Alpha-v2
B previous: ABSENT
B after insert: Beta
N previous entry exists: true
N previous value null: true
N remains cached null: true
R successful inserts: 1
R stores a candidate: true
```

**Giải thích kết quả:**

1. `A` chưa có → `get("A")` trả null wrapper; lần `put` đầu ghi `Alpha`, lần `put` sau thay bằng `Alpha-v2`.
2. `putIfAbsent("A", "Ignored")` trả wrapper chứa `Alpha-v2`, không thay value đã có.
3. `putIfAbsent("B", "Beta")` trả null wrapper vì `B` chưa tồn tại và ghi mới `Beta`.
4. `N` được chủ động ghi `null`. Provider trong ví dụ có bật hỗ trợ null, nên `putIfAbsent("N", "Replacement")` thấy **entry đã tồn tại** và không thay nó; `priorN` là wrapper khác null nhưng `priorN.get()` bằng null.
5. Hai thread cùng `putIfAbsent("R", candidate)`. `ConcurrentMapCache` triển khai thao tác này nguyên tử trong cùng JVM; chỉ **một** caller thấy kết quả null wrapper. Ứng dụng không in tên “người thắng” vì thứ tự thread không cố định.

Ví dụ dùng riêng `Cache` và `CacheManager` nên không yêu cầu Spring application context, `@EnableCaching` hay proxy. Chỉ cần dependency `spring-context`. Nó cũng không mô phỏng transaction, TTL hoặc chia sẻ cache giữa nhiều JVM.

## 7. `putIfAbsent` khác `get(key, Callable)` và `@Cacheable(sync=true)`

Ba thao tác dễ bị nhầm vì đều liên quan cache miss:

| Cơ chế | Giá trị mới được tạo khi nào? | Mục đích |
| --- | --- | --- |
| `cache.putIfAbsent(key, value)` | `value` **đã được tính trước khi gọi** | Không ghi đè key đang có |
| `cache.get(key, () -> load())` | Provider có thể chỉ gọi `load()` **khi key thiếu** | Lấy hoặc nạp value theo callback |
| `@Cacheable(sync=true)` | Interceptor gọi đường cache load có callback, nếu provider hỗ trợ | Giảm tải trùng khi nhiều lời gọi cùng miss theo key |

Ví dụ sau vẫn có thể gọi repository **hai lần**:

```java
// Hai thread đều có thể tính value trước.
Product expensive = repository.load(sku);
cache.putIfAbsent(sku, expensive);
```

Dù chỉ một thread thêm thành công, cả hai đã chạy `repository.load(sku)` trước đó. `putIfAbsent` không thể đảo ngược chi phí tính toán đã xảy ra.

Nếu mục tiêu là **không chạy loader trùng**, dùng đường value loader phù hợp và kiểm thử provider:

```java
Product product = cache.get(sku, () -> repository.load(sku));
```

Đoạn này chỉ minh họa khi `repository` có method `load` trả `Product`. `Cache.get(key, Callable)` có hợp đồng đồng bộ nạp được **khuyến nghị** nếu implementation hỗ trợ; không bảo đảm tuyệt đối cho mọi provider hay mọi node.

Tương tự, `@Cacheable(sync=true)` chịu giới hạn riêng: không hỗ trợ `unless`, chỉ một cache và không kết hợp operation khác trên cùng method synchronized. Đừng coi `putIfAbsent` là cách vòng qua các giới hạn đó.

## 8. Giao dịch, deferred write và tính nhất quán

### 8.1. `put` không nhất thiết hiển thị ngay

Spring Cache Javadoc cho phép `put` được thực hiện sau, ví dụ qua `TransactionAwareCacheDecorator`. Khi transaction Spring còn mở, decorator này có thể **hoãn put đến sau commit thành công**; nếu rollback, phần put bị hoãn không được áp dụng.

Dòng thời gian minh họa:

```text
Transaction bắt đầu
  -> update database
  -> cache.put("P100", productNew)   [có thể chỉ đăng ký callback]
  -> commit thành công
  -> decorator thực hiện put thật
```

Với `ConcurrentMapCache` trực tiếp như ví dụ mục 6, `put` áp dụng trong bộ nhớ ngay. Với decorator, asynchronous provider hoặc backend từ xa, cần kiểm tra thời điểm value thật sự được quan sát. Đừng áp dụng một kết luận cho mọi implementation.

### 8.2. `putIfAbsent` là thao tác immediate — không thể hoãn như `put`

`TransactionAwareCacheDecorator` phân biệt hai nhóm:

- `put`/`evict`/`clear` có thể được hoãn đến **after-commit** khi có transaction phù hợp.
- `putIfAbsent` và `evictIfPresent` có ngữ nghĩa tức thời, nên **không thể hoãn** cùng cách đó.

Điều này có thể gây vấn đề:

```text
Transaction bắt đầu
  -> tạo bản ghi P100 trong database (chưa commit)
  -> cache.putIfAbsent("P100", productNew)  [ghi ngay]
  -> transaction rollback
  -> database không có P100, cache vẫn có thể giữ P100
```

Vì vậy **không dùng `putIfAbsent` để thay thế `put` trong transaction chỉ vì muốn “atomic”**. Atomic về việc thêm key không đồng nghĩa atomic cùng transaction database.

Nếu cần transaction-aware caching, hãy kiểm tra rõ decorator và đặt thao tác cache vào thời điểm phù hợp, chẳng hạn sau commit, hoặc dùng outbox/event/invalidation strategy được kiểm thử. Nếu cần chức năng “chỉ tạo nếu chưa có” ở database, hãy dùng unique constraint hoặc compare-and-set của database, không dựa vào cache.

### 8.3. Race giữa put và evict vẫn tồn tại

`putIfAbsent` chỉ bảo vệ điều kiện **key đã tồn tại tại thời điểm kiểm tra-thêm**. Nó không khóa mọi thao tác khác:

```text
T1: đọc DB bản P100 cũ
T2: cập nhật DB bản P100 mới, evict P100
T1: putIfAbsent(P100, oldValue) -> thấy cache trống, ghi giá trị cũ
T3: đọc cache -> nhận oldValue
```

Đây là một race điển hình giữa cache load và update. Có thể cần versioning, invalidation sau commit, thiết kế read/write hợp đồng nhất quán, hoặc cơ chế cache theo phiên bản.

### 8.4. Cùng key nhưng khác cache name/provider

`putIfAbsent` áp dụng **một vùng Cache cụ thể**. Nó không bảo đảm giữa `productsLocal/P100` và `productsRedis/P100` nếu hai vùng có kho lưu riêng. `CompositeCacheManager` cũng chỉ chọn vùng theo tên, không tự làm L1/L2 theo key.

## 9. Liên hệ với `@CachePut` và API khai báo

`@CachePut` là một **annotation caching operation**, khác `Cache.put`:

```java
@CachePut(cacheNames = "products", key = "#p0.id()")
public Product save(Product product) {
    return repository.save(product);
}
```

Ví dụ trên là method minh họa của service đã có `repository` và kiểu `Product`. Khi đi qua Spring proxy, method thật vẫn chạy và Spring đưa kết quả vào cache theo annotation.

`@CachePut` **không phải tên khác của `putIfAbsent`**. Mục tiêu của nó là cập nhật cache bằng kết quả method; nó không cung cấp một cơ chế annotation chuẩn tương đương “chỉ put nếu chưa có”.

Ngược lại, khi dùng API lập trình:

```java
Cache cache = cacheManager.getCache("products");
cache.put(product.id(), product); 
```

Caller trực tiếp quyết định giá trị và thời điểm gọi. Nếu service dùng cả annotation và API lập trình, phải thống nhất region, key, kiểu dữ liệu, null policy và thời điểm invalidation; nếu không có thể vô tình tạo hai entry khác nhau cho cùng thực thể.

**Lưu ý:** việc gọi `Cache.put` hoặc `Cache.putIfAbsent` trực tiếp không yêu cầu `@EnableCaching` hay Spring AOP. Nhưng các annotation cache cần infrastructure Spring thích hợp và lời gọi qua interceptor/proxy. Không nhầm sự khác biệt này khi viết test.

## 10. Chọn API theo nhu cầu

| Nhu cầu thực tế | Gợi ý |
| --- | --- |
| Thay entry bằng kết quả mới đã được xác nhận | `cache.put(key, newValue)` |
| Chỉ đặt giá trị khởi tạo khi key chưa tồn tại | `cache.putIfAbsent(key, initialValue)` |
| Cần biết có entry trước đó không | Kiểm tra wrapper trả về từ `putIfAbsent` hoặc `get` |
| Tính value đắt và muốn tránh tính trùng trên miss | `cache.get(key, Callable)` khi provider bảo đảm phù hợp |
| Cập nhật cache bằng kết quả method đi qua Spring AOP | `@CachePut` |
| Không muốn giữ kết quả khi trả null | `@Cacheable(unless="#result == null")` cho operation phù hợp; không áp dụng máy móc vào `putIfAbsent` |
| Cần compare-and-set theo version | Dùng API hỗ trợ CAS/version của backend hoặc DB, không coi `putIfAbsent` là CAS đầy đủ |
| Cần lock phân tán cho nghiệp vụ | Dùng cơ chế khóa/transaction phù hợp; không suy ra từ một entry cache |

**Hai sự khác nhau không được bỏ qua:** `put` có thể thay thế value cũ và không trả thông tin về mapping; `putIfAbsent` không thay value cũ (khi implementation giữ đúng hợp đồng) và trả wrapper của mapping trước đó, có thể chứa Java `null`.

## 11. Lỗi phổ biến và kiểm thử bắt buộc

### 11.1. Các lỗi thường gặp

1. **Tưởng `putIfAbsent` trả boolean.** Sai: phương thức trả `Cache.ValueWrapper` hoặc null; dùng `previous == null` để xác định không có mapping trước đó.
2. **Nhầm cached-null với cache miss.** `wrapper.get() == null` không có nghĩa không có entry; phải kiểm tra `wrapper == null`.
3. **Tự viết `get` rồi `put`.** Hai thread có thể cùng thấy miss và ghi đè, trong khi `putIfAbsent` được thiết kế để tránh race ấy khi backend hỗ trợ atomic.
4. **Cho rằng mọi implementation đều atomic.** Default `Cache.putIfAbsent` có thể là hai bước; cần kiểm tra adapter và native cache.
5. **Giả định `put` hiển thị ngay.** `TransactionAwareCacheDecorator` hoặc backend async có thể trì hoãn thao tác.
6. **Cho rằng `putIfAbsent` cũng hoãn sau commit.** Với transaction-aware decorator, thao tác immediate không chờ after-commit, có rủi ro cache chứa dữ liệu từ transaction rollback.
7. **Dùng `putIfAbsent` để bảo đảm giá trị mới nhất.** Nó ưu tiên giá trị *đã có*, kể cả giá trị đã cũ; cần cập nhật/evict theo hợp đồng nghiệp vụ.
8. **Cho rằng `putIfAbsent` loại bỏ trùng lặp tính toán.** Nếu value được tải trước khi gọi, hai thread vẫn có thể cùng tải nguồn.
9. **Không để ý null policy.** Có provider từ chối null; `ConcurrentMapCache` có thể dùng sentinel; cần test provider thật.
10. **Dùng key mutable hoặc không phân biệt tenant.** Key sai có thể khiến entry được dùng chung giữa các nhóm dữ liệu không tương thích.
11. **Suy luận atomic một JVM thành atomic nhiều JVM.** Cache local và remote không cùng phạm vi; phải test đa node nếu cần.
12. **Dùng cache để thực thi ràng buộc duy nhất lâu dài.** Cache có TTL/evict và không thay thế constraint của database.

### 11.2. Các trường hợp test tối thiểu

| Ca thử | Hành động | Điều cần xác nhận |
| --- | --- | --- |
| Key vắng | `putIfAbsent(K,V1)` | Trả null wrapper; sau đó đọc được V1 |
| Key đã có | `put(K,V1)` rồi `putIfAbsent(K,V2)` | Trả wrapper V1; vẫn đọc được V1 |
| Ghi đè | `put(K,V1)` rồi `put(K,V2)` | Giá trị cuối cùng V2 theo semantics provider |
| Cached-null | `put(K,null)` rồi `putIfAbsent(K,V1)` | Nếu provider hỗ trợ: wrapper khác null, value null giữ nguyên |
| Hai thread cùng key trống | Cho hai thread gọi `putIfAbsent` | Với provider atomic, đúng một caller thêm |
| Hai process/nodes | Cùng ghi remote cache từ nhiều JVM | Kiểm tra atomic ở phạm vi thực, timeout và lỗi |
| Transaction rollback | Gọi `put` và `putIfAbsent` qua transaction-aware decorator | Kiểm tra deferred vs immediate |
| Key bị evict/expire | Thêm, xóa/hết hạn, rồi thêm lại | Có thể chèn mới khi mapping đã biến mất |
| Lỗi provider | Giả lập timeouts/failures | Xử lý lỗi, trường hợp “đã ghi nhưng chưa nhận phản hồi” |
| Cache hit/miss | Đọc qua `get` và kiểm tra wrapper | Không nhầm cached-null với missing |

Ngoài giá trị cuối, đo tỉ lệ lỗi, thời gian ghi cache, số lần tranh chấp cùng key, lần thay thế không mong muốn và tương tác với transaction. Khi dùng remote provider, đừng đưa key có thông tin nhạy cảm trực tiếp vào log hoặc nhãn metric.

## 12. Tóm tắt thực hành

Bộ quy tắc ngắn gọn:

```java
// Muốn ghi mới hoặc thay giá trị cũ:
cache.put(key, value);

// Muốn giữ giá trị cũ khi key đã tồn tại:
Cache.ValueWrapper previous = cache.putIfAbsent(key, value);
boolean inserted = previous == null;

// Muốn phân biệt miss và cached-null:
Cache.ValueWrapper current = cache.get(key);
boolean missing = current == null;
boolean storedNull = current != null && current.get() == null;
```

**Chọn `put` khi cố ý cập nhật; chọn `putIfAbsent` khi cần điều kiện “chưa có key thì mới thêm” và provider đáp ứng đúng yêu cầu atomicity.** Cả hai đều là thao tác trên cache entry, không thay thế transaction, khóa phân tán hoặc đảm bảo dữ liệu gốc nhất quán.

## Tài liệu chính thức

- Spring Framework 6.2.9 — `Cache` interface, `put` và `putIfAbsent`: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework 6.2.9 — `ConcurrentMapCache`: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html
- Spring Framework 6.2 — `TransactionAwareCacheDecorator`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html
- Spring Framework — Cache abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
