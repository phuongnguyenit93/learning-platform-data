# SimpleKeyGenerator với không có, một hoặc nhiều đối số trong Spring Cache

## 1. Vấn đề: từ lời gọi phương thức thành khóa cache

Khi gọi một phương thức có `@Cacheable`, Spring cần một **cache key** để tìm hoặc lưu kết quả. Cache key đại diện cho *đầu vào có ý nghĩa của lời gọi*, trong khi `cacheNames`/`CacheResolver` xác định **vùng cache** nơi key được dùng.

Ví dụ:

```java
@Cacheable("products")
public String getProduct(String sku) {
    return loadProductFromDatabase(sku);
}
```

Đoạn trên chỉ minh họa một phương thức trong service đã cấu hình caching; `loadProductFromDatabase` là nghiệp vụ do ứng dụng cung cấp. Lời gọi `getProduct("A01")` sẽ tạo key từ tham số `"A01"`. Nếu gọi lại cùng key trong cùng cache và entry còn hợp lệ, Spring có thể trả kết quả mà không chạy thân phương thức.

Khi annotation không khai báo `key` hoặc `keyGenerator` riêng, mặc định Spring sử dụng `org.springframework.cache.interceptor.SimpleKeyGenerator`. Bài này tập trung vào **chính xác key nào được sinh ra khi có 0, 1 hoặc nhiều đối số**, các ngoại lệ quan trọng và cách kiểm chứng.

## 2. Thuật toán mặc định của SimpleKeyGenerator

`SimpleKeyGenerator` quyết định key dựa trên **danh sách giá trị đối số tại thời điểm gọi**, không tự thêm tên phương thức, lớp, tên bean hay tên cache vào key. Tên cache đã được dùng riêng để tìm vùng lưu trữ; nếu hai phương thức dùng **cùng vùng** với **cùng key**, chúng có thể đụng nhau.

| Đối số truyền vào | Key mặc định | Ghi chú |
| --- | --- | --- |
| Không có đối số | `SimpleKey.EMPTY` | Một hằng đại diện cho danh sách đối số rỗng. |
| Một đối số **khác null, không phải mảng** | Chính đối tượng đó | Ví dụ `"A01"` hoặc `Integer.valueOf(7)`; không tạo `SimpleKey`. |
| Một đối số bằng `null` | `new SimpleKey((Object) null)` về mặt ngữ nghĩa | Kết quả vẫn là một đối tượng key khác `null`. |
| Một đối số là **mảng** | Một `SimpleKey` chứa mảng | Kể cả `int[]`, `String[]`; xử lý so sánh phần tử theo chiều sâu. |
| Từ hai đối số trở lên | Một `SimpleKey` chứa tất cả đối số theo thứ tự | Ví dụ `("VN", 7)` khác `(7, "VN")`. |

Một cách đọc tương đương thuật toán:

1. Nếu số phần tử là 0, lấy `SimpleKey.EMPTY`.
2. Nếu đúng 1 phần tử, trả **trực tiếp** phần tử đó **chỉ khi** nó khác `null` và không phải mảng.
3. Các trường hợp còn lại, tạo `SimpleKey` từ danh sách đối số.

Đặc biệt, một số bản tóm tắt chỉ ghi “một đối số → trả chính đối số”. Mô tả này thiếu hai ngoại lệ thực tế của implementation hiện đại: **`null` và mảng**. Với một đối số `null`, việc bọc vào `SimpleKey` tránh dùng trực tiếp null làm cache key; với mảng, việc bọc cho phép so sánh nội dung phần tử.

Ví dụ độc lập về kiểu key:

```java
import org.springframework.cache.interceptor.SimpleKey;
import org.springframework.cache.interceptor.SimpleKeyGenerator;

Object noArgs = SimpleKeyGenerator.generateKey();
Object one = SimpleKeyGenerator.generateKey("A01");
Object two = SimpleKeyGenerator.generateKey("VN", 7);
Object nullable = SimpleKeyGenerator.generateKey((Object) null);
Object array = SimpleKeyGenerator.generateKey((Object) new int[] {1, 2});

System.out.println(noArgs == SimpleKey.EMPTY);       // true
System.out.println(one.equals("A01"));              // true
System.out.println(two instanceof SimpleKey);       // true
System.out.println(nullable instanceof SimpleKey);  // true
System.out.println(array instanceof SimpleKey);     // true
```

Đây là **đoạn minh họa bên trong một method Java**, không phải file độc lập; mục 4 có chương trình chạy đầy đủ. Dùng ép kiểu `(Object)` khi truyền mảng tham chiếu cho lời gọi Java `Object...` nếu cần thể hiện rõ **một đối số là mảng**, tránh Java tự trải một `Object[]` thành nhiều tham số varargs của lời gọi kiểm thử.

### 2.1. Không có đối số

```java
@Cacheable("siteConfig")
public String currentConfig() { /* ... */ return "config"; }
```

Mọi lời gọi đến phương thức không đối số này, khi dùng generator mặc định, sẽ có key `SimpleKey.EMPTY`. Vì vậy cache theo một phương thức không đối số thường có thể hit tốt. Nhưng nếu hai phương thức **không đối số** cùng trỏ vào cache tên `siteConfig` và cùng dùng generator mặc định, chúng có **cùng key**, dù phương thức hoặc kiểu kết quả khác nhau.

Giải pháp là tách tên cache theo mục đích, hoặc tạo key khác biệt có chủ đích, ví dụ `key = "'currentConfig'"` trên một operation.

### 2.2. Một đối số thông thường

```java
@Cacheable("userProfiles")
public Profile getProfile(String userId) { /* ... */ return null; }
```

Với `getProfile("u1")`, key là String `"u1"`. Không có wrapper `SimpleKey` bổ sung. Hai String khác instance nhưng cùng nội dung vẫn tương đương theo `String.equals()` và `String.hashCode()`, nên một Map cache thông thường có thể hit.

Với đối số kiểu record bất biến hoặc object tự định nghĩa, key là **object đó**. Do đó class của object cần triển khai `equals()/hashCode()` nhất quán với định danh nghiệp vụ; nếu vẫn sử dụng so sánh identity mặc định, hai instance biểu diễn cùng dữ liệu có thể tạo hai key khác nhau.

### 2.3. Nhiều đối số

```java
@Cacheable("prices")
public String price(String region, long productId) {
    /* ... */
    return "";
}
```

`price("VN", 42)` tạo `SimpleKey` gồm hai phần tử `["VN", 42L]`. `price("US", 42)` tạo key khác; đổi thứ tự đối số cũng đổi key. `SimpleKey` dùng cơ chế so sánh và hash dựa trên **toàn bộ phần tử theo đúng thứ tự**, không gộp các tham số thành một số hash đơn lẻ rồi coi hai hash giống nhau là hai key giống nhau.

Chính vì vậy cấu hình nhiều tham số thường đủ tốt khi tất cả tham số đều ổn định và có `equals()/hashCode()` đúng. Trường hợp một tham số không ảnh hưởng kết quả mà chỉ phục vụ log/tracing, mặc định generator vẫn đưa nó vào key và có thể tạo nhiều entry không cần thiết.

## 3. Những trường hợp dễ hiểu sai

### 3.1. Một đối số null không phải key null

`SimpleKeyGenerator.generateKey((Object) null)` tạo một `SimpleKey` chứa một phần tử null. Nó **khác** `SimpleKey.EMPTY`, và không trả trực tiếp null. Tuy nhiên, một số biểu thức tùy biến như `key = "#p0"` có thể đánh giá thành null và không được provider/cache abstraction chấp nhận. Cần phân biệt **key mặc định** với **SpEL key tự khai báo**.

### 3.2. Một đối số mảng được bọc thành SimpleKey

Hai mảng `new int[] {1, 2}` là hai object riêng, thường không bằng nhau theo `Object.equals()` của mảng. Vì `SimpleKey` hỗ trợ so sánh sâu, hai lần gọi với mảng mới nhưng cùng phần tử có thể sử dụng cùng cache entry:

```java
Object k1 = SimpleKeyGenerator.generateKey((Object) new int[] {1, 2});
Object k2 = SimpleKeyGenerator.generateKey((Object) new int[] {1, 2});
System.out.println(k1.equals(k2)); // true
```

Với `String[]`, để Java hiểu một **mảng làm đối số đơn của generator** trong ví dụ trực tiếp, cần ép kiểu:

```java
Object key = SimpleKeyGenerator.generateKey(
        (Object) new String[] {"red", "blue"});
```

Trong lời gọi Spring AOP đến service thực tế, Spring lấy mảng tham số đã được reflection/AOP cung cấp; bạn không phải ép kiểu trong mỗi lời gọi phương thức business. Lưu ý `SimpleKey` không biến các đối tượng lồng trong mảng thành bất biến: thay đổi nội dung mảng sau khi cache có thể làm nghĩa của key, `equals()` hoặc `hashCode()` biến đổi và gây lỗi tra cứu. Hãy ưu tiên input bất biến.

### 3.3. Collection không được tự động chuẩn hóa thành SimpleKey

Một đối số `List<String>` khác null và không phải mảng sẽ thường được dùng **trực tiếp** làm key, vì `SimpleKeyGenerator` chỉ kiểm tra `param.getClass().isArray()` cho ngoại lệ kiểu dữ liệu. List chuẩn của Java có so sánh theo phần tử, nhưng một List có thể thay đổi nội dung vẫn có rủi ro key không ổn định. Không suy luận “một container bất kỳ sẽ luôn được Spring bọc”.

### 3.4. Varargs của phương thức được cache

Phương thức `find(String... tags)` nhận một đối số Java là `String[]` sau biên dịch. Khi chỉ có parameter varargs này, mặc định Spring xử lý mảng như **một đối số là mảng**, tạo `SimpleKey` để giữ tính so sánh nội dung. Nếu phương thức có thêm tham số khác, key thường chứa các tham số theo thứ tự, trong đó varargs array là một phần tử của compound key. Không tự coi các chuỗi trong varargs là các tham số độc lập của `KeyGenerator`.

## 4. Chương trình hoàn chỉnh: nhìn trực tiếp cache hit/miss

Ví dụ dùng **Java 17+** với Spring Cache, `ConcurrentMapCacheManager` (cache bộ nhớ tiến trình) và default `SimpleKeyGenerator`. Ta dùng bốn tên cache riêng để tránh va chạm giữa các phương thức trong phần demo. Không khai báo `key` hay `keyGenerator` trên annotation nên Spring tự áp dụng thuật toán ở trên.

Tạo cấu trúc:

```text
simple-key-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/keys/SimpleKeyDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'simple-key-demo'
```

`build.gradle`:

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
    mainClass = 'demo.keys.SimpleKeyDemo'
}
```

`src/main/java/demo/keys/SimpleKeyDemo.java`:

```java
package demo.keys;

import java.util.Arrays;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.SimpleKey;
import org.springframework.cache.interceptor.SimpleKeyGenerator;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class SimpleKeyDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class CacheConfig {
        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager(
                    "zero", "single", "multiple", "arrays");
        }

        @Bean
        DemoService demoService() {
            return new DemoService();
        }
    }

    // Spring tạo proxy cho bean này nhờ @EnableCaching.
    public static class DemoService {
        private int zeroCount;
        private int singleCount;
        private int multipleCount;
        private int arraysCount;

        @Cacheable("zero")
        public String zero() {
            return "zero#" + ++zeroCount;
        }

        @Cacheable("single")
        public String single(String sku) {
            return "sku=" + sku + "#" + ++singleCount;
        }

        @Cacheable("multiple")
        public String multiple(String region, int page) {
            return region + ":" + page + "#" + ++multipleCount;
        }

        @Cacheable("arrays")
        public String arrays(int[] numbers) {
            return Arrays.toString(numbers) + "#" + ++arraysCount;
        }

        public String counts() {
            return zeroCount + "/" + singleCount + "/"
                    + multipleCount + "/" + arraysCount;
        }
    }

    public static void main(String[] args) {
        // Quan sát key mà generator mặc định tạo ra.
        Object k0 = SimpleKeyGenerator.generateKey();
        Object k1 = SimpleKeyGenerator.generateKey("A");
        Object k2 = SimpleKeyGenerator.generateKey("VN", 2);
        Object kn = SimpleKeyGenerator.generateKey((Object) null);
        Object ka = SimpleKeyGenerator.generateKey((Object) new int[] {1, 2});
        Object kb = SimpleKeyGenerator.generateKey((Object) new int[] {1, 2});

        System.out.println("empty=" + (k0 == SimpleKey.EMPTY));
        System.out.println("one=" + "A".equals(k1));
        System.out.println("multiple=" + (k2 instanceof SimpleKey));
        System.out.println("null=" + (kn instanceof SimpleKey));
        System.out.println("array=" + (ka instanceof SimpleKey));
        System.out.println("deepArrayEqual=" + ka.equals(kb));

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(CacheConfig.class)) {
            DemoService service = context.getBean(DemoService.class);

            System.out.println(service.zero());
            System.out.println(service.zero());

            System.out.println(service.single("A"));
            System.out.println(service.single("A"));
            System.out.println(service.single("B"));

            System.out.println(service.multiple("VN", 2));
            System.out.println(service.multiple("VN", 2));
            System.out.println(service.multiple("US", 2));

            System.out.println(service.arrays(new int[] {1, 2}));
            System.out.println(service.arrays(new int[] {1, 2}));
            System.out.println(service.arrays(new int[] {2, 1}));

            System.out.println("executions=" + service.counts());
        }
    }
}
```

Trong thư mục `simple-key-demo`, chạy `gradle run --quiet` với Gradle phù hợp Java 17, hoặc `./gradlew run --quiet` nếu dự án đã có Gradle Wrapper (Windows PowerShell: `.\gradlew.bat run --quiet`).

Các dòng do `System.out.println` tạo ra theo thứ tự (log từ framework/build tool, nếu có, nằm ngoài phần này):

```text
empty=true
one=true
multiple=true
null=true
array=true
deepArrayEqual=true
zero#1
zero#1
sku=A#1
sku=A#1
sku=B#2
VN:2#1
VN:2#1
US:2#2
[1, 2]#1
[1, 2]#1
[2, 1]#2
executions=1/2/2/2
```

**Diễn giải bằng số lần thực thi method:**
- `zero()` không có đối số: key luôn `SimpleKey.EMPTY`, gọi hai lần chỉ chạy body một lần.
- `single("A")` dùng String `"A"` làm key. Gọi lần hai hit; đổi sang `"B"` sẽ miss, nên count = 2.
- `multiple("VN", 2)` dùng compound `SimpleKey`. Gọi lại cả cặp hit; đổi region thành `"US"` sẽ miss, nên count = 2.
- `arrays(new int[] {1, 2})` được gọi hai lần với hai mảng object khác nhau nhưng phần tử giống nhau. `SimpleKey` so sánh nội dung nên lần hai hit; đảo phần tử thành `{2, 1}` miss, nên count = 2.

Chú ý `getBean(DemoService.class)` lấy **bean từ Spring context**, không dùng `new DemoService()`. Nếu gọi trực tiếp đối tượng không qua cache proxy, annotation sẽ không được thực thi và bạn không quan sát được hit/miss như trên.

## 5. Khi nào khóa mặc định là lựa chọn tốt?

Dùng `SimpleKeyGenerator` khi các tham số có bản chất phù hợp làm định danh của kết quả cache, cụ thể:

- Không tham số: phương thức trả cùng loại dữ liệu toàn cục trong một vùng cache cụ thể và có chính sách invalidate rõ ràng.
- Một đối số: giá trị có `equals()`/`hashCode()` ổn định, ví dụ String, UUID, Long hoặc immutable record với các thành phần phù hợp.
- Nhiều đối số: mọi phần tử cùng tham gia xác định kết quả, thứ tự có nghĩa, không có tham số biến động vô ích như trace ID.
- Có mảng đầu vào: cách tạo key mặc định bảo toàn so sánh nội dung với mảng, nhưng input phải ổn định suốt đời entry.

Ngược lại, xem xét thay key khi:
- Chỉ một phần tham số ảnh hưởng dữ liệu (ví dụ `locale` và `id` có ý nghĩa, `traceId` thì không).
- Hai phương thức chia sẻ một vùng cache, có kiểu đầu ra khác nhau nhưng trùng bộ tham số.
- Đối số là entity mutable, collection mutable hoặc object không triển khai đúng `equals()`/`hashCode()`.
- Cần phân vùng theo tenant hoặc bảo mật: lựa chọn cache và key phải bao phủ đầy đủ phạm vi dữ liệu.
- Cache provider yêu cầu key format cụ thể (ví dụ String có prefix/namespace), hoặc đòi hỏi serialization tương thích khi dùng cache phân tán.

## 6. Va chạm giữa các phương thức dùng cùng cache

Xét hai phương thức trong một service:

```java
@Cacheable("catalog")
public Product findBySku(String sku) { /* ... */ return null; }

@Cacheable("catalog")
public Product findByBarcode(String barcode) { /* ... */ return null; }
```

Nếu cả hai được gọi với chuỗi `"123"`, key mặc định **đều là String "123"**. Generator không thêm tên method; vì vậy kết quả của method thứ nhất có thể được method thứ hai lấy lại từ cùng cache dù ý nghĩa tham số khác nhau.

Đây là **đoạn minh họa đặt trong service đã có kiểu `Product` và nghiệp vụ thật**, không phải code độc lập. Có ba cách xử lý phổ biến:

1. Đặt tên cache khác nhau, ví dụ `productsBySku` và `productsByBarcode`, phù hợp khi mỗi nhóm key có chính sách TTL/eviction riêng.
2. Dùng namespace ở key theo method, ví dụ `@Cacheable(cacheNames = "catalog", key = "'sku:' + #p0")` và `key = "'barcode:' + #p0"`.
3. Dùng `KeyGenerator` tự viết nếu nhiều method có một quy tắc chung phức tạp, cần bao gồm tên method, loại đối số, tenant và/hoặc version dữ liệu.

Không trông chờ hash code khác nhau để bảo vệ logic: key equality mới là quan hệ phân biệt cần đúng.

## 7. Tùy biến key qua annotation

Nếu muốn bỏ qua tham số không ảnh hưởng kết quả:

```java
@Cacheable(cacheNames = "products", key = "#p0 + ':' + #p1")
public Product getProduct(String tenantId, String productId, String traceId) {
    // traceId chỉ phục vụ logging và không thay đổi dữ liệu sản phẩm.
    return repository.load(tenantId, productId);
}
```

Đây là đoạn code **minh họa trong một service** có `Product`/`repository` hợp lệ, không phải chương trình độc lập. Ở đây SpEL `#p0` và `#p1` lấy hai tham số đầu tiên, còn `traceId` không tham gia cache key. Cần đảm bảo cách nối chuỗi không mơ hồ nếu giá trị có thể chứa dấu `:`; có thể dùng key object bất biến hoặc cấu trúc key rõ ràng hơn.

Nếu dùng generator tùy biến cho nhiều method:

```java
@Configuration(proxyBeanMethods = false)
class CacheKeyConfig {
    @Bean("businessKeyGenerator")
    KeyGenerator businessKeyGenerator() {
        return (target, method, params) -> {
            // Mã chỉ mang tính minh họa: phân biệt method và
            // giữ danh sách tham số bằng SimpleKey.
            Object[] keyParts = new Object[params.length + 1];
            keyParts[0] = method.getName();
            System.arraycopy(params, 0, keyParts, 1, params.length);
            return new SimpleKey(keyParts);
        };
    }
}
```

Cần bổ sung import `KeyGenerator`, `SimpleKey`, `@Bean` và `@Configuration`. Với các method overload hoặc nhiều lớp cùng dùng một cache, chỉ `method.getName()` có thể chưa đủ: cân nhắc thêm class và kiểu tham số hoặc namespace nghiệp vụ. Để kích hoạt trên một operation:

```java
@Cacheable(cacheNames = "catalog", keyGenerator = "businessKeyGenerator")
public Product load(String tenantId, long id) { /* ... */ return null; }
```

**Không khai báo đồng thời `key` và `keyGenerator` trên cùng một cache operation**: đây là hai cách chọn key loại trừ nhau. Bạn có thể đặt generator mặc định theo cấu hình chung bằng `CachingConfigurer` (và kiểm soát phạm vi `ApplicationContext` tương ứng) nếu nhiều method cùng cần quy tắc đó.

## 8. Đồng bộ giữa đọc, ghi và xóa cache

Giả sử `@Cacheable` dùng key mặc định `SimpleKey("VN", 42)` nhưng `@CacheEvict` chỉ dùng `key="#p1"`, thao tác xóa sẽ nhắm key `42`, nên entry dạng compound key **không bị xóa**. Điều này tạo stale data dù nghiệp vụ đã cập nhật database.

Cần giữ thống nhất **cache name/cache resolver** và **quy tắc sinh key** giữa các annotation liên quan:

```java
@Cacheable("prices")
public Price getPrice(String region, long productId) { /* ... */ return null; }

@CacheEvict(cacheNames = "prices")
public void invalidatePrice(String region, long productId) { /* ... */ }
```

Đây là đoạn minh họa khi cả hai method nhận đúng hai tham số cùng thứ tự; mặc định cả hai có `SimpleKey(region, productId)`. Nếu method xóa nhận input khác cấu trúc, hãy chỉ định SpEL hoặc `KeyGenerator` sao cho chính xác. Với `allEntries=true`, thao tác xóa toàn bộ cache không dùng một key cụ thể, nên đây là trường hợp chính sách khác.

## 9. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Khả năng cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Không có đối số nhưng trả nhầm kết quả của method khác | Hai method dùng cùng cache và `SimpleKey.EMPTY` | Tách tên cache hoặc key có namespace. |
| Một đối số `String[]`, kết quả khó hiểu | Gọi trực tiếp API varargs trong test khiến mảng bị trải thành nhiều tham số | Ép kiểu `(Object)` khi gọi `generateKey` để mô phỏng một tham số mảng. |
| Cùng dữ liệu object nhưng luôn miss | `equals/hashCode` so sánh identity hoặc tham số chứa trace/timestamp | Sửa định danh bất biến hoặc dùng SpEL/custom key. |
| Có mảng input, sau đó miss bất thường | Code đã mutate mảng/nội dung nested làm key không ổn định | Copy thành immutable input trước khi cache. |
| Xóa không có tác dụng | `@CacheEvict` dùng key khác `@Cacheable` | Đồng nhất tên cache và key, kiểm tra cả kiểu/thứ tự đối số. |
| Cache hit giữa hai phương thức khác nhau | Default key không chứa method/class | Dùng cache khác hoặc namespaced key. |
| Không bao giờ hit dù key đúng | Lời gọi không qua Spring proxy; `@EnableCaching` chưa có hoặc sai context | Kiểm tra Spring-managed bean, self-invocation và cấu hình caching. |
| Key đúng nhưng hit/miss khác dự kiến | Provider TTL, eviction, serialization hoặc backend nhiều instance | Kiểm tra cấu hình provider, thời điểm xóa và telemetry. |

Khi debug, kiểm tra **ba thành phần độc lập**: cache được chọn là gì, key thực tế là gì, và lời gọi có đi qua proxy cache hay không. Đừng đồng nhất việc có bean `CacheManager` với việc caching annotation đã được kích hoạt.

## 10. Bài tập tự kiểm tra

1. Phương thức `@Cacheable("x") String status()` không nhận tham số. Sau khi gọi một lần, key dự kiến là gì? — **`SimpleKey.EMPTY`**.
2. Phương thức `get(int id)` với `id=7` dùng default generator. Key là gì? — **Integer 7** do boxing, không phải `SimpleKey(7)`.
3. Phương thức `get(String tenant, int id)` được gọi `("VN", 7)`. Key là gì? — **`SimpleKey("VN", 7)`** theo thứ tự hai tham số.
4. Một method nhận đúng **một** `int[]` được gọi lần lượt với `new int[]{1,2}` và mảng mới cùng phần tử. Các key tương đương không? — **Có**, miễn nội dung ổn định và cùng quy tắc key mặc định.
5. Phương thức `lookup(UserKey key)` tạo hai instance khác nhau nhưng cùng ID; `UserKey` không override `equals/hashCode`. Có chắc hit không? — **Không**; một đối số object được dùng trực tiếp và mặc định so sánh theo identity.
6. Hai phương thức khác nhau cùng dùng cache `x` và cùng nhận String `"A"`. Key có khác nhau vì tên method không? — **Không**; tên method không nằm trong `SimpleKeyGenerator` mặc định.
7. Khi `@CacheEvict` dùng chỉ `productId`, còn `@Cacheable` dùng cặp `(tenantId, productId)`, có xóa trúng key không? — **Không**, nếu không tùy biến để hai annotation dùng cùng cấu trúc key.

## 11. Ghi nhớ

- **0 tham số:** `SimpleKey.EMPTY`.
- **1 tham số thường:** chính đối tượng đó; **1 null hoặc 1 mảng:** bọc vào `SimpleKey`.
- **2+ tham số:** `SimpleKey` chứa toàn bộ đối số theo đúng thứ tự.
- Generator mặc định **không chứa tên method hoặc class**; chọn tên cache và namespace key cẩn thận.
- Key có `equals/hashCode` ổn định và quy tắc nhất quán giữa `@Cacheable`, `@CachePut`, `@CacheEvict` mới giúp cache hoạt động đúng.

### Tài liệu tham khảo

- [Spring Framework – Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework – SimpleKeyGenerator API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/SimpleKeyGenerator.html)
- [Spring Framework – SimpleKey API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/SimpleKey.html)
- [Spring Framework – Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
