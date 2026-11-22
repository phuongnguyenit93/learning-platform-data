# Không lưu kết quả `null` bằng biểu thức phù hợp trong Spring Cache

## 1. Vì sao cần kiểm soát việc cache `null`?

Một phương thức đọc dữ liệu thường trả về `null` khi không tìm thấy bản ghi:

```java
public Account findById(String id) {
    return repository.findByIdOrNull(id);
}
```

Nếu cache lưu `null` cho khóa `"A100"`, một lần gọi tiếp theo có thể nhận lại `null` trực tiếp từ cache, không truy vấn nguồn dữ liệu. Đây là **negative caching**: lưu lại kết quả “chưa tìm thấy”. Nó có lợi nếu những lần truy vấn không tồn tại lặp lại rất nhiều, nhưng có thể gây sai kỳ vọng khi dữ liệu được tạo ngay sau đó.

Ví dụ trình tự:

1. Lúc 09:00, `findById("A100")` không tìm thấy bản ghi, trả `null`.
2. Cache có thể lưu giá trị `null` tại key `"A100"`, nếu provider/cấu hình cho phép.
3. Lúc 09:01, một thao tác khác tạo bản ghi `A100` trong database.
4. Lúc 09:02, `findById("A100")` vẫn có thể trả `null` từ cache, cho đến khi entry bị xóa, hết hạn hoặc được cập nhật.

Để **không lưu kết quả `null`**, Spring Cache hỗ trợ thuộc tính `unless` trên `@Cacheable`. Cấu hình trọng tâm:

```java
@Cacheable(cacheNames = "accounts", key = "#p0", unless = "#result == null")
public Account findById(String id) {
    return repository.findByIdOrNull(id);
}
```

Với cấu hình này, mỗi lần phương thức thực sự trả `null`, Spring bỏ qua bước đưa kết quả đó vào cache. Một lần gọi sau với cùng key vẫn phải chạy nguồn dữ liệu (nếu chưa có entry cache từ trước). Khi nguồn đã có đối tượng khác `null`, Spring mới lưu kết quả.

**Phạm vi bài:** cách chọn điều kiện không lưu dựa trên kết quả, SpEL `#result`, phân biệt `unless` với `condition`, tác động tới `Optional`, provider lưu null, vòng đời entry và kiểm thử hành vi.

## 2. `unless = "#result == null"` hoạt động như thế nào?

### 2.1. Hợp đồng của `@Cacheable`

Trong cơ chế cache thông thường, Spring xử lý một lời gọi đến bean đã được proxy/interceptor quản lý theo trình tự khái quát:

```text
Gọi service.findById("A100")
    |
    v
Tính cache key và kiểm tra condition (nếu có)
    |
    v
Tra cache theo key
    |
    +-- HIT -----------------------> Trả dữ liệu đã cache
    |
    +-- MISS --> Chạy method thật --> Nhận result
                                         |
                                         v
                              Đánh giá unless bằng SpEL
                                         |
                            +------------+------------+
                            |                         |
                        true: VETO               false: ALLOW
                            |                         |
                     Không lưu result           Lưu result vào cache
                            |                         |
                            +------------+------------+
                                         |
                                         v
                                  Trả kết quả
```

Với `unless = "#result == null"`:

| Kết quả thật của phương thức | Giá trị SpEL `#result == null` | Spring có đưa kết quả mới vào cache? |
| --- | --- | --- |
| `null` | `true` | **Không** |
| `new Account("A100", "Lan")` | `false` | Có, nếu thao tác cache được kích hoạt và provider ghi thành công |
| `""` (chuỗi rỗng) | `false` | Có, vì chuỗi rỗng khác `null` |
| `List.of()` (danh sách rỗng) | `false` | Có, vì danh sách rỗng khác `null` |
| `Optional.empty()` (kiểu Optional được Spring hỗ trợ) | `true` theo **giá trị bên trong** | Không |

`unless` là một **biểu thức SpEL trả về boolean**. Khi biểu thức trả `true`, Spring **veto** (từ chối) việc thêm kết quả của lời gọi vừa chạy vào cache. Tên `unless` dễ gây nhầm: `unless = "#result == null"` có nghĩa là “cache kết quả, **trừ khi** kết quả bằng null”.

### 2.2. `#result` là gì?

`#result` là biến ngữ cảnh được Spring cung cấp **sau khi phương thức đã trả kết quả**. Ví dụ:

```java
@Cacheable(
    cacheNames = "accounts",
    key = "#p0",
    unless = "#result == null"
)
public Account findById(String id) {
    // Một lời gọi thực tế có thể trả Account hoặc null.
    return repository.findByIdOrNull(id);
}
```

- `#p0` chọn tham số thứ nhất (ở đây là `id`) làm key, không phụ thuộc vào tên tham số khi biên dịch Java.
- `#result` tham chiếu **giá trị trả về** của phương thức (đã được Spring xử lý đối với wrapper được hỗ trợ).
- Toán tử `== null` kiểm tra trực tiếp giá trị null, không kiểm tra chuỗi ký tự `"null"`.
- Dấu nháy kép bên ngoài thuộc cú pháp Java annotation; nội dung bên trong là SpEL.

`#result` không tồn tại trong mọi thời điểm đánh giá biểu thức. Đối với `@Cacheable`, hãy dùng nó trong `unless`, **không** dùng `#result` trong `condition` hay `key` vì cả hai phải đánh giá trước khi phương thức chạy để quyết định có tra cache và tra theo khóa nào.

## 3. Phân biệt `condition` và `unless`

Đây là điểm dễ nhầm nhất khi muốn loại trừ dữ liệu `null`.

| Tiêu chí | `condition` | `unless` |
| --- | --- | --- |
| Đánh giá | Trước khi xét cache và gọi phương thức | Sau khi phương thức thật trả kết quả |
| Biết `#result`? | **Không** | **Có** |
| Khi biểu thức trả `true` | Cho phép áp dụng cơ chế caching | Từ chối lưu kết quả vừa tính |
| Khi biểu thức trả `false` | Bỏ qua caching cho lần gọi; method vẫn chạy | Cho phép lưu kết quả mới |
| Mục đích | Chọn request/tham số nào được cache | Chọn **kết quả** nào không được cache |

**Đúng:**

```java
@Cacheable(
    cacheNames = "accounts",
    key = "#p0",
    unless = "#result == null"
)
public Account findById(String id) {
    return repository.findByIdOrNull(id);
}
```

**Sai mục đích:**

```java
// Không dùng #result để kiểm tra kết quả tại giai đoạn condition.
@Cacheable(cacheNames = "accounts", condition = "#result != null")
public Account findById(String id) {
    return repository.findByIdOrNull(id);
}
```

Ở thời điểm `condition` chạy, giá trị trả về chưa được tính; biểu thức dựa vào `#result` không có ý nghĩa cho bài toán này và có thể dẫn đến lỗi đánh giá.

**Kết hợp khi cần lọc cả đầu vào lẫn đầu ra:**

```java
@Cacheable(
    cacheNames = "accounts",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()",
    unless = "#result == null"
)
public Account findById(String id) {
    return repository.findByIdOrNull(id);
}
```

Ý nghĩa: request có `id` null/trống sẽ không tham gia cache; request hợp lệ được tra cache nhưng nếu truy vấn nguồn trả `null` thì không lưu. `condition` không thay thế validation nghiệp vụ: phương thức vẫn có thể bị gọi với input không hợp lệ; nên kiểm tra input ở lớp thích hợp.

## 4. Cache hit, cache miss và “đã cache null” là ba tình huống khác nhau

Không nên đồng nhất “cache không có entry” với “cache có entry mang giá trị null”.

| Trạng thái một key trong cache | `cache.get(key)` | Hệ quả khi `@Cacheable` tra cứu |
| --- | --- | --- |
| Chưa có mapping | Trả `null` (không có `ValueWrapper`) | Cache miss; method thật được gọi |
| Có mapping với value `null` và provider hỗ trợ | Trả `Cache.ValueWrapper` khác null, `get()` bằng null | Cache hit; method thật có thể bị bỏ qua dù kết quả trả về null |
| Có mapping với một `Account` | Trả wrapper chứa `Account` | Cache hit; trả đối tượng đã lưu |

Đoạn mã minh họa khi đã có biến `Cache cache`:

```java
Cache.ValueWrapper wrapper = cache.get("A100");
if (wrapper == null) {
    System.out.println("MISS: key chưa có trong cache");
} else if (wrapper.get() == null) {
    System.out.println("HIT: key đang chứa null");
} else {
    System.out.println("HIT: " + wrapper.get());
}
```

`cache.get(key, Account.class)` trả về `null` cả khi miss và khi có cached-null, nên không thể dùng cách này để phân biệt hai trạng thái.

**Lưu ý về provider:** Spring Cache là abstraction; khả năng lưu null phụ thuộc backend và cấu hình. Ví dụ `ConcurrentMapCacheManager` mặc định hỗ trợ null bằng một đối tượng đại diện nội bộ vì `ConcurrentHashMap` không chấp nhận null trực tiếp. Các provider khác có thể không cho phép null hoặc xử lý khác nhau. `unless` đặt chính sách **không đưa kết quả null mới** vào cache ở tầng annotation, hữu ích ngay cả khi thay backend. Đừng giả định rằng tắt hỗ trợ null ở provider sẽ tự động tương đương `unless`: có implementation sẽ báo lỗi khi bị yêu cầu lưu null.

## 5. Ví dụ Java 17 chạy được: hai chính sách đối với cùng kết quả null

Chương trình sau dùng Spring Framework 6.2.x và cache bộ nhớ trong tiến trình. Hai region được tách ra để so sánh:

- `skipNull`: phương thức có `unless = "#result == null"`; truy vấn chưa có bản ghi sẽ tiếp tục đọc nguồn trong lần gọi sau.
- `allowNull`: phương thức không có `unless`; null được cache vì cấu hình ví dụ cho phép. Khi tạo bản ghi mới, entry cached-null cũ vẫn tồn tại cho tới khi bị evict.

Cả hai phương thức đều trả về cùng một kiểu `Account`. Số lần gọi `Repository.find` giúp kiểm tra chính xác khi nào cache hit hay miss.

**Cấu trúc:**

```text
cache-null-demo/
├── pom.xml
└── src/main/java/CacheNullDemo.java
```

**`pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cache-null-demo</artifactId>
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

**`src/main/java/CacheNullDemo.java`:**

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheNullDemo {

    @Bean
    CacheManager cacheManager() {
        var manager =
                new ConcurrentMapCacheManager("skipNull", "allowNull");
        manager.setAllowNullValues(true);
        return manager;
    }

    @Bean
    AccountRepository accountRepository() {
        return new AccountRepository();
    }

    @Bean
    AccountService accountService(AccountRepository repository) {
        return new AccountService(repository);
    }

    public record Account(String id, String label) {}

    public static class AccountRepository {
        private final Map<String, Account> data = new ConcurrentHashMap<>();
        private final AtomicInteger reads = new AtomicInteger();

        public Account find(String id) {
            reads.incrementAndGet();
            return data.get(id);
        }

        public void save(Account account) {
            data.put(account.id(), account);
        }

        public int reads() {
            return reads.get();
        }
    }

    public static class AccountService {
        private final AccountRepository repository;

        public AccountService(AccountRepository repository) {
            this.repository = repository;
        }

        @Cacheable(
            cacheNames = "skipNull",
            key = "#p0",
            unless = "#result == null"
        )
        public Account findSkipNull(String id) {
            return repository.find(id);
        }

        @Cacheable(cacheNames = "allowNull", key = "#p0")
        public Account findAllowNull(String id) {
            return repository.find(id);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(CacheNullDemo.class)) {
            var service = context.getBean(AccountService.class);
            var repository = context.getBean(AccountRepository.class);
            var manager = context.getBean(CacheManager.class);

            System.out.println("skip #1: " + service.findSkipNull("A100"));
            System.out.println("skip #2: " + service.findSkipNull("A100"));
            System.out.println("skip reads: " + repository.reads());

            repository.save(new Account("A100", "Lan"));
            System.out.println("skip after insert: "
                    + service.findSkipNull("A100"));
            System.out.println("skip hit: "
                    + service.findSkipNull("A100"));
            System.out.println("skip reads: " + repository.reads());

            System.out.println("allow #1: "
                    + service.findAllowNull("B200"));
            System.out.println("allow #2: "
                    + service.findAllowNull("B200"));
            System.out.println("allow reads: " + repository.reads());

            repository.save(new Account("B200", "Minh"));
            System.out.println("allow after insert: "
                    + service.findAllowNull("B200"));

            Cache allowed = manager.getCache("allowNull");
            if (allowed == null) {
                throw new IllegalStateException("Missing allowNull cache");
            }
            Cache.ValueWrapper wrapper = allowed.get("B200");
            System.out.println("cached null exists: " + (wrapper != null));
            System.out.println("cached value is null: "
                    + (wrapper != null && wrapper.get() == null));

            allowed.evict("B200");
            System.out.println("allow after evict: "
                    + service.findAllowNull("B200"));
            System.out.println("all source reads: " + repository.reads());
        }
    }
}
```

Chạy với JDK 17+ và Maven trong thư mục có `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=CacheNullDemo
```

**Các dòng do chương trình in ra** (không tính log khởi tạo của công cụ hoặc Spring, nếu có):

```text
skip #1: null
skip #2: null
skip reads: 2
skip after insert: Account[id=A100, label=Lan]
skip hit: Account[id=A100, label=Lan]
skip reads: 3
allow #1: null
allow #2: null
allow reads: 4
allow after insert: null
cached null exists: true
cached value is null: true
allow after evict: Account[id=B200, label=Minh]
all source reads: 5
```

**Giải thích theo số lần đọc nguồn:**

1. `skipNull/A100` lúc chưa tồn tại: cả hai lần truy vấn đều miss vì mỗi lần trả null đều bị `unless` từ chối lưu. Bộ đếm bằng 2.
2. Sau khi `repository.save(A100)`, lần tìm kế tiếp đọc bản ghi mới và cache nó; lần kế tiếp hit. Bộ đếm tăng lên 3 và giữ nguyên.
3. `allowNull/B200` lúc chưa tồn tại: lần đầu gọi nguồn trả null và cache null; lần hai hit, không tăng bộ đếm (giữ ở 4).
4. Sau khi thêm `B200`, lời gọi `findAllowNull("B200")` vẫn thấy cached-null cũ, trả null. `Cache.get("B200")` cho một wrapper khác null nhưng `wrapper.get() == null`.
5. Khi `allowed.evict("B200")`, bản sao cũ biến mất; lần tìm tiếp theo đọc và cache bản ghi mới, bộ đếm tăng thành 5.

Trong chương trình này, `repository.save` được gọi trực tiếp để minh họa tác động của dữ liệu gốc thay đổi. Trong ứng dụng thật, thao tác tạo/sửa/xóa thường phải có chiến lược `@CacheEvict` hoặc `@CachePut` tương ứng. Việc bỏ qua null **không thay thế** invalidation đối với những entry khác null đã cache.

## 6. Phương thức trả `Optional<T>`: tránh nhầm wrapper với nội dung

Spring Cache hỗ trợ `java.util.Optional` với ngữ nghĩa đặc biệt: nếu `Optional` có giá trị, nội dung được cache; nếu trả `Optional.empty()`, giá trị đưa vào cache (nếu không bị veto) được xem là `null`. Trong ngữ cảnh `unless`, `#result` là **đối tượng bên trong Optional**, không phải wrapper `Optional`.

Ví dụ:

```java
@Cacheable(
    cacheNames = "accounts",
    key = "#p0",
    unless = "#result == null"
)
public java.util.Optional<Account> findOptional(String id) {
    return repository.findOptional(id);
}
```

Khi `repository.findOptional(id)` trả `Optional.empty()`, `#result` được đánh giá là null và Spring không lưu entry mới. Khi trả `Optional.of(account)`, `#result` là `account` và có thể được lưu. Đoạn trên chỉ minh họa method của một service đã có `repository` tương ứng, không thuộc chương trình `CacheNullDemo.java` độc lập ở mục trước.

**Tránh biểu thức sai trong ngữ cảnh `unless`:**

```java
// Dễ sai: #result là Account (hoặc null), không phải Optional<Account>.
@Cacheable(cacheNames = "accounts", unless = "#result.isEmpty()")
public java.util.Optional<Account> findOptional(String id) {
    return repository.findOptional(id);
}
```

Biểu thức này cố gọi `isEmpty()` trên entity hoặc null. Hãy dùng `unless="#result == null"` để từ chối cả `null` và `Optional.empty()`. Khi muốn kiểm tra một thuộc tính của entity có thể null, dùng SpEL safe navigation thích hợp, ví dụ `unless="#result == null || #result.disabled()"` nếu kiểu dữ liệu thật có method `disabled()`.

## 7. Khi nào biểu thức cần phức tạp hơn?

`unless = "#result == null"` là lựa chọn trực tiếp khi chỉ muốn loại trừ null. Có thể mở rộng theo hợp đồng của kết quả:

| Mục tiêu | Ví dụ `unless` | Ý nghĩa |
| --- | --- | --- |
| Không cache null | `"#result == null"` | Chặn giá trị thiếu |
| Không cache null hoặc danh sách rỗng | `"#result == null || #result.isEmpty()"` | Tránh lưu kết quả rỗng khi nguồn thay đổi thường xuyên |
| Không cache null hoặc entity chưa hợp lệ | `"#result == null || !#result.valid()"` | Dựa vào method `valid()` có thật của kiểu trả về |
| Không cache null hoặc dữ liệu tạm thời | `"#result == null || #result.temporary()"` | Chỉ lưu kết quả đã ổn định |

Đây là **các biểu thức minh họa**, chỉ dùng khi kiểu trả về có method tương ứng; Spring không tự tạo `valid()`/`temporary()`. Toán tử `||` đánh giá ngắn mạch: nếu vế `#result == null` là true, Spring không đánh giá vế truy cập method ở bên phải, nên tránh gọi trên null.

**Không tự động coi rỗng là null.** Danh sách rỗng có thể là một kết quả hợp lệ, ổn định, đáng cache. Nếu dữ liệu hiếm khi thay đổi nhưng truy vấn tốn chi phí, cache một danh sách rỗng có thể có lợi. Chỉ chặn rỗng nếu sản phẩm/chính sách cập nhật cần như vậy.

Nếu biểu thức dài hoặc quyết định dựa vào nhiều điều kiện nghiệp vụ, cân nhắc đưa kết quả về một kiểu trả về rõ ràng rồi viết test cho điều kiện. Một biểu thức ngắn, kiểm thử được thường dễ bảo trì hơn SpEL phức tạp trong annotation.

## 8. Những giới hạn quan trọng

### 8.1. `unless` không làm sạch cached-null đã tồn tại

Nếu một key đã được cache với null **trước khi** thêm `unless="#result == null"`, lời gọi `@Cacheable` về sau có thể hit entry cũ; method thật không chạy nên điều kiện `unless` của lần nạp mới không được áp dụng. Cần **evict key cũ** (hoặc clear region có chủ đích), thay key namespace/version, hoặc chờ TTL của provider. Điều này quan trọng khi triển khai bản nâng cấp ứng dụng.

### 8.2. Không kết hợp `@Cacheable(sync = true)` với `unless`

Spring Framework đặt hạn chế cho `@Cacheable(sync = true)`: thuộc tính `unless` không được hỗ trợ trong chế độ đồng bộ nạp này. Ví dụ sau **không hợp lệ về hợp đồng annotation**:

```java
// Không dùng tổ hợp này: sync=true không hỗ trợ unless.
@Cacheable(
    cacheNames = "accounts",
    key = "#p0",
    sync = true,
    unless = "#result == null"
)
public Account findById(String id) {
    return repository.findByIdOrNull(id);
}
```

Nếu cần đồng thời chống cache null và chống nhiều request cùng tải một key (cache stampede), hãy chọn giải pháp đồng bộ ở tầng dữ liệu/provider phù hợp và kiểm thử hành vi nạp, thay vì giả định có thể thêm `sync=true` vào annotation trên.

### 8.3. `@CachePut` và dữ liệu cũ

`@CachePut` **luôn chạy method thật** và cũng có thuộc tính `unless` để quyết định có ghi kết quả mới hay không. Nhưng nếu method trả null, `unless="#result == null"` **chỉ bỏ qua put mới**, không tự xóa một entry cũ đã tồn tại. Nếu null có nghĩa “bản ghi đã bị xóa” hoặc “không còn hợp lệ”, phải thực hiện evict theo hợp đồng cập nhật dữ liệu.

Ví dụ đoạn minh họa của service có sẵn:

```java
@CacheEvict(cacheNames = "accounts", key = "#p0")
public void delete(String id) {
    repository.delete(id);
}
```

Mặc định `@CacheEvict` thực hiện sau khi method thành công; với transaction, cần thiết kế thời điểm invalidation so với commit của nguồn dữ liệu.

### 8.4. Chi phí của việc không cache null

Nếu một ID không tồn tại bị hỏi hàng nghìn lần, `unless="#result == null"` sẽ tạo hàng nghìn lần truy vấn nguồn vì lần nào cũng miss. Do đó cần cân nhắc:

- **Dữ liệu rất động, bản ghi thường xuất hiện sau truy vấn:** bỏ cache null là hợp lý để phát hiện dữ liệu mới sớm hơn.
- **ID sai/không tồn tại bị tra rất nhiều:** có thể chủ động negative-cache trong một TTL ngắn, với chiến lược xóa khi bản ghi được tạo, để giảm tải nguồn.
- **Dữ liệu quan trọng, yêu cầu nhất quán cao:** cả việc skip-null lẫn TTL không thay thế quy trình đọc/ghi và xác nhận nghiệp vụ đúng.

Tùy provider, TTL, kích thước tối đa và hành vi phân tán được cấu hình riêng. Spring Cache annotation không cung cấp một TTL chung độc lập với provider. Khi chuyển từ cache local sang Redis hoặc cache nhiều node, phải kiểm thử lại các tình huống trả null, eviction, serialization và đồng bộ dữ liệu.

### 8.5. Proxy và phạm vi áp dụng

`@Cacheable` chỉ có tác dụng khi lớp được Spring quản lý và lời gọi được interception theo cấu hình caching (ví dụ `@EnableCaching`). Trong proxy mode mặc định, tự gọi `this.findById(...)` trong cùng bean thường bỏ qua advice; kết quả kiểm thử có thể sai vì method luôn chạy thay vì cache hit. Hãy kiểm thử bằng bean service nhận từ Spring context như chương trình minh họa.

Chính sách bỏ cache null áp dụng tại **cache operation được đánh dấu**, không biến thành một chính sách tự động trên mọi region, mọi call dùng `Cache.put(...)` hay mọi writer ở service khác.

## 9. Checklist và các lỗi dễ gặp

1. **Nhầm `condition` với `unless`:** muốn kiểm tra kết quả đã tính phải dùng `unless`, vì `condition` không có `#result`.
2. **Đảo nghĩa boolean:** `unless="#result != null"` sẽ từ chối lưu kết quả có dữ liệu và có thể cho phép lưu null, trái với mục tiêu.
3. **So sánh chuỗi `"null"`:** `#result == 'null'` không kiểm tra Java null, nó so sánh với chuỗi ký tự.
4. **Đánh giá sai `Optional`:** với wrapper được hỗ trợ, `#result` là entity bên trong; `Optional.empty()` tương ứng null khi xét cache.
5. **Chỉ nhìn kết quả trả về để suy ra hit/miss:** cả miss trả null lẫn cached-null hit đều trả null; đo số lần gọi repository hoặc đọc `Cache.ValueWrapper`.
6. **Quên xóa entry cũ khi nguồn thay đổi:** skip-null chỉ ngăn cache null mới, không tự cập nhật những value cũ hoặc null đã cache từ trước.
7. **Cho rằng provider chắc chắn lưu null:** hành vi null phụ thuộc `CacheManager` và provider; kiểm tra cấu hình thực tế.
8. **Kết hợp `unless` với `sync=true`:** không được Spring hỗ trợ; thiết kế xử lý concurrency ở chỗ khác.
9. **Không kiểm thử invalidation sau create/delete:** với nguồn có nhiều writer hoặc nhiều instance, phải đảm bảo vùng dữ liệu liên quan được cập nhật đúng.
10. **Không đánh giá hiệu năng:** liên tục miss cho ID không tồn tại có thể gây tải database lớn; quyết định skip-null cần phù hợp lưu lượng và tính mới dữ liệu.

Các ca kiểm thử nên có:

| Ca | Cách thực hiện | Kỳ vọng với `unless="#result == null"` |
| --- | --- | --- |
| Miss trả null liên tiếp | Đọc cùng ID chưa tồn tại hai lần | Nguồn được gọi hai lần |
| Miss rồi xuất hiện bản ghi | Đọc null, tạo bản ghi, đọc lại | Đọc được bản ghi mới và có thể cache |
| Hit đối tượng khác null | Đọc cùng ID hợp lệ hai lần | Nguồn chỉ được gọi một lần |
| `Optional.empty()` | Trả optional rỗng rồi gọi lại | Không cache kết quả rỗng |
| Đổi cấu hình với cached-null cũ | Seed cached-null rồi thêm `unless` | Phải evict/invalidate entry cũ để nhận dữ liệu mới |
| Lỗi từ nguồn | Method ném exception | Không lưu một kết quả mới; exception được truyền theo cơ chế thông thường |

## 10. Kết luận thực hành

Đối với phương thức đồng bộ trả một đối tượng hoặc null, biểu thức thường phù hợp nhất là:

```java
@Cacheable(cacheNames = "accounts", key = "#p0", unless = "#result == null")
public Account findById(String id) {
    return repository.findByIdOrNull(id);
}
```

Hãy hiểu đầy đủ hợp đồng của dòng này: **cache hit vẫn trả entry đã tồn tại; khi cache miss dẫn tới một kết quả null, Spring không ghi null mới; khi kết quả khác null, Spring có thể ghi vào cache**. Để hệ thống đúng lâu dài, cần thống nhất key và invalidation với thao tác tạo/sửa/xóa dữ liệu.

## Tài liệu chính thức

- Spring Framework — Cache Annotations / Conditional Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — `@Cacheable` Javadoc (điều kiện `unless` và hạn chế `sync`): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — `ConcurrentMapCacheManager` Javadoc (`allowNullValues`): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html
