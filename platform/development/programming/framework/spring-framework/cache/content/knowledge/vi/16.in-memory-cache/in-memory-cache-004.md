# Tùy chọn lưu theo giá trị và yêu cầu tuần tự hóa trong Spring Cache

## Mục tiêu bài học

Trong cache bộ nhớ, một đối tượng Java có thể được lưu theo **tham chiếu (store-by-reference)** hoặc theo **giá trị/bản sao (store-by-value)**. Khác biệt này không chỉ là tối ưu hiệu năng: nó quyết định liệu việc sửa một đối tượng mà caller nhận từ cache có thể vô tình **làm thay đổi dữ liệu được cache** hay không.

Spring Framework có một tùy chọn cụ thể trên `ConcurrentMapCacheManager`: `setStoreByValue(true)`. Khi bật, `ConcurrentMapCache` sử dụng cơ chế serialization để lưu bản sao của **giá trị cache**. Điều này tạo ra một yêu cầu quan trọng: đối tượng được cache phải có thể được tuần tự hóa một cách hợp lệ, bao gồm cả các thành phần trong object graph.

Sau bài học, bạn sẽ:

- Phân biệt **store-by-reference** và **store-by-value** bằng object identity, trạng thái và mutation.
- Hiểu mặc định của `ConcurrentMapCacheManager` và cách bật `setStoreByValue(true)`.
- Giải thích vì sao `Serializable` không đồng nghĩa “mọi trường đều tự tuần tự hóa được”.
- Nhận biết lỗi runtime khi cache một đối tượng không serializable, thay vì nhầm với lỗi `@Cacheable` hoặc cache miss.
- Chạy chương trình Java 17 + Spring Framework minh họa việc sửa đối tượng trước và sau khi cache hit.
- Biết khi nào nên dùng DTO bất biến, defensive copy, store-by-value, Redis hoặc một cache provider khác.
- Nhận diện chi phí CPU/bộ nhớ, tương thích serialization, class loader, transaction và rủi ro bảo mật.

> **Điểm cốt lõi:** `@Cacheable` không xác định việc trả tham chiếu hay bản sao. Đối với `ConcurrentMapCacheManager`, mặc định là **store-by-reference**. Bật `setStoreByValue(true)` làm manager lưu **bản sao đã serialized** và mỗi lần đọc sẽ tạo giá trị giải tuần tự hóa tương ứng; **giá trị phải serializable**.

## 1. Vì sao hai chế độ lưu trữ lại quan trọng?

Giả sử một phương thức truy vấn sản phẩm:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public MutableProduct getProduct(long id) {
    return repository.findProduct(id);
}
~~~

Đây là đoạn minh họa; `MutableProduct` và repository cần được định nghĩa trong ứng dụng thực tế.

Lần đầu `getProduct(42)` cache miss, Spring chạy phương thức và lưu kết quả. Caller nhận được một đối tượng `MutableProduct`. Nếu đối tượng đó có setter:

~~~java
MutableProduct p = service.getProduct(42);
p.setName("Tên sửa tạm trong giao diện");
~~~

Điều gì sẽ xảy ra ở lần gọi `service.getProduct(42)` tiếp theo?

- Với **store-by-reference**, cache có thể đang giữ **chính tham chiếu** của đối tượng `p`. Setter thay đổi đối tượng mà cache đang trỏ tới. Lần đọc sau có thể nhìn thấy tên “Tên sửa tạm trong giao diện” **dù repository chưa hề được cập nhật**.
- Với **store-by-value**, cache giữ bản sao đã được tách khỏi `p`. Setter sửa `p` của caller nhưng không thay đổi bản sao nằm trong cache. Lần đọc sau nhận một bản được deserialized từ dữ liệu đã lưu, nên vẫn có tên ban đầu.

Hai chế độ đều có thể tạo cache hit và tránh truy vấn lại. Sự khác biệt là **quyền sở hữu và chia sẻ object identity**, không phải tốc độ tra cứu key.

### Minh họa bộ nhớ

~~~text
STORE-BY-REFERENCE

Cache["42"] ---------+
                     |
                     v
                 Product A
                 name="Book"
                     ^
                     |
Caller variable -----+

Caller gọi A.setName("Changed")
=> Cache["42"] vẫn trỏ Product A, nên thấy "Changed".


STORE-BY-VALUE

Caller variable ----> Product A
                       name="Book"
                          |
                    serializable copy
                          |
                          v
Cache["42"] ---------- serialized snapshot ("Book")

Caller gọi A.setName("Changed")
=> Snapshot vẫn chứa "Book".

Lần đọc tiếp:
snapshot -> deserialize -> Product B, name="Book"
~~~

**Lưu ý rất quan trọng:** store-by-value không có nghĩa cache tự biết lúc nào nguồn dữ liệu thật thay đổi. Nó chỉ tạo **ranh giới bản sao** giữa caller và nội dung được cache. Khi database đổi, vẫn phải dùng chiến lược invalidation như `@CacheEvict`, `@CachePut` hoặc TTL phù hợp.

## 2. API nào hỗ trợ store-by-value trong Spring?

### 2.1. ConcurrentMapCacheManager

Trong Spring Framework, `ConcurrentMapCacheManager` quản lý các `ConcurrentMapCache` sử dụng `ConcurrentHashMap` làm nơi lưu trữ. API đáng chú ý:

~~~java
void setStoreByValue(boolean storeByValue);
boolean isStoreByValue();
~~~

Đây là **chữ ký API rút gọn** của manager, không phải một class tự viết.

Hợp đồng chính:

- `setStoreByValue(false)` — **mặc định**: lưu object reference, không yêu cầu đối tượng cache phải triển khai `Serializable`.
- `setStoreByValue(true)`: lưu **bản sao** của mỗi cache value; mọi value được lưu phải tuần tự hóa được.
- `isStoreByValue()`: xác nhận chế độ hiện tại.
- Khi **thay đổi** lựa chọn store-by-value trên manager đã có cache, Spring có thể **reset các cache hiện hữu** để cấu hình lại. Vì thế nên đặt mode **một lần khi cấu hình**, trước khi ứng dụng phục vụ traffic, thay vì bật/tắt giữa lúc đang chạy.

Đây là tùy chọn của **implementation `ConcurrentMapCacheManager`**, không phải thuộc tính tiêu chuẩn của mọi `CacheManager`.

### 2.2. Cấu hình Java trong Spring

~~~java
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CacheConfiguration {

    @Bean
    CacheManager cacheManager() {
        ConcurrentMapCacheManager manager =
            new ConcurrentMapCacheManager("products");
        manager.setStoreByValue(true);
        return manager;
    }
}
~~~

Đây là mã cấu hình có thể tích hợp vào một ứng dụng Spring có `@EnableCaching`. Khi dùng `@Cacheable(cacheNames = "products")`, cache operation dùng `products` trong manager đã bật store-by-value.

Không tồn tại thuộc tính chuẩn:

~~~java
@Cacheable(cacheNames = "products", storeByValue = true)
~~~

**Dòng trên là phản ví dụ cú pháp không hợp lệ** của `@Cacheable` chuẩn Spring: annotation không có attribute `storeByValue`. Không nên sao chép vào chương trình chạy.

### 2.3. Không có một công tắc áp dụng cho tất cả provider

`CacheManager` là interface. API `setStoreByValue` nói trên là riêng cho `ConcurrentMapCacheManager`:

- Với **Caffeine** local cache thông thường, các object values do ứng dụng đặt vào thường được truy cập theo reference của JVM. Caffeine không mặc nhiên serialization-copy values mỗi lần `get`/`put`.
- Với **Redis cache**, dữ liệu phải được mã hóa/serialized thành bytes hoặc định dạng khác để lưu trên backend. Khi đọc, dữ liệu được deserialized bằng serializer cấu hình. Điều này **không đồng nghĩa** rằng Redis dùng cùng API hay Java native serialization với `ConcurrentMapCacheManager`.
- Với **JCache (JSR-107)**, store-by-value/store-by-reference là một khái niệm trong cache configuration, nhưng khả năng và mặc định phải đối chiếu provider và cách Spring tích hợp với nó.
- Với một custom `Cache`, người viết implementation có thể chọn chính sách khác, miễn thực hiện đúng hợp đồng Spring Cache.

Đừng suy ra rằng mọi backend đều hỗ trợ `setStoreByValue(true)` chỉ vì đang sử dụng cùng annotation `@Cacheable`.

## 3. Spring làm thế nào để tạo bản sao?

### 3.1. Không đơn thuần gọi clone()

Trong `ConcurrentMapCache`, chế độ store-by-value được hỗ trợ bằng một `SerializationDelegate` do manager cung cấp. Một cách nhìn khái quát là:

~~~text
PUT ("42", MutableProduct A)
               |
          serialize A
               |
         byte[] snapshot
               |
   ConcurrentHashMap["42"] = snapshot


GET ("42")
    |
lấy byte[] snapshot
    |
deserialize snapshot
    |
trả MutableProduct B
~~~

Đối tượng `B` là một instance mới và có trạng thái đã được lưu khi serialize. Việc caller sửa `B` không trực tiếp làm biến đổi bytes cất trong cache. Những lần `get` sau có thể tạo các đối tượng mới khác nhau.

**Không gọi đây là shallow copy.** Nếu mọi object trong graph đều được serializable và quá trình serialization thành công, những object con được ghi vào luồng serialization cũng được phục dựng theo graph. Đó là khác biệt lớn so với `clone()` đơn giản hay copy constructor chỉ sao chép một vài trường.

### 3.2. Chế độ mặc định giữ chính reference

Khi store-by-value tắt:

~~~text
Cache.put("42", objectA)
Cache.get("42") --> objectA
~~~

Đối với một value bình thường, `ConcurrentMapCache` trả object reference tương ứng qua wrapper, không tạo bản sao. Hai lần lấy cùng key thường trỏ tới cùng instance nếu entry chưa bị replace/evict.

**Ngoại lệ về câu chữ:** nếu có `null` caching, Spring có thể lưu một internal null marker vì `ConcurrentHashMap` không chấp nhận null. Cơ chế null marker không làm đổi ý nghĩa store-by-reference của những object values thông thường.

### 3.3. Thời điểm đầu tiên trả về trong @Cacheable

Khi cache miss, Spring gọi phương thức thật, nhận kết quả `A`, rồi yêu cầu cache put và trả kết quả cho caller. Ở chế độ store-by-value, lần put tạo snapshot nhưng **không có quy tắc bắt buộc biến luôn kết quả `A` thành một copy khác trước khi trả cho caller**.

Điều này dẫn tới phép thử rất hữu ích:

1. Gọi lần đầu, nhận `A`, cache lưu snapshot của `A`.
2. Sửa `A` ở caller.
3. Gọi lại cùng key để tạo cache hit, nhận `B`.
4. `B` phản ánh snapshot ở thời điểm put, không phải những sửa đổi sau đó của `A`.

Nếu cần cách ly cả kết quả đầu tiên khỏi nội trạng của repository/domain entity, bạn phải thiết kế DTO, defensive copy hoặc ranh giới mapping phù hợp. Store-by-value là một thuộc tính của cache, không phải một cơ chế bảo đảm mọi đối tượng trong toàn hệ thống đều bất biến.

## 4. Bảng so sánh để lựa chọn

| Tiêu chí | Store-by-reference | Store-by-value |
| --- | --- | --- |
| Cách lưu trong `ConcurrentMapCache` | Object reference | Serialized snapshot của value |
| Mặc định `ConcurrentMapCacheManager` | **Có** | Không; phải bật |
| Cần `Serializable` cho cached value | Không chỉ vì cache | **Có** |
| Caller sửa object đã lấy từ cache | Có thể tác động tới entry được chia sẻ | Không làm đổi snapshot đã lưu |
| Object identity qua các lần hit | Có thể là cùng instance | Thường là các instance khác nhau |
| Chi phí `get`/`put` | Thấp hơn, không serialization-copy | Phải serialize/deserialize; tốn CPU, allocations |
| Deep copy của object graph | Không có | Theo graph có thể serialization được |
| Thích hợp cho object mutable được nhiều caller dùng | Có rủi ro shared mutation | Giảm rủi ro aliasing do cache |
| Tính đúng sau database update | Vẫn cần invalidation | Vẫn cần invalidation |
| Tính sẵn sàng đa node | Chỉ local memory | **Vẫn chỉ local memory** |
| Nguy cơ tương thích serialization | Không phát sinh từ lưu reference | Có: class version, field types, class loader |
| TTL/max size | Không tự có | **Cũng không tự có** trong ConcurrentMapCacheManager |

**Store-by-value không miễn phí.** Nó là một cách đánh đổi hiệu năng để có khả năng cách ly giá trị cache khỏi việc mutate object do các caller khác nhau nắm giữ.

## 5. Yêu cầu Serializable: hiểu đúng trước khi bật

### 5.1. Lớp được cache phải serializable

Ví dụ đơn giản với Java 17:

~~~java
import java.io.Serializable;

public record ProductDto(
    long id,
    String name,
    long priceCents
) implements Serializable {}
~~~

Record **không tự mặc định implements Serializable**; bạn phải khai báo `implements Serializable` nếu muốn dùng Java serialization. Trong ví dụ trên, các thành phần `long` và `String` serializable nên record có thể được serialize.

Class truyền thống:

~~~java
import java.io.Serializable;

public class ProductDto implements Serializable {
    private static final long serialVersionUID = 1L;

    private final long id;
    private final String name;

    public ProductDto(long id, String name) {
        this.id = id;
        this.name = name;
    }

    public long getId() { return id; }
    public String getName() { return name; }
}
~~~

Đây là một class mẫu hoàn chỉnh về declaration, nhưng không có `main`; ví dụ runnable toàn bộ ở mục 6.

### 5.2. Từng trường trong object graph cũng quan trọng

Một lớp triển khai `Serializable` **không bảo đảm mọi field bên trong đều serializable**:

~~~java
import java.io.Serializable;
import java.util.concurrent.ExecutorService;

public class BadCachedResult implements Serializable {
    private static final long serialVersionUID = 1L;

    private String title;
    private ExecutorService workerPool;
}
~~~

Đoạn này là **phản ví dụ**: `workerPool` không phải dữ liệu nghiệp vụ cần lưu và thường không thể serialize. Dù lớp ngoài implements `Serializable`, việc ghi object graph có thể thất bại với nguyên nhân `NotSerializableException`.

Những field tham chiếu trực tiếp/gián tiếp đến các object như `InputStream`, `DataSource`, `EntityManager`, HTTP request, service bean, thread, executor, security context hoặc tài nguyên hệ điều hành thường không nên nằm trong value cache. Hãy lưu **dữ liệu cần dùng**, không lưu hạ tầng đang sống.

Có thể dùng `transient` cho một field không cần lưu, nhưng phải hiểu rằng sau khi deserialize, field ấy **không có lại giá trị cũ** trừ khi bạn chủ động tái khởi tạo. Dùng `transient` bừa bãi có thể tạo đối tượng không hợp lệ về mặt nghiệp vụ.

### 5.3. serialVersionUID và nâng cấp class

Đối với những class Serializable thông thường, `serialVersionUID` giúp Java kiểm tra khả năng tương thích phiên bản khi deserialization. Khi thay đổi class hoặc object graph, serialized bytes cũ có thể không còn đọc được và ném lỗi như `InvalidClassException`, dù các field nhìn qua tưởng giống nhau.

Cache `ConcurrentMapCache` là local RAM nên thường mất dữ liệu sau restart; do đó tác động version khác cache lưu lâu trên disk/Redis. Tuy vậy, khi nâng cấp thư viện, hot reload hoặc thay classloader, vẫn phải tính đến khả năng deserialization.

Java records có semantics serialization riêng. Record triển khai `Serializable` có thể dùng canonical constructor khi deserialize; đừng áp dụng mọi giả định về custom `readObject` của class thông thường sang record.

### 5.4. Serializable không đồng nghĩa bất biến hoặc an toàn

- `Serializable` **không làm object immutable**; các setter vẫn thay đổi object được deserialized.
- `Serializable` **không bảo đảm thread-safe**; nếu nhiều thread cùng nắm một object còn mutable, chúng vẫn có thể đua nhau sửa trạng thái.
- `Serializable` **không bảo đảm mọi dữ liệu đều an toàn**; Java native deserialization từ nguồn byte **không tin cậy** có thể gây rủi ro bảo mật nghiêm trọng.
- `Serializable` **không có nghĩa giá trị cache nên có dữ liệu nhạy cảm**. Cần phân quyền, key tenant-safe và chính sách dữ liệu riêng.

Store-by-value ở local `ConcurrentMapCache` nhằm cách ly giá trị, không phải cơ chế mã hóa, phân quyền hoặc truyền dữ liệu an toàn qua mạng.

### 5.5. Nếu không implement Serializable, lỗi xuất hiện khi nào?

Lỗi xuất hiện khi **thực sự serialize value để put vào cache**, không phải khi JVM load class hoặc ngay khi Spring đọc annotation. Một method `@Cacheable` trả value không serializable có thể chạy được phần thân, nhưng bước cache put sau đó thất bại.

Với `ConcurrentMapCache`, bạn thường gặp `IllegalArgumentException` được ném khi không serialize được, bên trong có nguyên nhân serialization như `NotSerializableException`. Không nên dựa vào nguyên văn message/chuỗi stack trace khi viết business logic; hãy xử lý đúng kiểu lỗi, log nguyên nhân và sửa DTO.

## 6. Ví dụ Java 17 chạy được: reference, value và lỗi serialization

Ví dụ này dùng Maven + Java 17 + Spring Framework 6.2.10. Hai Spring contexts độc lập sử dụng `ConcurrentMapCacheManager` trên cache `products`:

1. Context thứ nhất dùng mặc định **store-by-reference**.
2. Context thứ hai bật **store-by-value**.
3. Cả hai dùng `@Cacheable` với cùng key; một biến đếm đo số lần thân phương thức nguồn chạy.
4. Code cố tình mutate object đầu tiên và so sánh những lần cache hit.
5. Cuối cùng code trực tiếp thử put một object **không Serializable** vào cache ở value mode để quan sát lỗi.

### 6.1. Cấu trúc dự án

~~~text
spring-store-by-value/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── StoreByValueDemo.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-store-by-value</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.10</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Không cần Redis hoặc Caffeine. `spring-context` cung cấp `ConcurrentMapCacheManager` và các thành phần Spring Cache/proxy cần thiết cho ví dụ Java Config.

### 6.3. src/main/java/demo/StoreByValueDemo.java

~~~java
package demo;

import java.io.Serializable;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class StoreByValueDemo {

    // Một value có thể mutate và có thể serialize.
    public static final class MutableProduct implements Serializable {
        private static final long serialVersionUID = 1L;

        private String name;

        public MutableProduct(String name) {
            this.name = name;
        }

        public String name() {
            return name;
        }

        public void setName(String newName) {
            this.name = newName;
        }
    }

    // Cố tình không implements Serializable.
    public static final class NotSerializableValue {
        private final String text;

        public NotSerializableValue(String text) {
            this.text = text;
        }

        public String text() {
            return text;
        }
    }

    public static class ProductService {
        private final AtomicInteger loads = new AtomicInteger();

        @Cacheable(cacheNames = "products", key = "#p0")
        public MutableProduct load(String sku) {
            loads.incrementAndGet();
            return new MutableProduct("Book");
        }

        public int loads() {
            return loads.get();
        }
    }

    @Configuration
    @EnableCaching
    public static class ReferenceConfig {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("products");
        }

        @Bean
        public ProductService productService() {
            return new ProductService();
        }
    }

    @Configuration
    @EnableCaching
    public static class ValueConfig {
        @Bean
        public CacheManager cacheManager() {
            ConcurrentMapCacheManager manager =
                new ConcurrentMapCacheManager("products");
            manager.setStoreByValue(true);
            return manager;
        }

        @Bean
        public ProductService productService() {
            return new ProductService();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(
                    ReferenceConfig.class)) {
            ProductService service =
                context.getBean(ProductService.class);

            MutableProduct first = service.load("42");
            System.out.println("REFERENCE:");
            System.out.println("First: " + first.name());
            first.setName("Changed");
            MutableProduct second = service.load("42");
            System.out.println(
                "After caller mutation: " + second.name());
            System.out.println(
                "Same instance: " + (first == second));
            System.out.println("Loads: " + service.loads());
        }

        try (var context =
                new AnnotationConfigApplicationContext(
                    ValueConfig.class)) {
            ProductService service =
                context.getBean(ProductService.class);
            CacheManager manager =
                context.getBean(CacheManager.class);

            MutableProduct first = service.load("42");
            System.out.println("VALUE:");
            System.out.println("First: " + first.name());
            first.setName("Changed");
            MutableProduct second = service.load("42");
            System.out.println(
                "After caller mutation: " + second.name());
            System.out.println(
                "Same instance: " + (first == second));

            second.setName("Changed again");
            MutableProduct third = service.load("42");
            System.out.println(
                "After second mutation: " + third.name());
            System.out.println(
                "Second and third same: " + (second == third));
            System.out.println("Loads: " + service.loads());

            Cache cache = Objects.requireNonNull(
                manager.getCache("products"));

            boolean rejected = false;
            try {
                cache.put("bad", new NotSerializableValue("Oops"));
            } catch (IllegalArgumentException ex) {
                rejected = true;
            }
            System.out.println(
                "Reject non-serializable: " + rejected);
        }
    }
}
~~~

**Cách thiết kế ví dụ:**

- `MutableProduct` có setter và triển khai `Serializable`; field `String name` serializable.
- `NotSerializableValue` cố ý không triển khai `Serializable`.
- `@Cacheable` được đặt trên method public của Spring bean. Các lời gọi `load` đều đi qua bean lấy từ `ApplicationContext`, không phải `new ProductService()` bên ngoài container.
- Hai contexts không chia sẻ cache. Điều này ngăn lần thử store-by-reference ảnh hưởng đến lần thử store-by-value.
- `load("42")` trả "Book" khi thực sự chạy; biến `loads` đo số cache misses đi tới thân phương thức.
- Kiểm tra `cache.put` cho kiểu không serializable dùng cùng cache region ở value mode và bắt `IllegalArgumentException` của chính implementation này. Các provider khác có thể dùng lỗi khác.

### 6.4. Cách chạy

Tại thư mục chứa `pom.xml`, với JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.StoreByValueDemo
~~~

Kết quả **do chương trình in ra** (không tính log Maven):

~~~text
REFERENCE:
First: Book
After caller mutation: Changed
Same instance: true
Loads: 1
VALUE:
First: Book
After caller mutation: Book
Same instance: false
After second mutation: Book
Second and third same: false
Loads: 1
Reject non-serializable: true
~~~

### 6.5. Phân tích từng đoạn kết quả

**REFERENCE:**

1. Lần đầu `load("42")` là cache miss; method tạo một `MutableProduct("Book")` rồi cache giữ **reference** tới object này.
2. Caller sửa `first.name` thành `"Changed"`. Vì `first` là chính object nằm trong cache, entry đang được cache cũng chứa name mới.
3. Lần thứ hai `load("42")` là cache hit; trả object cũ, không chạy thân method. Vì vậy `After caller mutation: Changed`, `Same instance: true` và `Loads: 1`.

**VALUE:**

1. Cache miss đầu tiên trả `first`, đồng thời Spring lưu một snapshot đã serializable vào cache.
2. Caller sửa `first` thành `"Changed"`, nhưng snapshot trong cache được lưu trước mutation nên còn `"Book"`.
3. Lần đọc hit thứ hai deserialize snapshot thành `second`. Nó **không phải cùng instance** với `first`.
4. Caller sửa `second` lần nữa thành `"Changed again"`. Snapshot vẫn không đổi; lần hit tiếp theo tạo `third` với name `"Book"`, không cùng instance với `second`.
5. Bộ đếm vẫn là 1: hai lần cache hit không chạy `load` thật.
6. Khi put `NotSerializableValue`, `ConcurrentMapCache` không thể chuyển nó thành snapshot, nên thao tác bị từ chối và `rejected` thành `true`.

**Kết quả không chứng minh có dữ liệu mới từ repository.** Cả hai mode đều cache trạng thái theo thời điểm lưu; nếu dữ liệu gốc thay đổi, ứng dụng cần invalidation/reload riêng.

## 7. Vì sao chỉ implements Serializable chưa đủ?

### 7.1. Object graph lồng nhau

Một DTO có thể chứa list, map, các object con và tham chiếu vòng:

~~~java
public class CatalogSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;
    private List<ProductSnapshot> products;
}
~~~

Đây là **đoạn minh họa**, chưa có imports/constructor. Nếu những `ProductSnapshot` bên trong không serializable hoặc chứa trường non-serializable mà không được bỏ qua đúng cách, quá trình tuần tự hóa vẫn có thể thất bại. Một `ArrayList` serializable không biến mọi phần tử của nó thành serializable.

Java serialization có cơ chế quản lý object graph, chia sẻ reference và vòng tham chiếu trong cùng luồng; không nên coi nó chỉ là “copy từng field bằng reflection”. Nhưng bạn vẫn phải kiểm soát những loại object nào được đưa vào graph.

### 7.2. Lazy-loaded entity và proxy ORM

JPA/Hibernate entity có thể mang lazy proxy, quan hệ chưa load hoặc tham chiếu vòng. Serialize trực tiếp entity cho cache có thể:

- kích hoạt truy cập dữ liệu không mong đợi;
- thất bại vì proxy hoặc field không serializable;
- tạo snapshot quá lớn;
- lưu trạng thái không còn hợp lệ khi entity detached;
- làm lộ thông tin không muốn trả cho caller.

Thực hành tốt thường là cache **DTO/snapshot có hợp đồng dữ liệu rõ ràng** thay vì cache thẳng managed entity. DTO cho phép xác định trường nào được giữ, giảm graph và dễ kiểm thử.

### 7.3. transient và dữ liệu mất sau deserialize

~~~java
public class SessionView implements Serializable {
    private static final long serialVersionUID = 1L;
    private String displayName;
    private transient Object computedHelper;
}
~~~

Trong class minh họa trên, `computedHelper` không được ghi bởi cơ chế serialization mặc định. Sau deserialize, nó thường ở giá trị mặc định `null`. Nếu method khác luôn tin `computedHelper` tồn tại, cached value có thể gây `NullPointerException` hoặc sai nghiệp vụ.

Vì vậy, đừng dùng `transient` chỉ để “cho serialization hết lỗi” nếu field thực sự cần thiết cho tính đúng.

### 7.4. Cẩn thận với thời điểm ghi

Store-by-value tạo snapshot lúc **put**, không phải một cơ chế theo dõi live object. Nếu method trả object rồi một thread khác sửa object trước hoặc trong quá trình serialization, snapshot có thể phản ánh trạng thái không nhất quán nếu object không được bảo vệ đồng thời.

Khi dữ liệu là mutable và được chia sẻ giữa các thread, cần snapshot bất biến hoặc đồng bộ hóa tại nguồn. Store-by-value **không tự sửa các race condition** trong quá trình xây dựng value.

## 8. Store-by-value có tác động đến key không?

Một cache entry có hai thành phần: **key** và **value**.

Với `ConcurrentMapCache`, chế độ được mô tả ở đây sử dụng serialization khi chuyển **value** vào/ra store. Đây **không phải lời hứa rằng mọi key cũng được clone/serialize**. Key của `ConcurrentHashMap` vẫn phải có `equals`/`hashCode` ổn định suốt thời gian được sử dụng.

Ví dụ nguy hiểm:

~~~java
public final class MutableKey {
    private long id;

    public MutableKey(long id) {
        this.id = id;
    }

    // Giả sử equals/hashCode phụ thuộc vào id.
    public void setId(long id) {
        this.id = id;
    }
}
~~~

Đây là **phản ví dụ**, chưa cung cấp implementation `equals/hashCode`. Nếu object key được đưa vào map rồi bị mutate làm thay đổi `hashCode`, lookup có thể không còn tìm được entry. `setStoreByValue(true)` không bảo đảm cứu được một key thiết kế sai.

**Lời khuyên:** dùng `String`, `Long`, immutable record/composite key có `equals/hashCode` hợp lệ; với cache phân tán còn cần serialization/key format nhất quán giữa các instance.

### Giá trị null

`ConcurrentMapCacheManager` còn có `setAllowNullValues(boolean)`. Mặc định manager có thể dùng internal marker để biểu diễn user-level null vì `ConcurrentHashMap` không lưu null trực tiếp. Đây là cấu hình **khác** với store-by-value.

Nếu dùng `@Cacheable(unless = "#result == null")`, Spring có thể từ chối ghi null ngay ở mức caching advice. `unless` giải quyết việc **có cache null hay không**, không giải quyết việc cache value theo reference hay serialized snapshot.

## 9. Khi nào nên dùng store-by-reference?

Mặc định store-by-reference thích hợp khi:

- Giá trị là **immutable DTO** (hoặc được xử lý như immutable thật sự).
- Object không bị caller sửa sau khi được cache.
- Cần cache local latency thấp, tránh chi phí serialize/deserialize.
- Một số value không serializable nhưng vẫn có thể được chia sẻ an toàn theo reference.
- Có kiểm soát tương tác giữa các thread khi đọc state của object.

Ví dụ record có các thành phần bất biến phù hợp:

~~~java
public record PriceView(
    String sku,
    long priceCents,
    String currency
) {}
~~~

Record này không triển khai `Serializable` nhưng **vẫn có thể cache theo reference** trong `ConcurrentMapCacheManager` mặc định. Với các thành phần `String` và primitive ở đây, không có setter để caller sửa nội dung. Nhưng không phải mọi record đều deep immutable: một record chứa `List` mutable vẫn có thể bị thay đổi qua reference của list.

Đừng coi store-by-reference là lỗi trong mọi trường hợp. Nó là một cơ chế hiệu quả nếu các giá trị cache được thiết kế bất biến hoặc quy ước sử dụng không mutate được đảm bảo bằng code/test.

## 10. Khi nào nên dùng store-by-value?

Chế độ store-by-value hữu ích nếu:

- Caller có khả năng mutate object được trả về và thay đổi đó **không được phép tác động vào cache**.
- Cần mô phỏng semantics snapshot như khi dữ liệu đi qua một tầng serialization.
- Muốn test sớm các yêu cầu `Serializable` của value trước khi dùng một số provider có bước tuần tự hóa.
- Dữ liệu cache tương đối nhỏ, tần suất đọc/ghi chấp nhận được overhead.

Nhưng nó **không tự động** là lựa chọn tốt nhất cho mọi cache:

- Serialization/deserialization trên mỗi lần đọc/ghi tạo allocation và CPU cost.
- Các object graph lớn có thể tốn nhiều byte hơn và tăng GC pressure.
- Java native serialization có chi phí tương thích và bảo mật riêng.
- Cached value vẫn local RAM, không trở thành durable cache hay shared cache.
- Không tự có TTL, max size hoặc eviction theo dung lượng nếu dùng `ConcurrentMapCache` đơn giản.
- Giá trị sau deserialize có thể cần làm lại derived/transient state.

Khi DTO bất biến đã đủ, giữ mặc định by-reference thường đơn giản và hiệu quả hơn.

## 11. Caffeine, Redis và JCache: đừng áp dụng máy móc

### 11.1. Caffeine local

Caffeine thông thường dùng cache in-memory của JVM và trả cùng object reference đã lưu, không dùng Java native serialization-copy tại mỗi cache hit. Bật `setStoreByValue(true)` trên **ConcurrentMapCacheManager** không thay đổi behavior của một `CaffeineCacheManager` khác.

Nếu cần copy khi dùng Caffeine, có thể chọn thiết kế DTO bất biến hoặc viết adapter tạo defensive copy có kiểm soát; đừng trông đợi annotation `@Cacheable` sinh ra copy tự động. Khi dữ liệu có thể thay đổi, nhớ chính sách TTL/evict riêng.

### 11.2. Redis cache

Redis lưu bytes/giá trị được mã hóa ở backend. Trong Spring Data Redis, `RedisCacheConfiguration` cho phép định cấu hình key/value serialization (ví dụ serializer cho JSON hoặc định dạng khác).

Những yêu cầu cần tính:

- Object value được serializer **thực sự hỗ trợ**; không phải serializer nào cũng dùng `java.io.Serializable`.
- Định dạng phải tương thích giữa các phiên bản ứng dụng và giữa instance đọc/ghi.
- Phải kiểm soát type metadata, security khi deserialize, và không dùng deserialization nguy hiểm với dữ liệu không tin cậy.
- Redis serialization không có nghĩa Spring có cùng lựa chọn `setStoreByValue` của ConcurrentMap manager.
- Khi dùng Redis, latency mạng, cluster và TTL là những yếu tố riêng so với local cache.

Nếu chọn JSON serializer, một DTO không `implements Serializable` vẫn có thể được lưu, miễn serializer hiểu và phục dựng được nó. Vì thế câu “mọi cache đều bắt buộc implements Serializable” là **sai**. Điều bắt buộc trong bài này là **ConcurrentMapCache store-by-value dựa trên Java serialization**.

### 11.3. JCache và provider khác

JSR-107/JCache định nghĩa các khái niệm store-by-value và cấu hình cache. Tuy nhiên provider thực tế có thể có hành vi, hạn chế và cơ chế serialize khác nhau. Hãy kiểm tra API/tài liệu của implementation được sử dụng và viết integration test xác nhận object identity và mutation.

Tương tự, Ehcache hoặc cache framework dùng memory/disk tiers có thể sử dụng copier/serializer riêng. Không suy ra “tất cả cache trong RAM đều lưu reference” hay “tất cả cache phân tán đều dùng Java Serializable”.

## 12. Hiệu năng, tính đúng và an toàn

### 12.1. Chi phí tạo bản sao

Thử so sánh một vùng cache thường xuyên trả 100.000 DTO/giây:

- By-reference chỉ phải lookup trong map rồi trả đối tượng đang được giữ.
- By-value phải deserialize snapshot mỗi hit, và serialize value khi put. Nếu object graph lớn, chi phí có thể ảnh hưởng latency P95/P99, throughput và GC.
- Nếu caller chỉ đọc các object thực sự immutable, serialize-copy lặp lại có thể là lãng phí.

Đừng suy ra mức chi phí bằng một tỷ lệ cố định. Cần benchmark với payload và profile thực tế, quan sát allocations, GC, CPU và kích thước dữ liệu.

### 12.2. Không thay thế concurrency control

Với store-by-reference, hai thread có thể nhìn cùng mutable object và race khi mutate. Store-by-value giảm chia sẻ value giữa các lần get, nhưng nó không biến toàn bộ luồng update thành transaction, cũng không cung cấp một khóa phân tán.

Khi cần cập nhật cache theo version và chống lost update, dùng cơ chế versioning/atomic operations do hệ thống thực sự hỗ trợ. `@CachePut` và `@CacheEvict` vẫn có thể cần thiết sau khi data source thay đổi.

### 12.3. Không thay thế authorization

Một value được serialize thành bytes trong local memory vẫn có thể chứa thông tin nhạy cảm. Nếu cache key thiếu tenant/user scope hoặc kết quả phụ thuộc quyền của request, một caller có thể thấy dữ liệu không thuộc phạm vi của họ. Store-by-value không ngăn loại rò rỉ này.

Cần thiết kế key, vùng cache, lifetime và đường kiểm tra quyền theo dữ liệu nghiệp vụ. Không đưa credentials, token, raw session hoặc object chứa secret vào cache nếu không có lý do và biện pháp bảo vệ thích hợp.

### 12.4. Cẩn trọng với native Java serialization

Java deserialization từ nguồn không tin cậy là rủi ro bảo mật. Với nội dung cache local do chính ứng dụng tạo ra, phạm vi threat model khác với dữ liệu nhận qua mạng, nhưng vẫn không nên coi serialized bytes luôn vô hại. Dùng allow-list/filter, serializer phù hợp và kiểm soát nguồn dữ liệu; tránh mở đường deserialize arbitrary bytes từ client.

## 13. Chẩn đoán lỗi thường gặp

| Triệu chứng | Khả năng nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Cache hit trả object bị caller sửa ở chỗ khác | Store-by-reference giữ cùng mutable instance | Dùng immutable DTO, defensive copy hoặc store-by-value phù hợp |
| `Failed to serialize cache value` | Cached value hoặc một field lồng nhau không serializable | Xác định `NotSerializableException`, thu gọn object graph/DTO |
| Class implements Serializable nhưng vẫn lỗi | Một object con trong graph không Serializable | Xác định field/element gây lỗi; đừng chỉ thêm Serializable vào lớp ngoài |
| Sau deserialize một field thành null | Field `transient` hoặc logic khởi tạo không được phục hồi | Thiết kế reinitialization/mapping, không lưu live resource |
| Cache hit nhiều nhưng CPU/GC tăng | Serialize/deserialize mỗi lần hit | Benchmark, dùng immutable value theo reference hoặc provider khác |
| Data source thay đổi nhưng cache vẫn cũ | Thiếu invalidation/TTL, không liên quan store-by-value | Thêm `@CacheEvict`, `@CachePut` và policy vòng đời |
| Thay `setStoreByValue` và cache entry cũ biến mất | Manager reset cache khi thay chế độ | Chọn mode trước traffic, tránh đổi runtime |
| `CacheManager` khác không có `setStoreByValue` | Đây không phải API trên interface chung | Cấu hình provider cụ thể |
| Cache key không tìm lại được sau khi sửa key object | Mutable key có hashCode thay đổi | Dùng immutable key có equals/hashCode ổn định |
| Redis JSON cache được DTO không Serializable | JSON serializer không cần Java Serializable interface | Kiểm tra hợp đồng serializer thay vì ép kiểu chung |
| Không có cache hit dù annotation đúng | Self-invocation hoặc chưa bật caching | Bật `@EnableCaching`, gọi qua Spring proxy, kiểm tra key |
| Lỗi deserialize sau deployment | Class/version/serializer/class loader không tương thích | Thiết kế migration, invalidation, versioned cache namespace |

### Cách tìm lỗi trong ứng dụng thật

1. Xác định **CacheManager đang được dùng thực sự**, thay vì nhìn tên bean một cách suy đoán.
2. Xác nhận `isStoreByValue()` nếu đó là `ConcurrentMapCacheManager`; không gọi API này trên manager khác.
3. Đọc exception root cause từ `Cache.put`/`@Cacheable`, đặc biệt các nguyên nhân serialization.
4. Kiểm tra loại value trả về: DTO, JPA entity, proxy, collection hay class mang resource.
5. Kiểm tra mọi phần tử của graph và các trường `transient`.
6. Dùng integration test qua Spring bean để quan sát hit/miss và object identity.
7. So sánh giá trị ở thời điểm cache put, sau mutation của caller và tại lần cache hit.
8. Nếu có nhiều instance, tách lỗi shared reference nội bộ với vấn đề invalidation liên node.
9. Đo hiệu năng bằng payload điển hình; không bật store-by-value mà bỏ qua chi phí.
10. Xác định policy migration của serialized value nếu đổi kiểu/serializer.

## 14. Checklist thiết kế và kiểm thử

### Trước khi chọn chế độ

- [ ] Cached value là immutable thật sự hay chỉ “mong là không ai sửa”?
- [ ] Caller có thể mutate object sau cache hit không?
- [ ] Có thể trả immutable DTO thay vì cache managed entity không?
- [ ] Ranh giới copy nào là cần thiết: lúc write, lúc read hay cả hai?
- [ ] Provider hỗ trợ copy semantics nào; không giả định mọi manager giống nhau.
- [ ] Có đánh giá CPU, allocations, GC và memory khi serialize/deserialize không?
- [ ] Có chính sách TTL/invalidation riêng để xử lý cập nhật dữ liệu nguồn không?

### Nếu bật ConcurrentMap store-by-value

- [ ] Cấu hình `setStoreByValue(true)` trước khi sử dụng manager.
- [ ] Tất cả cache values có thể được Java serialization.
- [ ] Mọi thành phần object graph cần lưu cũng serializable hoặc được xử lý đúng.
- [ ] Không cache resource sống như streams, connection, executor hay toàn bộ Spring bean.
- [ ] Có test cho giá trị non-serializable và nhánh lỗi dự kiến.
- [ ] Có test caller mutation không làm thay đổi snapshot.
- [ ] Cache key bất biến và có equals/hashCode ổn định.
- [ ] Có chính sách version/migration nếu payload serialized tồn tại qua deploy.
- [ ] Có phân quyền/key scoping khi dữ liệu chứa thông tin nhạy cảm.
- [ ] Có quan sát cache size, hit ratio, error rate và memory.
- [ ] Không nhầm store-by-value với cache phân tán hoặc lưu bền vững.

## 15. Câu hỏi tự kiểm tra

**1.** `ConcurrentMapCacheManager` mặc định lưu theo giá trị hay theo tham chiếu?  
**Đáp án:** Theo tham chiếu (`setStoreByValue(false)`).

**2.** Vì sao caller sửa object trả về có thể làm thay đổi cache khi store-by-reference?  
**Đáp án:** Caller và cache cùng tham chiếu tới một mutable instance.

**3.** `setStoreByValue(true)` sao chép bằng `Object.clone()` hay bằng serialization?  
**Đáp án:** Với `ConcurrentMapCache`, nó sử dụng serialization/deserialization thông qua hạ tầng `SerializationDelegate`.

**4.** Khi bật store-by-value, vì sao cached DTO cần `Serializable`?  
**Đáp án:** Implementation phải serialize object để tạo snapshot được lưu trong map. Object graph cũng cần đáp ứng yêu cầu serialization.

**5.** Record Java tự động triển khai `Serializable` không?  
**Đáp án:** Không. Nếu dùng Java serialization, khai báo `implements Serializable`.

**6.** Store-by-value có tự thay thế `@CacheEvict` khi database đổi không?  
**Đáp án:** Không. Nó chỉ bảo vệ snapshot khỏi mutation của caller; tính tươi của dữ liệu vẫn cần invalidation/TTL.

**7.** Nếu một DTO Serializable chứa `ExecutorService`, việc serialize có chắc chắn thành công không?  
**Đáp án:** Không. Field không serializable có thể khiến cả graph thất bại; cần tách DTO hoặc xử lý field đúng đắn.

**8.** Lần đầu cache miss trong `@Cacheable` trả về object original hay nhất thiết một copy của cache?  
**Đáp án:** Thông thường Spring trả kết quả method đích; snapshot được tạo khi cache put, nên không mặc định kết quả đầu là một bản deserialized từ cache.

**9.** Tại sao `@Cacheable(storeByValue=true)` không hợp lệ?  
**Đáp án:** Annotation chuẩn không có thuộc tính đó; lựa chọn copy thuộc provider/CacheManager.

**10.** Khi dùng Redis với JSON serializer, một DTO không `Serializable` có luôn bị từ chối không?  
**Đáp án:** Không; phụ thuộc hợp đồng của JSON serializer và khả năng encode/decode type đó.

**11.** Store-by-value có đảm bảo cache key mutable sẽ hoạt động an toàn không?  
**Đáp án:** Không. Với ConcurrentMap, key vẫn cần hashCode/equals ổn định.

**12.** Vì sao không bật store-by-value toàn bộ ứng dụng mà không đo đạc?  
**Đáp án:** Serialization/deserialization có CPU, allocation và GC overhead, cùng rủi ro compatibility và runtime errors.

**13.** Khi chuyển store-by-reference sang store-by-value trên manager đang chạy, có thể xảy ra gì với cache cũ?  
**Đáp án:** Manager có thể reset các cache đã tạo để thay đổi policy; không nên đổi mode tùy tiện giữa traffic.

## Tài liệu tham khảo

- Spring Framework 6.2 — `ConcurrentMapCacheManager` Javadoc (setStoreByValue/isStoreByValue): https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html
- Spring Framework 6.2 — `ConcurrentMapCache` Javadoc (store-by-value và SerializationDelegate): https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html
- Spring Framework — Understanding the Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache/strategies.html
- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Oracle Java — Serializable interface: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html
- Oracle Java — Serialization of Records: https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html
- Spring Data Redis — RedisCacheConfiguration Javadoc: https://docs.spring.io/spring-data/redis/reference/cache.html
