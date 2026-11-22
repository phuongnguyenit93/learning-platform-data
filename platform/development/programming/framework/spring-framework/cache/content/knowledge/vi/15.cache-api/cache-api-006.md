# evict so với evictIfPresent trong Spring Cache

> **Spring Framework – Cache Abstraction · Nhóm: API lập trình.** Bài này so sánh `Cache.evict(Object key)` và `Cache.evictIfPresent(Object key)` khi cần vô hiệu hóa một entry cache. Khác biệt quan trọng nhất nằm ở **thời điểm nhìn thấy kết quả xóa** và **ý nghĩa của boolean trả về**, nhất là khi cache được bọc bằng transaction-aware decorator.

## 1. Cùng xóa một key, nhưng hợp đồng không hoàn toàn giống nhau

Giả sử cache `books` đang có:

~~~text
books["ISBN-A"] = "Java Basics"
books["ISBN-B"] = "Spring Basics"
~~~

Khi dữ liệu nguồn của ISBN-A thay đổi, chương trình muốn bỏ entry tương ứng để lần đọc sau không dùng bản cũ. Hai API thường gặp:

~~~java
cache.evict("ISBN-A");
boolean knownPresent = cache.evictIfPresent("ISBN-A");
~~~

Đoạn này chỉ minh họa lời gọi trong một method đã có biến `cache` kiểu `org.springframework.cache.Cache`. Ví dụ chạy được ở phần 6.

Cả hai cùng yêu cầu **xóa mapping của một key**, chứ không cập nhật cơ sở dữ liệu và không xóa cả vùng cache. Nhưng:

- `evict(key)` có kiểu trả về **`void`**; implementation có thể xóa ngay, bất đồng bộ hoặc **trì hoãn** thao tác. Lời gọi không cho biết key đã tồn tại trước đó.
- `evictIfPresent(key)` có kiểu trả về **`boolean`**; hợp đồng mong đợi key trở nên **không còn nhìn thấy ngay qua lookup kế tiếp**. Giá trị trả về cho biết implementation có biết mapping đã tồn tại trước khi xóa hay không.
- Sự bảo đảm ở mức hệ thống còn phụ thuộc backend, decorator và writer chạy đồng thời. **Xóa xong không ngăn một luồng khác put lại cùng key.**

### Bảng so sánh

| Tiêu chí | `evict(Object key)` | `evictIfPresent(Object key)` |
| --- | --- | --- |
| Phạm vi | Một key | Một key |
| Kiểu trả về | `void` | `boolean` |
| Báo cáo entry đã tồn tại? | Không | Có nếu provider xác định được |
| Thời điểm xóa | Có thể immediate, delayed hoặc asynchronous | API kỳ vọng immediate visibility |
| Dùng với transaction-aware decorator | Có thể defer đến **after-commit** | Immediate, **không defer** đến after-commit |
| Khi key không tồn tại | Không có giá trị trả về | Thường trả `false` |
| Khi provider không biết prior presence | Không áp dụng | Có thể trả `false` |
| Phù hợp | Invalidation thường xuyên, không cần phản hồi presence | Immediate eviction và biết prior presence khi provider hỗ trợ |

**Tên `evictIfPresent` không mang nghĩa rằng `evict` sẽ xóa key dù key vắng mặt, còn phương thức kia chỉ xóa khi key tồn tại**. Cả hai đều nhắm tới mapping nếu mapping có mặt. Phần “IfPresent” thể hiện thêm contract boolean.

## 2. Hiểu đúng true và false của evictIfPresent

Định nghĩa Spring Cache API:

~~~java
void evict(Object key);
default boolean evictIfPresent(Object key);
~~~

Với `evictIfPresent`:

- Trả **`true`** khi cache implementation **biết rằng có mapping** cho key trước khi xóa.
- Trả **`false`** khi implementation biết không có mapping **hoặc không xác định được** trạng thái tồn tại trước đó.

Vì vậy, không dùng kết quả `false` để khẳng định bản ghi nghiệp vụ không tồn tại trong database, hoặc khẳng định trước đó chưa từng có entry cache.

Ví dụ:

~~~java
public boolean removeKnownCacheEntry(Cache cache, String isbn) {
    return cache.evictIfPresent(isbn);
}
~~~

Đây là method Java minh họa cần import `org.springframework.cache.Cache`. Boolean nên được hiểu là **known prior cache presence**, không phải một kiểm tra tình trạng bản ghi ở kho dữ liệu gốc.

### Vì sao trả false dù key từng có entry?

Từ Spring Framework **5.2**, `evictIfPresent` là một **default method** trên interface `Cache`. Default implementation ủy quyền cho `evict(key)`, sau đó trả `false` do **không xác định được prior presence**.

Các provider/decorator được khuyến khích override method này để có khả năng xóa tức thời và báo cáo trạng thái chính xác. `ConcurrentMapCache` của Spring có implementation riêng và được dùng trong ví dụ sau.

**Hệ quả thiết kế:** contract API có mục tiêu immediate eviction, nhưng nếu một provider tự viết chỉ sử dụng default implementation, caller không thể suy ra bảo đảm immediate mạnh hơn `evict`. Trước khi dựa vào boolean hoặc đặc tính thời gian, hãy kiểm tra class triển khai `Cache` thật sự, không chỉ nhìn chữ ký interface.

## 3. Immediate visibility không giống tính nhất quán toàn hệ thống

`evictIfPresent(key)` mô tả kỳ vọng **key không còn nhìn thấy trong các lookup tiếp theo của cache implementation**. Điều đó không đồng nghĩa:

- Database đã commit bản cập nhật.
- Không có request khác đang đọc bản cũ.
- Không có writer concurrent put lại key ngay sau eviction.
- Các node sử dụng cache cục bộ riêng đã nhận thông điệp invalidation.
- Mọi bản sao trên nhiều tầng cache đã đồng bộ ngay tức thời.

Ví dụ race:

~~~text
Reader R1 đọc "old" từ database (chưa put cache)
                   |
Writer W cập nhật database thành "new"
                   |
Writer W evictIfPresent("ISBN-A")
                   |
Reader R1 put("ISBN-A", "old")
                   |
Lần đọc sau lại gặp stale cache
~~~

Eviction tức thì giải quyết **trạng thái mapping tại thời điểm gọi**, nhưng không tạo transaction nguyên tử giữa cache và database. Khi yêu cầu nhất quán cao, cân nhắc versioned key, transaction coordination, TTL, event invalidation và cơ chế chống ghi lại giá trị cũ.

## 4. TransactionAwareCacheDecorator làm hai API khác nhau rõ rệt

`TransactionAwareCacheDecorator` của Spring có thể đồng bộ các thao tác `put`, `evict`, `clear` với **Spring-managed transaction**. Khi có transaction phù hợp, thao tác thực tế được thực hiện trong pha **after-commit** sau một commit thành công; khi không có transaction, chúng thường chạy ngay.

### Gọi evict trong transaction

~~~text
Transaction bắt đầu
        |
Cập nhật row trong database (chưa commit)
        |
cache.evict("ISBN-A")
        |
Transaction-aware decorator lên lịch eviction
        |
Commit thành công
        |
After-commit: thực sự xóa entry ISBN-A
~~~

Ở giữa lần gọi `evict` và commit, cache có thể **vẫn nhìn thấy mapping cũ**. Đây không nhất thiết là lỗi; việc đợi commit có thể ngăn xóa cache vô ích khi transaction rollback.

### Gọi evictIfPresent trong transaction

~~~text
Transaction bắt đầu
        |
Cập nhật row trong database (chưa commit)
        |
cache.evictIfPresent("ISBN-A")
        |
Decorator gọi immediate eviction ngay
        |
Reader khác có thể miss cache trước khi DB commit
        |
Commit hoặc rollback xảy ra sau đó
~~~

Spring nêu rõ thao tác immediate như `evictIfPresent` **không thể trì hoãn tới after-commit** trên decorator này. Cần cẩn trọng: cache bị xóa trước khi transaction thật sự thành công có thể dẫn tới reader nạp lại dữ liệu DB cũ; nếu transaction rollback thì eviction đã xảy ra.

**Khuyến nghị:** đừng đổi `evict` thành `evictIfPresent` trong một transaction chỉ vì muốn nhận boolean. Nếu điều cần thiết là invalidation *sau commit*, hãy thiết kế đúng transaction boundary, cache manager và hành vi provider. Nếu yêu cầu là thấy key biến mất ngay lập tức thì chấp nhận và xử lý rủi ro nhất quán tương ứng.

Lưu ý: transaction awareness là một lớp trang trí cụ thể. Cache backend riêng không đương nhiên có cùng chính sách; thêm `@Transactional` vào bất kỳ method nào cũng không tự biến mọi cache thành transaction-aware.

## 5. Cache miss khác với cached null

Khi kiểm tra key sau eviction, phương thức `Cache.get(key)` (dạng trả `ValueWrapper`) là công cụ phù hợp.

~~~java
Cache.ValueWrapper wrapper = cache.get("ISBN-A");
boolean entryVisible = wrapper != null;
~~~

Đoạn này minh họa code bên trong một method có biến `cache`. Spring phân biệt:

| Kết quả | Diễn giải |
| --- | --- |
| `cache.get(key) == null` | **Cache miss**, không nhìn thấy mapping |
| `cache.get(key) != null` và `wrapper.get() == null` | Có mapping nhưng **giá trị logic là null** |
| `wrapper.get()` khác null | Có mapping với giá trị logic |

Vì một số cache backend cho phép cached null, kết quả `cache.get(key, String.class) == null` **không đủ** để kết luận cache miss. Ví dụ phần 6 kiểm chứng `evictIfPresent` vẫn trả true khi entry có cached-null value và provider biết mapping tồn tại.

## 6. Ví dụ Java 17+ đầy đủ: kiểm tra cả hai API

Ví dụ dùng **Java 17**, **Spring Framework 6.2.14** và local `ConcurrentMapCacheManager`. Trong backend này, cả `evict` lẫn `evictIfPresent` đều xóa entry ngay. Sự khác nhau quan sát rõ nhất là **giá trị trả về** của `evictIfPresent`.

Tạo hai tệp đúng đường dẫn sau.

**Tệp `build.gradle`**

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.EvictMethodsDemo'
}
~~~

**Tệp `src/main/java/demo/EvictMethodsDemo.java`**

~~~java
package demo;

import java.util.Objects;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;

public class EvictMethodsDemo {

    public static void main(String[] args) {
        CacheManager manager = new ConcurrentMapCacheManager("books");
        Cache cache = Objects.requireNonNull(manager.getCache("books"));

        cache.put("A", "first-edition");
        cache.put("B", "stable-edition");

        System.out.println("A initially present: " + (cache.get("A") != null));
        System.out.println("B initially present: " + (cache.get("B") != null));

        cache.evict("A");
        System.out.println("A after evict: " + (cache.get("A") != null));
        System.out.println("B after evict: " + (cache.get("B") != null));

        cache.put("A", "second-edition");
        boolean first = cache.evictIfPresent("A");
        System.out.println("first evictIfPresent: " + first);
        System.out.println("A after evictIfPresent: " +
                (cache.get("A") != null));

        boolean second = cache.evictIfPresent("A");
        System.out.println("second evictIfPresent: " + second);

        // ConcurrentMapCacheManager mặc định cho phép cached null.
        cache.put("EMPTY", null);
        Cache.ValueWrapper nullEntry = cache.get("EMPTY");
        System.out.println("cached null entry exists: " +
                (nullEntry != null));
        System.out.println("cached null value: " +
                Objects.requireNonNull(nullEntry).get());

        System.out.println("evict cached null: " +
                cache.evictIfPresent("EMPTY"));
        System.out.println("null entry after eviction: " +
                (cache.get("EMPTY") != null));

        cache.evict("MISSING");
        System.out.println("B final value: " +
                Objects.requireNonNull(cache.get("B")).get());
    }
}
~~~

Chạy trong thư mục chứa `build.gradle`, với JDK 17+ và Gradle tương thích:

~~~bash
gradle run --quiet
~~~

**Stdout dự kiến của ứng dụng** (không tính log của Gradle):

~~~text
A initially present: true
B initially present: true
A after evict: false
B after evict: true
first evictIfPresent: true
A after evictIfPresent: false
second evictIfPresent: false
cached null entry exists: true
cached null value: null
evict cached null: true
null entry after eviction: false
B final value: stable-edition
~~~

### Phân tích kết quả

1. Hai `put` đầu tiên tạo entry A và B. Vì `Cache.get(key)` trả wrapper, hai dòng đầu in true.
2. `cache.evict("A")` xóa A trong local `ConcurrentMapCache`; B vẫn có. Lời gọi `evict` không báo số lượng mapping xóa.
3. Sau khi put lại A, `evictIfPresent("A")` lần thứ nhất trả true (biết có mapping), sau đó A không còn. Lần thứ hai trả false vì lúc đó A vắng mặt.
4. `cache.put("EMPTY", null)` tạo **một entry chứa giá trị null logic** thông qua null holder nội bộ; `Cache.get("EMPTY")` trả wrapper khác null.
5. `evictIfPresent("EMPTY")` trả true vì entry trước đó tồn tại, dù nội dung logic bằng null.
6. Xóa key `MISSING` bằng `evict` không ảnh hưởng B; giá trị cuối của B vẫn là `stable-edition`.

**Giới hạn demo:** đây là một JVM không dùng transaction decorator. Không lấy output để kết luận mọi remote provider đều trả boolean và có mức immediate visibility tương tự. Output được suy luận từ code và hành vi API trong cấu hình này; khi triển khai thật nên chạy test với đúng cache provider.

Chương trình chỉ gọi trực tiếp `Cache`. Nó **không cần `@EnableCaching`** hoặc Spring AOP proxy để các lời gọi `cache.evict` và `cache.evictIfPresent` hoạt động.

## 7. Nên sử dụng evict hay evictIfPresent?

### Ưu tiên `evict(key)` khi

- Chỉ cần ra lệnh xóa key, không có logic phụ thuộc vào prior presence.
- Muốn kết hợp với transaction-aware cache để thao tác có thể đợi đến after-commit.
- Cache API là phần của workflow cập nhật thông thường, nơi độ đúng nghiệp vụ không dựa vào giá trị boolean.
- Chấp nhận semantics của backend có khả năng bất đồng bộ, miễn chính sách TTL và consistency đã được xác định.

Ví dụ:

~~~java
public void invalidate(Cache cache, String isbn) {
    cache.evict(isbn);
}
~~~

Method này không chứng minh cache từng có key. Nó chỉ yêu cầu backend xử lý invalidation.

### Ưu tiên `evictIfPresent(key)` khi

- Cần contract **immediate visibility** và đã kiểm tra provider triển khai tương ứng.
- Muốn biết một mapping được **xác nhận đã tồn tại trước khi gọi**, chẳng hạn để đo metric theo provider.
- Chấp nhận rằng invocation này có thể không đợi transaction commit.
- Không dùng `false` như kết luận chắc chắn về database hoặc về prior presence với custom backend.

Ví dụ:

~~~java
public boolean invalidateImmediately(Cache cache, String isbn) {
    return cache.evictIfPresent(isbn);
}
~~~

**Chú ý:** boolean ở đây là **known prior presence**, không phải xác nhận bản ghi ở nguồn đã bị xóa hoặc mọi instance cache đã nhất quán.

| Tình huống | Lựa chọn cần cân nhắc |
| --- | --- |
| Update DB, cache transaction-aware nên xóa sau commit | `evict` |
| Cần key biến mất ngay trong cache hiện tại | `evictIfPresent` trên backend hỗ trợ |
| Muốn phân biệt hit/miss trước invalidation | `evictIfPresent`, nhưng tôn trọng giá trị false = absent/unknown |
| Code cũ dùng custom `Cache` chưa override default method | Kiểm chứng implementation trước khi dựa vào boolean |
| Cần invalidation nhiều key/region | Thiết kế nhiều key hoặc dùng API toàn vùng, không ép one-key API |

## 8. Quan hệ với @CacheEvict

`@CacheEvict` là annotation khai báo trên phương thức nghiệp vụ; `Cache.evict` và `Cache.evictIfPresent` là lời gọi Java trực tiếp. Hai lớp API này có liên hệ nhưng **không đồng nhất**.

~~~java
@CacheEvict(cacheNames = "books", key = "#p0")
public void renameBook(String isbn, String newTitle) {
    repository.updateTitle(isbn, newTitle);
}
~~~

Đây là ví dụ tích hợp, cần repository thật, bean được Spring quản lý và caching infrastructure. Với `beforeInvocation = false` mặc định, Spring evict sau khi method kết thúc thành công; nếu ném exception thì không thực hiện eviction mặc định.

~~~java
@CacheEvict(
    cacheNames = "books",
    key = "#p0",
    beforeInvocation = true
)
public void renameBook(String isbn, String newTitle) {
    repository.updateTitle(isbn, newTitle);
}
~~~

Ở chế độ trước invocation, Spring thực hiện eviction trước khi gọi method, ngay cả khi phần thân sau đó ném exception. Trong caching interceptor, nhánh immediate của `AbstractCacheInvoker` sử dụng `evictIfPresent`, còn nhánh thông thường sử dụng `evict`.

**Không hiểu nhầm:** annotation không trả boolean từ `evictIfPresent` cho method caller. Thuộc tính `beforeInvocation` chủ yếu thể hiện lựa chọn **evict trước hay sau logic nghiệp vụ**, không phải cờ “có trả true/false hay không”.

Nếu ứng dụng cập nhật database trong transaction, phải cân nhắc race và commit boundary trước khi đổi sang evict trước invocation. Cùng một kiểu API immediate không mặc nhiên tốt hơn kiểu deferred khi nhiệm vụ là bảo toàn consistency.

## 9. Không nhầm với xóa toàn vùng

Hai phương thức đang học đều xóa **một entry key**. Spring còn có cặp phương thức áp dụng toàn vùng:

| Một key | Toàn vùng cache | Khác biệt chính |
| --- | --- | --- |
| `evict(key)` | `clear()` | Có thể có semantics deferred/asynchronous |
| `evictIfPresent(key)` | `invalidate()` | Hướng tới immediate visibility, có thông tin boolean |

Nếu chỉ cập nhật một sản phẩm, xóa toàn vùng có thể khiến mọi key phải nạp lại. Chỉ dùng `clear` hoặc `invalidate` khi thật sự cần làm mất hiệu lực **mọi entry** của vùng cache ấy.

## 10. Lỗi thường gặp và cách kiểm tra

| Sai lầm | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Cho rằng `evict` luôn xóa ngay | Decorator deferred vẫn cho thấy entry cũ trước commit | Kiểm tra backend/transaction-aware decorator |
| Cho rằng false của `evictIfPresent` chứng minh chưa có key | Default implementation có thể trả false vì unknown | Phân biệt known presence và absent/unknown |
| Dùng `evictIfPresent` trong transaction nhưng muốn after-commit | Cache bị xóa trước commit, có nguy cơ nạp lại bản cũ | Dùng semantics phù hợp transaction boundary |
| Dùng giá trị null từ `Cache.get(key, type)` để kết luận miss | Nhầm cached null với không có entry | Kiểm tra `Cache.ValueWrapper` |
| Xóa một key nhưng sau đó vẫn stale | Reader concurrent put lại dữ liệu cũ; sai key hoặc sai manager | Xác minh key, thời điểm put/evict, provider và reader |
| Dùng API toàn vùng để xóa một SKU | Làm mất entry không liên quan | Dùng API một-key |
| Gọi `@CacheEvict` từ method khác trên chính cùng bean | Self-invocation bỏ qua proxy cache | Gọi qua Spring bean/proxy hợp lệ |
| Dùng true làm bằng chứng DB có bản ghi | Cache entry khác dữ liệu nghiệp vụ | Truy vấn nguồn để kiểm tra tồn tại |

Khi gỡ lỗi, xác nhận theo trình tự: **đúng cache instance → đúng key → implementation cụ thể → có transaction decorator không → trạng thái ValueWrapper sau eviction → có writer concurrent nào đưa key lại không**.

## 11. Bài tập tự kiểm tra

**Bài 1.** `cache.evict("A")` có trả true khi A từng tồn tại không?

**Đáp án:** Không. Phương thức trả `void`.

**Bài 2.** `cache.evictIfPresent("A")` trả false có nghĩa chắc chắn cache chưa từng có A?

**Đáp án:** Không. Có thể key vắng mặt hoặc provider **không biết** prior presence.

**Bài 3.** Cache có mapping `"N"` với giá trị logic null. `evictIfPresent("N")` có thể trả true không?

**Đáp án:** Có, nếu provider biết mapping tồn tại, như `ConcurrentMapCache` trong ví dụ.

**Bài 4.** Transaction-aware decorator đang defer `evict` đến after-commit. Đổi sang `evictIfPresent` có giữ được after-commit không?

**Đáp án:** Không. Đây là API immediate, không thể deferred theo decorator này.

**Bài 5.** Vì sao xóa ngay vẫn có thể dẫn tới stale data?

**Đáp án:** Reader khác có thể load bản cũ trước database commit, sau đó put lại key vào cache. Eviction không tạo tính nguyên tử giữa hai hệ thống.

## 12. Tóm tắt và tài liệu chính thức

- `evict(key)` = xóa một mapping, trả **void**, có thể bị trì hoãn.
- `evictIfPresent(key)` = xóa một mapping với kỳ vọng **ngay lập tức**, trả boolean về *known prior presence*.
- **`false` có thể là vắng mặt hoặc không xác định được**; default method có thể ủy quyền `evict` và trả false.
- Transaction-aware decorator có thể defer `evict` sau commit; không defer `evictIfPresent`.
- Cache miss khác cached null; kiểm tra bằng `Cache.ValueWrapper`.
- Immediate eviction không loại trừ race và không thay thế việc đồng bộ với database.

**Tài liệu Spring:**

- [Spring 6.2.14 – Cache API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/Cache.html)
- [Spring 6.2.14 – ConcurrentMapCache](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html)
- [Spring 6.2.14 – TransactionAwareCacheDecorator](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html)
- [Spring 6.2.14 – AbstractCacheInvoker](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/interceptor/AbstractCacheInvoker.html)
- [Spring Framework 6.2 – Annotation-based Caching](https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html)
