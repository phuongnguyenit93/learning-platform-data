# Spring Cache: `condition` và kiểm tra trước khi áp dụng cache

## 1. Mục tiêu và tình huống sử dụng

Một phương thức có `@Cacheable` không nhất thiết nên sử dụng cache trong **mọi lời gọi**. Ví dụ: dữ liệu ít thay đổi của một mã sản phẩm có thể được cache, nhưng dữ liệu truy vấn đặc biệt, request thử nghiệm, hoặc trường hợp yêu cầu tính toán mới cần đi thẳng vào phương thức.

Spring Cache hỗ trợ thuộc tính `condition` trên các cache annotation. Đây là một biểu thức **Spring Expression Language (SpEL) trả về boolean**, dùng để quyết định có áp dụng **cache operation cho lời gọi hiện tại** hay không.

Sau bài này, bạn cần hiểu được:
- `condition` được đánh giá **trước khi tra cache** trong ngữ cảnh `@Cacheable`; phân biệt tác động khi điều kiện đúng/sai.
- Truy cập tham số qua `#p0`, `#p1`, `#root.args`; kiểm tra `null` an toàn và viết biểu thức dễ bảo trì.
- Phân biệt `condition` (kiểm tra theo đầu vào) với `unless` (có thể từ chối ghi kết quả sau khi phương thức chạy).
- Hiểu cách `condition` tham gia vào `@CachePut` và `@CacheEvict`; tránh dùng điều kiện như cơ chế phân quyền.
- Quan sát cache hit/miss bằng ví dụ Java 17+ chạy qua Spring proxy.

Tình huống xuyên suốt: chỉ các mã bắt đầu bằng `HOT-` mới được đọc/ghi vào cache `items`. Các mã `COLD-` và tham số `null` vẫn đi qua nghiệp vụ mỗi lần nhưng không dùng cache.

## 2. `@Cacheable(condition = "...")` xử lý một lời gọi như thế nào?

Xét đoạn cấu hình trong một Spring-managed service:

```java
@Cacheable(
    cacheNames = "items",
    key = "#p0",
    condition = "#p0 != null && #p0.startsWith('HOT-')"
)
public String find(String code) {
    return loadFromSource(code);
}
```

Đây là **đoạn minh họa một method**, chưa phải chương trình độc lập. `loadFromSource` biểu diễn công việc cần chạy khi cache không được sử dụng hoặc khi cache miss.

Cách Spring Cache xử lý trong chế độ proxy thông thường:

```text
Client gọi find(code) thông qua Spring proxy
           |
           v
Đánh giá condition trên đầu vào hiện tại
           |
      +----+-----------------------+
      |                            |
   false                          true
      |                            |
      v                            v
Bỏ qua cache operation       Chọn cache và tạo key
      |                            |
      v                            v
Gọi method trực tiếp         Kiểm tra entry với key
      |                            |
      v                       +----+----------+
Trả kết quả                  hit             miss
                               |               |
                               v               v
                         Trả value cũ      Chạy method
                                               |
                                               v
                                        Cache kết quả hợp lệ
                                        (nếu không bị unless veto)
                                               |
                                               v
                                            Trả value
```

**Nếu `condition` trả `false`:** Spring bỏ qua việc tra/ghi cache **cho operation đó**. Phương thức vẫn thực thi khi được gọi; nếu gọi ba lần cùng tham số không đạt điều kiện, body có thể chạy cả ba lần. Đây **không phải** tính năng ngăn phương thức chạy hoặc cơ chế validation.

**Nếu `condition` trả `true`:** thao tác `@Cacheable` được áp dụng bình thường. Key đã tồn tại và entry còn hợp lệ thì Spring trả dữ liệu cache, có thể không gọi method; nếu cache miss thì gọi method rồi lưu kết quả theo chính sách.

Biểu thức được xét cho **từng lời gọi**. Nếu trước đây một key đã được cache, sau đó điều kiện ở request hiện tại thành `false` thì request ấy **không đọc cache cũ**; tuy nhiên entry cũ **không bị xóa** chỉ vì condition sai. Khi condition trở lại `true`, entry đó vẫn có thể được sử dụng nếu chưa hết hạn hoặc chưa bị evict.

| `condition` | Trạng thái entry | `@Cacheable` có đọc cache? | Body có chạy? | Có ghi kết quả vào cache? |
| --- | --- | --- | --- | --- |
| `false` | Có hoặc không | Không | Có | Không |
| `true` | Hit | Có | Không | Không cần ghi mới |
| `true` | Miss | Có | Có | Có, trừ khi bị `unless`/provider ngăn |
| Lỗi đánh giá SpEL | Chưa xác định | Không có kết quả cache bình thường | Không nên dự đoán | Thường phát sinh lỗi xử lý cache |

Bảng giả định method trả kết quả đồng bộ và không có các operation cache khác cùng tác động. Với async/reactive, thời điểm hoàn tất và lưu kết quả có quy tắc riêng của phiên bản Spring và cache provider.

## 3. Viết điều kiện SpEL đúng và an toàn

### 3.1. Cú pháp và biến sẵn có

Các giá trị được sử dụng phổ biến:

| Biểu thức | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `#p0` / `#a0` | Đối số thứ nhất (index 0) | `#p0 != null` |
| `#p1` / `#a1` | Đối số thứ hai (index 1) | `#p1 > 0` |
| `#root.args[0]` | Đối số đầu tiên trong mảng args | `#root.args[0] == 'VN'` |
| `#root.methodName` | Tên phương thức đang gọi | `#root.methodName == 'find'` |
| `#root.targetClass` | Class của target | Dùng khi cần đọc metadata |
| `#code` | Đối số theo tên, nếu có metadata tên tham số | `#code.startsWith('HOT-')` |

Dùng `#p0`/`#p1` là cách ổn định khi không chắc dự án đã biên dịch với flag `-parameters` để truy cập tên tham số như `#code`. Các tham số đánh số từ **0**, còn ký tự `#` là cú pháp tham chiếu biến của SpEL.

Một số mẫu thực tế:

```java
@Cacheable(cacheNames = "products", condition = "#p0 > 0")
public Product find(long id) { /* truy vấn */ return null; }

@Cacheable(cacheNames = "prices",
           condition = "#p0 != null && #p1 > 0")
public Price price(String region, long productId) {
    /* tính giá */ return null;
}

@Cacheable(cacheNames = "documents",
           condition = "#p0 != null && #p0.startsWith('PUB-')")
public Document findDocument(String documentCode) {
    /* truy vấn */ return null;
}
```

Đây là các **đoạn chữ ký minh họa**, không tự biên dịch riêng vì thiếu lớp kiểu dữ liệu và phần thân nghiệp vụ. `condition` luôn được đặt trong **chuỗi Java** bên trong annotation, nhưng bản thân biểu thức SpEL dùng các toán tử `&&`, `||`, `!`, `==`, `!=` và phép gọi method/property theo cú pháp SpEL.

### 3.2. Kiểm tra null và short-circuit

Ví dụ cần kiểm tra mã chỉ bắt đầu bằng `HOT-`:

```java
condition = "#p0 != null && #p0.startsWith('HOT-')"
```

Vế phải chỉ nên được đánh giá khi `#p0` không `null` nhờ cơ chế short-circuit của toán tử AND. Nếu viết `#p0.startsWith('HOT-')` khi giá trị thực tế là `null`, thao tác có thể thất bại do lỗi đánh giá biểu thức trước khi phương thức nghiệp vụ được gọi.

Ưu tiên điều kiện ngắn, thuần từ dữ liệu đầu vào và **không có side effect**. Ví dụ không nên gọi service ngoài, sửa database, tăng biến đếm hoặc đọc nguồn dữ liệu mạng bên trong SpEL. Một điều kiện vừa tốn thời gian vừa có side effect sẽ khiến đường đi của mọi cache hit trở nên khó đoán và khó kiểm thử.

### 3.3. `#result` không thuộc dữ liệu đầu vào của `@Cacheable.condition`

Trong `@Cacheable`, `condition` được kiểm tra trước khi có kết quả method, nên **không thể dùng `#result` để quyết định có tra cache hay không**. Nếu muốn xét kích thước, trạng thái hoặc nội dung kết quả **sau khi** phương thức chạy, dùng `unless`.

Sai về thời điểm:

```java
// Sai ý tưởng: condition chưa có kết quả method để kiểm tra.
@Cacheable(cacheNames = "products", condition = "#result != null")
public Product find(String id) { /* ... */ return null; }
```

Hợp lý hơn:

```java
// condition quyết định áp dụng cache cho mã hợp lệ.
// unless bỏ qua bước ghi khi kết quả không có dữ liệu.
@Cacheable(
    cacheNames = "products",
    condition = "#p0 != null && !#p0.isBlank()",
    unless = "#result == null"
)
public Product find(String id) { /* ... */ return null; }
```

Hai đoạn trên mang tính minh họa; `Product` và nghiệp vụ cần triển khai riêng. Lưu ý `unless` không hủy một cache hit đã xảy ra: nếu key có entry hợp lệ, `@Cacheable` có thể trả kết quả từ cache ngay và không chạy body để đánh giá kết quả mới.

## 4. Ví dụ đầy đủ chạy được: quan sát condition trước khi cache lookup

Chương trình dùng **Java 17+**, Spring Framework Cache thông qua các thư viện của **Spring Boot 3.3.x**, và `ConcurrentMapCacheManager` để chạy trong bộ nhớ, không cần Redis hay database. Các kết quả được tạo bằng bộ đếm nên ta nhìn thấy chính xác khi nào body chạy.

Tạo cấu trúc:

```text
cache-condition-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/cache/ConditionDemo.java
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'cache-condition-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}

application {
    mainClass = 'demo.cache.ConditionDemo'
}
```

Tệp `src/main/java/demo/cache/ConditionDemo.java` (đầy đủ):

```java
package demo.cache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ConditionDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class CacheConfig {
        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("items");
        }

        @Bean
        ItemService itemService() {
            return new ItemService();
        }
    }

    public static class ItemService {
        private final AtomicInteger executions = new AtomicInteger();

        @Cacheable(
            cacheNames = "items",
            key = "#p0",
            condition = "#p0 != null && #p0.startsWith('HOT-')"
        )
        public String find(String code) {
            return code + "-load-" + executions.incrementAndGet();
        }

        public int executionCount() {
            return executions.get();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(CacheConfig.class)) {
            // Quan trọng: lấy bean qua Spring context để đi qua proxy.
            ItemService service = context.getBean(ItemService.class);

            System.out.println(service.find("HOT-1"));
            System.out.println(service.find("HOT-1"));

            System.out.println(service.find("COLD-1"));
            System.out.println(service.find("COLD-1"));

            System.out.println(service.find("HOT-2"));
            System.out.println(service.find("HOT-2"));

            System.out.println(service.find(null));
            System.out.println(service.find(null));

            System.out.println("executions=" + service.executionCount());

            Cache cache = context.getBean(CacheManager.class).getCache("items");
            if (cache == null) {
                throw new IllegalStateException("Missing cache: items");
            }
            System.out.println("cacheHasHOT=" + (cache.get("HOT-1") != null));
            System.out.println("cacheHasCOLD=" + (cache.get("COLD-1") != null));
        }
    }
}
```

Chạy trong thư mục `cache-condition-demo`:

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper, dùng `./gradlew run --quiet` (Windows: `gradlew.bat run --quiet`). Đầu ra do chương trình in ra, không tính log của framework/build tool:

```text
HOT-1-load-1
HOT-1-load-1
COLD-1-load-2
COLD-1-load-3
HOT-2-load-4
HOT-2-load-4
null-load-5
null-load-6
executions=6
cacheHasHOT=true
cacheHasCOLD=false
```

Đối chiếu chi tiết:

1. `find("HOT-1")`: biểu thức đúng; lookup key `"HOT-1"` bị miss, chạy method lần 1 và ghi kết quả.
2. Lặp lại `find("HOT-1")`: condition vẫn đúng; có cache hit nên trả `HOT-1-load-1`, bộ đếm không tăng.
3. `find("COLD-1")` hai lần: condition sai do prefix khác `HOT-`; **không lookup/put**, method chạy ở lần 2 và 3.
4. `find("HOT-2")` hai lần: lần đầu miss, lần sau hit; method chạy thêm đúng một lần (lần 4).
5. `find(null)` hai lần: điều kiện `#p0 != null` sai, không cố gọi `startsWith` và không đưa null làm key; method vẫn chạy hai lần (lần 5 và 6).
6. Kiểm tra trực tiếp cache manager xác nhận chỉ nhóm HOT được ghi: `cacheHasHOT=true`, `cacheHasCOLD=false`.

**Vì sao ví dụ này tái hiện được cache?** `@EnableCaching` được đặt trên cấu hình Spring, bean `ItemService` được tạo và inject qua context, và các lời gọi xuất phát từ class `ConditionDemo` nên đi qua Spring proxy. Nếu thay bằng `new ItemService().find(...)`, caching annotation không được kích hoạt. Tương tự, tự gọi `this.find(...)` từ một method cùng service sẽ bỏ qua proxy trong chế độ mặc định.

`ConcurrentMapCacheManager` là lựa chọn để học tập; đối với Redis/Caffeine cần xét thêm TTL, key serialization, phân tán, quota và chính sách cache của provider. `condition` không tự đặt TTL hay tạo cache store.

## 5. So sánh `condition` với `unless` và `key`

Cùng một cache operation có ba câu hỏi riêng:

| Cấu hình | Câu hỏi | Thời điểm với `@Cacheable` | Có thể dùng `#result`? |
| --- | --- | --- | --- |
| `condition` | Có sử dụng cache cho lời gọi này không? | Trước cache lookup/method | **Không** |
| `key` hoặc `keyGenerator` | Entry nào trong cache? | Khi thao tác cache cần một key | Không đối với key của `@Cacheable` thông thường |
| `unless` | Có từ chối lưu kết quả vừa tính xong không? | Sau khi method đã chạy khi miss | **Có** |

Ví dụ áp dụng cả hai điều kiện:

```java
@Cacheable(
    cacheNames = "searchResults",
    key = "#p0",
    condition = "#p0 != null && #p0.length() <= 50",
    unless = "#result == null || #result.isEmpty()"
)
public String search(String query) {
    return searchFromDatabase(query);
}
```

Đây là method minh họa với `searchFromDatabase` do ứng dụng triển khai.

- Query quá dài hoặc null: `condition=false`, không dùng cache, method vẫn chạy.
- Query hợp lệ và cache miss: method chạy; nếu kết quả null hoặc rỗng, `unless=true` ngăn ghi kết quả.
- Query hợp lệ và cache hit: dùng entry sẵn có, không chạy method để tính một kết quả mới; `unless` không thay thế cơ chế invalidation.

Đừng nhầm **`condition=false`** với **“không lưu sau khi chạy”** theo mọi nghĩa: trong trường hợp `@Cacheable` nó còn **bỏ qua bước đọc cache**. Ngược lại, `unless=true` chỉ từ chối **cache put của kết quả hiện tại**, không có tác dụng tự làm mất hiệu lực entry đã có trước đó.

### Tại sao không dùng kết quả cho condition?

Để biết kết quả, method phải chạy. Nhưng `@Cacheable` cần quyết định có lookup trước khi chạy method để có cơ hội bỏ qua tính toán. Do đó input được dùng làm điều kiện trước, kết quả được xét ở bước sau bằng `unless`. Những thông tin chưa có trước khi thực thi, chẳng hạn tổng số dòng trả về từ truy vấn, thường thích hợp với `unless` hơn.

## 6. `condition` trên `@CachePut` và `@CacheEvict`

Cả hai annotation cũng hỗ trợ `condition`, nhưng cần tách **cache operation** và **việc chạy nghiệp vụ**:

### 6.1. `@CachePut`

```java
@CachePut(
    cacheNames = "profiles",
    key = "#p0.id",
    condition = "#p0 != null && #p0.cacheEligible"
)
public Profile save(Profile input) {
    return repository.save(input);
}
```

Đây là đoạn minh họa cần class `Profile` và `repository` thực tế. `@CachePut` có mục đích cập nhật cache từ **kết quả method**, không dùng cache để bỏ qua method. Khi điều kiện sai, phương thức `save` vẫn được thực thi; cache put được bỏ qua. Khi điều kiện đúng, phương thức vẫn chạy và Spring có thể ghi kết quả vào cache theo operation. Biểu thức `condition` trong ví dụ truy cập dữ liệu đầu vào, nên không cần dựa vào `#result`.

### 6.2. `@CacheEvict`

```java
@CacheEvict(
    cacheNames = "profiles",
    key = "#p0",
    condition = "#p1",
    beforeInvocation = false
)
public void updateProfile(String id, boolean changed) {
    // Ghi dữ liệu nguồn, nếu có thay đổi.
}
```

Ví dụ này có ý nghĩa khi `changed` biểu diễn điều kiện nghiệp vụ **được bảo đảm đúng** ở đầu vào, và các phép cập nhật gây thay đổi giá trị cache luôn đánh dấu đúng. Với `@CacheEvict`, condition kiểm soát **có evict hay không**, không bỏ qua phương thức `updateProfile`.

- `beforeInvocation=false` (mặc định): evict khi thao tác phù hợp và phương thức kết thúc thành công.
- `beforeInvocation=true`: thao tác evict được thực hiện **trước** khi gọi method nếu điều kiện cho phép, kể cả khi method sau đó ném exception.
- `allEntries=true` xóa toàn bộ entry của cache được chọn và không cần key đơn lẻ; condition vẫn có thể quyết định có thực hiện thao tác xóa này hay không.

**Lưu ý nhất quán:** Nếu update database mà quên evict vì điều kiện sai, một entry cũ có thể được đọc lại. Điều kiện ở cache annotation không tự theo dõi mọi thay đổi dữ liệu nguồn hoặc thay thế chiến lược invalidate.

## 7. Thiết kế condition cho đúng nhu cầu

### 7.1. Ưu tiên tiêu chí ổn định, không có side effect

Các tiêu chí phù hợp thường liên quan trực tiếp tới tham số:
- ID dương/định dạng hợp lệ: `#p0 > 0`.
- Phân loại request có thể cache: `#p1 == 'STANDARD'`.
- Độ dài truy vấn trong ngưỡng phù hợp: `#p0 != null && #p0.length() <= 50`.
- Input không rỗng: `#p0 != null && !#p0.isBlank()`.

Nếu mọi điều kiện đều liên quan tới cùng một nghiệp vụ nhiều nơi, nên đặt quy tắc rõ ràng vào một thành phần test được, hoặc thiết kế lại API thành các method khác nhau. Tránh nhồi logic nghiệp vụ phức tạp và gọi hàm có side effect vào biểu thức SpEL.

### 7.2. Không dùng condition như hệ thống phân quyền

Việc kiểm tra có dùng cache **không xác định người dùng có quyền xem dữ liệu hay không**. Trên cache hit, body method có thể không chạy; nếu toàn bộ authorization chỉ nằm trong body, kết quả có thể được trả từ cache trước khi kiểm tra quyền.

Khi dữ liệu phụ thuộc tenant, user, scope hoặc region, phải đảm bảo cả:
- Xác thực/phân quyền được thực hiện ở lớp phù hợp **trước khi trả dữ liệu**, kể cả đường cache hit.
- Cache key và/hoặc cache region phân biệt đúng phạm vi dữ liệu. Hai user không được chia sẻ một key cho dữ liệu riêng tư.
- Khi quyền hoặc dữ liệu thay đổi, cần có chiến lược evict/TTL rõ ràng.

Ví dụ `condition="#p0.role == 'ADMIN'"` không phải kiểm tra bảo mật đáng tin cậy nếu `role` là input do client tự cung cấp. Quyết định quyền phải đến từ cơ chế security đã được xác thực.

### 7.3. Condition thay đổi theo thời gian không tự xóa entry cũ

Giả sử ban đầu chính sách cho phép cache; sau đó feature flag tắt để buộc truy vấn nguồn. Những request lúc cờ tắt bỏ qua cache, nhưng entry đã tạo trước đó vẫn tồn tại. Khi cờ bật lại, dữ liệu cũ có thể trở thành cache hit nếu còn trong store.

Nếu điều kiện có tính động như feature flag, chính sách hệ thống cần xác định rõ lúc nào xóa cache hoặc thay đổi version của key. `condition` tự nó chỉ **bỏ qua thao tác hiện tại**, không làm data migration hay xóa lịch sử cache.

### 7.4. Cân nhắc chi phí kiểm tra

`condition` là một phần của đường gọi cache. Với cache hit, việc đánh giá điều kiện cũng có chi phí; những biểu thức ngắn dựa trên tham số thường chấp nhận được. Đừng gọi HTTP, mở transaction hoặc truy vấn DB chỉ để trả về boolean trong `condition`: cách đó làm mất lợi ích của cache và có thể tạo độ trễ không ổn định.

### 7.5. Tương tác với key và kết quả

Nếu cùng một cache chứa hai kết quả khác nhau cho một key giống nhau (chẳng hạn theo locale/tenant mà locale/tenant không nằm trong key), `condition=true` không thể sửa lỗi va chạm đó. Key mặc định có thể lấy tất cả tham số, nhưng `key="#p0"` tùy biến chỉ lấy giá trị được chỉ định. Kiểm tra **trường nào quyết định dữ liệu đầu ra**, và đảm bảo key chứa đủ dữ liệu đó.

Trong luồng cập nhật, `@Cacheable`, `@CachePut` và `@CacheEvict` phải thống nhất về cache region và key. Dùng condition chọn vùng cần cache mà quên invalidate vùng ấy là một nguồn gây stale data phổ biến.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể xảy ra | Cách kiểm tra |
| --- | --- | --- |
| `condition=false` nhưng method vẫn chạy | Đây là hành vi đúng của cache bypass | Phân biệt bỏ qua cache với ngăn nghiệp vụ. |
| `condition=true` nhưng method vẫn chạy | Cache miss, hết hạn, key khác hoặc proxy không kích hoạt | Đo call count và key/cache name. |
| Lỗi SpEL khi tham số null | Truy cập method/property của null trước khi guard | Dùng `#p0 != null && ...`. |
| Viết `condition="#result != null"` | `@Cacheable.condition` đánh giá trước khi có result | Chuyển kiểm tra kết quả sang `unless`. |
| Query không được cache dù mong muốn | Điều kiện sai hoặc kiểu tham số khác dự kiến | Log/kiểm thử input trong bối cảnh request. |
| Method chạy trực tiếp dù có annotation | Bean không do Spring quản lý, `@EnableCaching` sai context, self-invocation | Kiểm tra bean/proxy và context cấu hình. |
| Có entry cũ khi feature flag bật lại | `condition=false` không tự xóa cache | Evict hoặc version key theo chính sách. |
| Dữ liệu của người dùng khác bị trả ra | Cache key thiếu tenant/user scope, authorization đặt sai vị trí | Thiết kế phân quyền và cách chọn cache/key đúng. |
| `@CacheEvict` không xóa entry cũ | Điều kiện evict sai, key không khớp, chỉ xóa một region | Đối chiếu operation đọc và evict. |

Bắt đầu debug với phép thử nhỏ, có thể đo: cùng key gọi hai lần khi `condition=true`, sau đó thử key không thỏa điều kiện hai lần. Nếu case đầu hit và case sau luôn thực thi body, logic condition đang vận hành như mong muốn.

Khi cần quan sát xử lý annotation, có thể bật log trong môi trường test:

```properties
logging.level.org.springframework.cache.interceptor=TRACE
```

Tên logger/cường độ thông tin phụ thuộc cấu hình logging của ứng dụng. Không dựa duy nhất vào một dòng log; kiểm tra behavior từ kết quả và số lần body chạy vẫn cần thiết.

## 9. Checklist kiểm thử và bài tập tư duy

1. **Điều kiện đúng, cache chưa có entry:** gọi lần đầu, đếm lần chạy method tăng 1. Gọi lại cùng key mà cache chưa bị evict thì đếm không tăng.
2. **Điều kiện sai:** gọi hai lần cùng key, đếm lần chạy tăng 2; kiểm tra provider không chứa entry mới từ hai lượt này.
3. **Đối số null:** biểu thức ngắn mạch không lỗi; method vẫn xử lý được null theo contract hoặc trả lỗi nghiệp vụ có kiểm soát.
4. **Condition đúng nhưng unless veto:** method chạy khi miss, kết quả không được put; lần sau vẫn phải chạy lại nếu entry chưa tồn tại.
5. **Đã có entry rồi condition đổi thành false:** lượt hiện tại bypass. Kiểm tra entry cũ không bị tự động xóa.
6. **Dữ liệu thay đổi:** thử luồng update + evict với cùng cache name/key để chứng minh dữ liệu cũ không bị tái sử dụng.
7. **Nhiều context/proxy:** lấy service từ Spring context khi integration test; không chứng minh caching bằng cách gọi trực tiếp `new Service()`.

Câu hỏi kiểm tra:

**Q1.** `condition=false` có làm method không chạy?

**Đáp:** Không. Với `@Cacheable`, nó bỏ qua cache cho lời gọi đó, vì vậy method vẫn thực thi.

**Q2.** Trong `@Cacheable.condition` có thể viết `#result.isEmpty()` không?

**Đáp:** Không. Kết quả chưa có ở giai đoạn kiểm tra condition; dùng `unless="#result == null || #result.isEmpty()"` khi cần đánh giá sau method.

**Q3.** Lời gọi dùng cùng key, một lần condition true tạo cache entry; lần khác condition false. Entry có bị xóa không?

**Đáp:** Không. Lời gọi condition false chỉ bypass cache operation tại thời điểm đó.

**Q4.** `@CachePut(condition=false)` có bỏ qua lưu database không?

**Đáp:** Không. CachePut không ngăn method chạy; việc ghi database là nghiệp vụ trong method và diễn ra theo logic phương thức.

**Q5.** Có thể dùng `condition` để kiểm tra tenant được quyền truy cập dữ liệu không?

**Đáp:** Không đủ. Authorization phải bảo vệ cả cache hit và miss; cần chọn cache/key có phạm vi dữ liệu đúng.

## 10. Ghi nhớ

- `condition` là **SpEL boolean dựa trên ngữ cảnh lời gọi**, dùng để quyết định **áp dụng cache operation hay bỏ qua**.
- Với `@Cacheable`: `condition=false` → **không tra cache, không ghi cache, method vẫn chạy**; `condition=true` → tra cache, hit thì có thể bỏ qua body, miss thì chạy và có thể ghi.
- `condition` được kiểm tra khi chưa có kết quả method; dùng `unless` nếu cần từ chối ghi cache dựa trên `#result`.
- Kiểm tra null an toàn, biểu thức không side effect, đảm bảo key/region/eviction nhất quán và phân quyền độc lập với cache.
- Mọi kiểm thử caching annotation phải đi qua **Spring proxy** và quan sát cả số lần thực thi lẫn nội dung cache.

### Tài liệu tham khảo

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — @Cacheable API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/cache/annotation/Cacheable.html)
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
