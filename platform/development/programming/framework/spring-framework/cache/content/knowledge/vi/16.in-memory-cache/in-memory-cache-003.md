# Hỗ trợ null và lưu theo tham chiếu mặc định trong cache bộ nhớ của Spring

## 1. Hai mặc định cần nắm vững

Khi ứng dụng dùng `ConcurrentMapCacheManager`/`ConcurrentMapCache`, Spring Cache cung cấp một bộ đệm đơn giản dựa trên JDK `ConcurrentMap`, thường với `ConcurrentHashMap` ở bên dưới. Hai đặc tính mặc định quan trọng:

- **`allowNullValues = true`:** Spring chấp nhận lưu kết quả nghiệp vụ `null`. Vì native `ConcurrentHashMap` không cho phép value `null`, cache adapter chuyển `null` thành một **đối tượng đánh dấu nội bộ**, rồi giải mã khi đọc.
- **`storeByValue = false`:** value object được lưu **theo tham chiếu** (*store-by-reference*). Cache và code gọi có thể cùng giữ reference tới **một object mutable**, nên thay đổi trạng thái object có thể làm dữ liệu cache đổi mà không có lệnh `put` mới.

Đây là đặc tính của **implementation và cấu hình cụ thể**. Không được suy ra mọi provider Spring Cache — Redis, Caffeine, JCache hoặc nhà cung cấp riêng — có cùng cơ chế hoặc cùng mặc định.

### Mục tiêu học tập

Sau bài này, bạn có thể giải thích:

1. Tại sao Spring Cache chấp nhận cached-null nhưng `ConcurrentHashMap` lại không.
2. Cách phân biệt entry chưa có với entry chứa giá trị null qua `Cache.ValueWrapper`.
3. Hành vi `@Cacheable` khi method trả null và cách dùng `unless = "#result == null"`.
4. Ý nghĩa lưu theo tham chiếu, hiện tượng *aliasing* và nguy cơ sửa object dùng chung.
5. Cách bật/tắt `setAllowNullValues` và `setStoreByValue`.
6. Vai trò của `Serializable` khi lưu theo giá trị; đánh đổi CPU, bộ nhớ và tính nhất quán.
7. Cách kiểm chứng các hành vi bằng chương trình Java 17 chạy với Spring Framework.

## 2. Cache abstraction, manager và native map

Sơ đồ:

~~~text
Caller / @Cacheable / Cache API
               |
               v
         CacheManager
               |
        getCache("items")
               |
               v
      ConcurrentMapCache
               |
           Key -> Value
               |
               v
    ConcurrentMap<Object, Object>
       (thường dùng JDK ConcurrentHashMap)
~~~

`CacheManager` quản lý những cache có tên. `Cache` quản lý các entry theo key. `ConcurrentMapCache` chuyển đổi giữa giao diện `Cache` của Spring và kiểu lưu trữ `ConcurrentMap`.

Ví dụ cấu hình:

~~~java
@Bean
public CacheManager cacheManager() {
    return new ConcurrentMapCacheManager("items");
}
~~~

Đây là đoạn minh họa trong `@Configuration` của Spring; chưa phải file Java độc lập. Khi dùng API lập trình:

~~~java
Cache cache = Objects.requireNonNull(
        cacheManager.getCache("items"));

Cache.ValueWrapper entry = cache.get("P1");
~~~

Tầng `getCache("items")` là chọn **vùng**, còn `get("P1")` là tra **entry**. Nếu `getCache` trả `null` thì vùng cache không được cung cấp; nếu `get` trả `null` thì **entry không có mapping**. Hai kiểu null này không có cùng ý nghĩa.

### Không nhầm null value với null key

`ConcurrentHashMap` cấm cả `null` key và `null` value. Spring's `allowNullValues` chỉ xử lý **user-level null value**, không có nghĩa API sẽ hỗ trợ `cache.put(null, value)`. Hãy dùng key ổn định, non-null, có `equals/hashCode` phù hợp.

## 3. Vì sao ConcurrentMapCache hỗ trợ null?

### 3.1. Native ConcurrentHashMap không chấp nhận null

Code Java bình thường:

~~~java
Map<String, Object> raw = new ConcurrentHashMap<>();
raw.put("missing", null); // ném NullPointerException
~~~

Đoạn này cần import `Map` và `ConcurrentHashMap`. Trong native map, `get(key) == null` là dấu hiệu không tìm thấy mapping. Do đó không thể dùng `null` trực tiếp làm value.

### 3.2. Spring sử dụng một marker

Với `ConcurrentMapCacheManager` mặc định:

~~~java
Cache cache = manager.getCache("items");
cache.put("missing", null);
~~~

Spring đi qua các bước khái niệm:

~~~text
Ứng dụng gọi Cache.put("missing", null)
                 |
                 v
    Spring chuyển user-level null
    thành một đối tượng marker
                 |
                 v
 ConcurrentHashMap["missing"] = marker
                 |
                 v
  Cache.get("missing") trả ValueWrapper
                 |
                 v
  ValueWrapper.get() trả user-level null
~~~

Spring có `org.springframework.cache.support.NullValue` để đại diện nội bộ cho null. Bạn **không nên thao tác với marker** như kiểu dữ liệu nghiệp vụ, và không nên lấy raw value rồi cast trực tiếp sang DTO; hãy dùng API `Cache` để Spring chuyển đổi.

Theo Javadoc `ConcurrentMapCacheManager`, `setAllowNullValues(boolean)` mặc định là `true`; một holder nội bộ được dùng vì native `ConcurrentHashMap` không hỗ trợ null.

### 3.3. Phân biệt miss và cached-null

~~~java
Cache.ValueWrapper missing = cache.get("P1"); // chưa put -> null

cache.put("P1", null);
Cache.ValueWrapper cachedNull = cache.get("P1");

// cachedNull != null: entry tồn tại.
// cachedNull.get() == null: value nghiệp vụ là null.
~~~

Bảng phân biệt:

| Trạng thái | `cache.get(key)` | `wrapper.get()` | Kết luận |
| --- | --- | --- | --- |
| Chưa có entry | `null` | Không thể gọi | Cache miss |
| Entry có user-level null | Wrapper khác `null` | `null` | Cache hit với null |
| Entry có `"item-A"` | Wrapper khác `null` | `"item-A"` | Cache hit bình thường |

Cách kiểm tra không nhầm lẫn:

~~~java
Cache.ValueWrapper wrapper = cache.get(key);
if (wrapper == null) {
    // Chưa có entry.
} else if (wrapper.get() == null) {
    // Có entry, value đã được cache là null.
} else {
    // Có entry, value khác null.
}
~~~

Những snippet trên giả định biến `cache` và `key` đã được khai báo.

### 3.4. Typed lookup không phân biệt được

~~~java
String value = cache.get("P1", String.class);
~~~

`value == null` **không chứng minh** cache miss: đó có thể là cached-null. Khi cần phân biệt, dùng `Cache.ValueWrapper` của `get(Object)`. Đây là khác biệt thực tế khi viết logic fallback, thống kê hit/miss và xử lý giá trị không tìm thấy.

## 4. Spring @Cacheable và negative caching

Method có thể trả null:

~~~java
@Cacheable(cacheNames = "items", key = "#p0")
public String findDescription(String sku) {
    return repository.findDescription(sku); // có thể null
}
~~~

Đây là snippet minh họa, chưa độc lập vì cần `repository` và cấu hình Spring.

Với manager cho phép null, giả sử SKU `"P404"` không có:

~~~text
Lần 1 findDescription("P404")
  -> Cache MISS
  -> chạy repository.findDescription
  -> nhận null
  -> Spring ghi null-marker cho key P404
  -> caller nhận null

Lần 2 findDescription("P404")
  -> Cache HIT với null-marker
  -> caller nhận null
  -> KHÔNG chạy repository.findDescription
~~~

Đây là **negative caching**: cache sự vắng mặt của dữ liệu. Lợi ích là giảm tải khi một key không tồn tại bị truy vấn liên tục. Rủi ro: nếu record vừa được tạo trong database mà cached-null chưa bị xóa/hết hạn, ứng dụng vẫn trả null.

### 4.1. Bỏ qua kết quả null bằng unless

~~~java
@Cacheable(
    cacheNames = "items",
    key = "#p0",
    unless = "#result == null"
)
public String findDescription(String sku) {
    return repository.findDescription(sku);
}
~~~

`unless` được tính **sau khi method trả kết quả**; khi result là null thì Spring bỏ qua put. Lần gọi tiếp theo phải tải lại. Trái lại, `condition` kiểm tra điều kiện **trước invocation** và không sử dụng giá trị trả về làm căn cứ.

| Lựa chọn | Trả null lần đầu | Lần gọi sau cùng key |
| --- | --- | --- |
| Mặc định, provider cho lưu null | Lưu null-marker | Cache hit, method có thể được bỏ qua |
| `unless = "#result == null"` | Không lưu | Miss, method chạy lại |
| `setAllowNullValues(false)` nhưng không có veto | Có thể lỗi lúc ghi null | Không nên phụ thuộc hành vi thành công |
| `setAllowNullValues(false)` cùng veto null | Không lưu null | Miss lần sau, method chạy lại |

Nếu return type là `Optional<T>`, Spring Cache thường unwrap `Optional`: `Optional.empty()` được biểu diễn dưới dạng user-level null ở cache. Vì vậy quyết định cache null vẫn quan trọng khi method dùng `Optional`.

### 4.2. Tình huống nên và không nên cache null

Cache null hợp lý khi kết quả “không tồn tại” ổn định, chi phí lookup cao, có kế hoạch TTL/invalidation. Không nên cache null quá lâu nếu record mới xuất hiện thường xuyên, hoặc null đang bị dùng để biểu diễn **lỗi timeout, không đủ quyền, service tạm ngừng**.

Không dùng cache null chia sẻ giữa các user/tenant khi quyền truy cập tác động đến kết quả. Một user không được phép xem dữ liệu không nên khiến user có quyền nhận cached-null chỉ vì hai request trùng key.

## 5. Store-by-reference mặc định là gì?

Với `ConcurrentMapCacheManager` mặc định:

~~~java
manager.isStoreByValue(); // false
~~~

`storeByValue=false` có nghĩa value được giữ bằng **reference**, không tạo bản sao của object. Nếu code khác đang giữ cùng reference và value mutable, sửa object **thay đổi trạng thái mà cache nhìn thấy**.

~~~text
Caller
  local variable "box"
            |
            v
     +--------------+
     | MutableBox   |
     | amount = 100 |
     +--------------+
            ^
            |
   Cache["box"] giữ reference
   tới đúng object ở trên
~~~

Ví dụ:

~~~java
final class MutableBox {
    int amount;
    MutableBox(int amount) { this.amount = amount; }
}

MutableBox box = new MutableBox(100);
cache.put("box", box);

box.amount = 150;
MutableBox fromCache = cache.get("box", MutableBox.class);

System.out.println(fromCache.amount);  // 150
System.out.println(fromCache == box);   // true
~~~

Snippet này minh họa với cache đang cấu hình store-by-reference và biến `cache` đã khai báo. Không có `cache.put` lần thứ hai; object được thay đổi qua reference ngoài cache.

### 5.1. Sửa object trả về từ cache có thể ảnh hưởng mọi caller

~~~java
MutableBox first = cache.get("box", MutableBox.class);
first.amount = 999;

MutableBox second = cache.get("box", MutableBox.class);
System.out.println(second.amount); // 999 nếu cùng reference
~~~

Một endpoint có thể nhận DTO mutable từ `@Cacheable`, sau đó sửa field để hiển thị. Nếu đó là chính object cached, request khác sẽ nhìn thấy field bị sửa — dù database, transaction và `@CachePut` không hề chạy. Đây là **cache pollution** do chia sẻ reference.

### 5.2. Không tự động đồng bộ database

Việc field của object cache chuyển từ 100 sang 150 không chứng minh database đã lưu 150. Cache chỉ nhìn thấy cùng object. Ngược lại, database có thể đổi nhưng reference cached vẫn mang dữ liệu cũ nếu không có logic invalidation/reload. Không dùng mutable reference như một cơ chế cập nhật dữ liệu gốc.

### 5.3. ConcurrentMap không làm value thread-safe

`ConcurrentHashMap` bảo vệ cấu trúc map trong thao tác đồng thời, **không bảo đảm thread safety của object được lưu**. Nếu value chứa `ArrayList`, `HashMap` hoặc nhiều field mutable, các reader/writer có thể quan sát trạng thái trung gian hoặc race.

Muốn cập nhật nhất quán, hãy lưu **snapshot bất biến** rồi thay toàn bộ entry. Một `record` có component mutable (array/list) vẫn chưa deep-immutable; cần copy cả object graph khi cần bảo vệ dữ liệu.

### 5.4. Đừng dùng key mutable

Dù chủ đề là *reference của value*, key cũng có rủi ro riêng: một key object đổi `hashCode()/equals()` sau khi put có thể làm lookup thất bại. Dùng key như `String`, `UUID` hoặc record chứa thành phần bất biến, không lấy DTO mutable làm key.

## 6. Hai cờ cấu hình độc lập

`ConcurrentMapCacheManager` cung cấp:

~~~java
ConcurrentMapCacheManager manager =
        new ConcurrentMapCacheManager("items");

manager.setAllowNullValues(false); // Từ chối user-level null.
manager.setStoreByValue(true);    // Sao chép value bằng serialization.
~~~

Không bắt buộc bật/tắt cả hai; chúng giải quyết hai vấn đề khác nhau:

| Cờ | Mặc định | Khi thay đổi | Ý nghĩa |
| --- | --- | --- | --- |
| `allowNullValues` | `true` | `false` | Không cho cache user-level null |
| `storeByValue` | `false` | `true` | Serialize/copy value thay vì chia sẻ reference |

### 6.1. Tắt cached-null

~~~java
@Bean
public CacheManager cacheManager() {
    ConcurrentMapCacheManager manager =
            new ConcurrentMapCacheManager("items");
    manager.setAllowNullValues(false);
    return manager;
}
~~~

Nếu sau đó gọi `cache.put("A", null)`, `ConcurrentMapCache` từ chối value null (thường ném `IllegalArgumentException`). Khi dùng `@Cacheable` mà kết quả có thể null, hãy kết hợp `unless = "#result == null"` hoặc thiết kế trả về một giá trị nghiệp vụ non-null.

### 6.2. Lưu theo giá trị: storeByValue=true

~~~java
@Bean
public CacheManager cacheManager() {
    ConcurrentMapCacheManager manager =
            new ConcurrentMapCacheManager("items");
    manager.setStoreByValue(true);
    return manager;
}
~~~

Khi bật `storeByValue=true`, `ConcurrentMapCacheManager` dùng serialization để tạo **bản sao khi lưu** và trả một **bản sao khi lấy**. Cached values cần thỏa `Serializable`; các field con của object graph cũng phải serialize được. Nếu không, thao tác cache có thể ném lỗi runtime.

Ví dụ class phù hợp:

~~~java
public static final class MutableBox implements Serializable {
    private static final long serialVersionUID = 1L;
    private int amount;

    public MutableBox(int amount) { this.amount = amount; }
    public int getAmount() { return amount; }
    public void setAmount(int amount) { this.amount = amount; }
}
~~~

Snippet cần import `java.io.Serializable` và phải nằm ở nơi hợp lệ trong mã Java. Bản sao tách biệt reference; sửa object gốc sau put **không** ảnh hưởng snapshot đang lưu, và sửa bản copy sau get **không** làm cache thay đổi.

### 6.3. Bật store-by-value không tự động có TTL, Redis hay persistence

Serialization trong `ConcurrentMapCacheManager` vẫn làm việc **trong JVM hiện tại**. Không có nghĩa dữ liệu được chia sẻ qua network, tự lưu trên ổ đĩa, tự tồn tại sau restart hoặc tự hết hạn theo TTL.

Đánh đổi: store-by-value cần serialize/deserialize, tốn CPU, cấp phát bộ nhớ và có thể gặp lỗi tương thích class/schema. Nếu value vốn immutable, store-by-reference thường tiết kiệm hơn mà vẫn an toàn trước mutation.

### 6.4. Config trước khi dùng, không đổi flags nóng

Theo Javadoc, thay `setAllowNullValues` hoặc `setStoreByValue` có thể **reset các cache đã tạo** để cấu hình lại. Điều này có thể mất entries và làm thay đổi object `Cache` được giữ ở nơi khác.

Cấu hình hai cờ khi xây `CacheManager` bean, trước khi đưa cache vào phục vụ request. Không dùng chúng như công tắc runtime để chuyển chính sách trên một cache đang hoạt động.

## 7. Demo hoàn chỉnh Java 17: null marker và reference/copy

Project dưới đây sử dụng **Spring Framework 6.2.16**, Java 17 và Maven. Không cần Spring Boot, database hoặc Redis. Demo kiểm chứng:

1. Manager mặc định `allowNullValues=true`, `storeByValue=false`.
2. `get(key)` trả null khi miss, nhưng non-null `ValueWrapper` nếu đã cache null.
3. Native `ConcurrentMap` giữ marker khác null.
4. Object mutable được lưu cùng reference.
5. `@Cacheable` cache kết quả null, còn `unless` ngăn lưu null.
6. Manager cấu hình `setAllowNullValues(false)` từ chối null.
7. Manager khác cấu hình `setStoreByValue(true)` tạo bản sao serializable.

### 7.1. Cấu trúc

~~~text
in-memory-null-reference/
├── pom.xml
└── src/main/java/demo/InMemoryCacheDemo.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>in-memory-null-reference</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.16</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.3. src/main/java/demo/InMemoryCacheDemo.java

~~~java
package demo;

import java.io.Serializable;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class InMemoryCacheDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public ConcurrentMapCacheManager cacheManager() {
            return new ConcurrentMapCacheManager("items");
        }

        @Bean
        public LookupService lookupService() {
            return new LookupService();
        }
    }

    public static class LookupService {
        private final AtomicInteger loads = new AtomicInteger();
        private final AtomicInteger vetoLoads = new AtomicInteger();

        @Cacheable(cacheNames = "items", key = "#p0")
        public String find(String key) {
            int n = loads.incrementAndGet();
            System.out.println("LOAD " + key + " #" + n);
            return null;
        }

        @Cacheable(
                cacheNames = "items",
                key = "'skip:' + #p0",
                unless = "#result == null")
        public String findWithoutNullCache(String key) {
            int n = vetoLoads.incrementAndGet();
            System.out.println("VETO_LOAD " + key + " #" + n);
            return null;
        }

        public int loadCount() {
            return loads.get();
        }
    }

    public static final class MutableBox implements Serializable {
        private static final long serialVersionUID = 1L;
        private int amount;

        public MutableBox(int amount) {
            this.amount = amount;
        }

        public int getAmount() {
            return amount;
        }

        public void setAmount(int amount) {
            this.amount = amount;
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            ConcurrentMapCacheManager manager =
                    context.getBean(ConcurrentMapCacheManager.class);
            LookupService service =
                    context.getBean(LookupService.class);
            Cache cache = Objects.requireNonNull(
                    manager.getCache("items"));

            System.out.println("allowNull="
                    + manager.isAllowNullValues());
            System.out.println("storeByValue="
                    + manager.isStoreByValue());

            // Một entry miss khác với entry đã cache null.
            System.out.println("initialMiss="
                    + (cache.get("nil") == null));
            cache.put("nil", null);
            Cache.ValueWrapper wrapper = cache.get("nil");
            System.out.println("nullEntry="
                    + (wrapper != null));
            System.out.println("nullValue="
                    + (wrapper != null && wrapper.get() == null));

            ConcurrentMapCache nativeCache =
                    (ConcurrentMapCache) cache;
            System.out.println("nativeHasMarker="
                    + (nativeCache.getNativeCache().get("nil") != null));

            // Store-by-reference: cùng object mutable.
            MutableBox shared = new MutableBox(1);
            cache.put("box", shared);
            System.out.println("sameReference="
                    + (cache.get("box", MutableBox.class) == shared));
            shared.setAmount(7);
            System.out.println("afterExternalMutation="
                    + Objects.requireNonNull(
                            cache.get("box", MutableBox.class))
                            .getAmount());

            // @Cacheable: null được lưu thành cached-null.
            System.out.println("lookup1=" + service.find("X"));
            System.out.println("lookup2=" + service.find("X"));
            System.out.println("loadCount=" + service.loadCount());
            System.out.println("annotatedNullEntry="
                    + (cache.get("X") != null));

            // unless: không lưu kết quả null.
            System.out.println("veto1="
                    + service.findWithoutNullCache("X"));
            System.out.println("veto2="
                    + service.findWithoutNullCache("X"));
            System.out.println("vetoHasEntry="
                    + (cache.get("skip:X") != null));

            // Manager khác: từ chối lưu null.
            ConcurrentMapCacheManager strict =
                    new ConcurrentMapCacheManager("strict");
            strict.setAllowNullValues(false);
            Cache strictCache = Objects.requireNonNull(
                    strict.getCache("strict"));
            System.out.println("strictAllowNull="
                    + strict.isAllowNullValues());

            boolean strictRejected = false;
            try {
                strictCache.put("nil", null);
            } catch (IllegalArgumentException expected) {
                strictRejected = true;
            }
            System.out.println("strictRejected=" + strictRejected);

            // Manager store-by-value: value phải Serializable.
            ConcurrentMapCacheManager copies =
                    new ConcurrentMapCacheManager("copies");
            copies.setStoreByValue(true);
            Cache copyCache = Objects.requireNonNull(
                    copies.getCache("copies"));
            MutableBox original = new MutableBox(1);
            copyCache.put("box", original);

            System.out.println("copyMode="
                    + copies.isStoreByValue());
            System.out.println("copySameReference="
                    + (copyCache.get("box", MutableBox.class)
                            == original));

            original.setAmount(9);
            System.out.println("copyAfterOriginalMutation="
                    + Objects.requireNonNull(
                            copyCache.get("box", MutableBox.class))
                            .getAmount());

            MutableBox returned = Objects.requireNonNull(
                    copyCache.get("box", MutableBox.class));
            returned.setAmount(6);
            System.out.println("copyAfterReturnedMutation="
                    + Objects.requireNonNull(
                            copyCache.get("box", MutableBox.class))
                            .getAmount());
        }
    }
}
~~~

### 7.4. Chạy bằng Maven

Trong thư mục `in-memory-null-reference`, cần JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.InMemoryCacheDemo
~~~

Stdout dự kiến do **chương trình** in (không tính thông báo riêng của Maven/JVM):

~~~text
allowNull=true
storeByValue=false
initialMiss=true
nullEntry=true
nullValue=true
nativeHasMarker=true
sameReference=true
afterExternalMutation=7
LOAD X #1
lookup1=null
lookup2=null
loadCount=1
annotatedNullEntry=true
VETO_LOAD X #1
veto1=null
VETO_LOAD X #2
veto2=null
vetoHasEntry=false
strictAllowNull=false
strictRejected=true
copyMode=true
copySameReference=false
copyAfterOriginalMutation=1
copyAfterReturnedMutation=1
~~~

### 7.5. Đối chiếu các nhóm hành vi

**Null và marker:** `initialMiss=true` do chưa có key. Sau `put("nil", null)`, `nullEntry=true` nhưng `nullValue=true`; native map giữ marker nên `nativeHasMarker=true`. Caller không cần biết marker là class gì.

**Reference:** `sameReference=true` cho thấy cache giữ cùng instance như `shared`. Sau khi gọi `shared.setAmount(7)`, getter cho amount 7 dù không put lại.

**Cache annotation:** `LOAD X #1` chỉ in một lần. Lần gọi `lookup2` trả null bằng cache hit. `annotatedNullEntry=true` xác nhận entry đã tồn tại. Ngược lại, `VETO_LOAD` in hai lần và `vetoHasEntry=false` vì `unless` ngăn lưu null.

**Cấu hình strict:** `strictAllowNull=false` và `strictRejected=true` chứng minh cache khác từ chối null. Các cờ cấu hình không tác động ngược sang manager mặc định của Spring context.

**Store-by-value:** `copyMode=true` và `copySameReference=false` vì cache lưu/trả bản sao. Thay đổi object `original` hoặc object vừa lấy ra không đổi snapshot đang cache: cả `copyAfter...` đều là 1.

**Proxy:** method `find` nằm trong Spring-managed bean, được lấy từ context, nên `@Cacheable` có hiệu lực. Nếu tạo `new LookupService()` ngoài Spring, annotation không tự thực hiện cache lookup.

## 8. Thiết kế an toàn cho production

### 8.1. Chọn chính sách cho null có chủ đích

Nếu “không tìm thấy” tương đối ổn định và truy vấn đắt, cached-null có thể hữu ích. Nếu record mới có thể xuất hiện ngay sau đó, null marker dễ stale. Cách xử lý:

- Dùng `unless = "#result == null"` để không lưu null.
- Chủ động evict đúng key khi tạo mới record.
- Dùng provider có TTL và giới hạn cache size phù hợp.
- Tách lỗi kỹ thuật khỏi kết quả “không có dữ liệu”; không cache lỗi timeout như null hợp lệ.

Một `ConcurrentMapCache` thuần **không cung cấp TTL tự động**; cached-null có thể tồn tại tới khi bị xóa/clear hoặc JVM kết thúc.

### 8.2. Trả DTO immutable khi có thể

Với store-by-reference, ưu tiên DTO không setter và có cấu trúc sâu bất biến. Một `record` chứa mutable collection vẫn có thể bị sửa thông qua collection. Nếu không kiểm soát được caller, trả defensive copy hoặc chọn store-by-value khi serialization phù hợp.

### 8.3. Thread safety và consistency

`ConcurrentHashMap` không bảo vệ invariant của value mutable. Nếu người đọc/ghi ở nhiều thread, nên thay toàn bộ value bằng snapshot immutable thay vì sửa vài field của một object dùng chung.

### 8.4. Kiểm tra đúng manager thực tế

Trong Spring Boot, manager được auto-configure phụ thuộc classpath/config; không được giả định mọi ứng dụng Boot đều dùng `ConcurrentMapCacheManager`. Xem bean `CacheManager` đang được inject thực sự, provider và flags của nó trước khi suy luận null/reference semantics.

### 8.5. Không xem in-memory cache là distributed cache

Một manager local ở instance A không chia sẻ reference với manager ở instance B. Khi có nhiều replica, cache TTL, eviction, memory và consistency phải được thiết kế riêng; store-by-value không tự tạo replication.

### 8.6. Không đổi flags giữa giờ phục vụ

`setAllowNullValues` và `setStoreByValue` có thể reset các cache hiện có. Khai báo cấu hình một lần khi tạo bean; nếu cần đổi chính sách production, phải xét migration của cached entries, downtime, warm-up và thử nghiệm.

## 9. Checklist kiểm thử

| Tình huống | Kiểm chứng |
| --- | --- |
| Mặc định của manager | `isAllowNullValues()==true`; `isStoreByValue()==false` |
| Cache miss | `cache.get(key)==null` |
| Cached-null | `cache.put(key,null)` rồi wrapper khác null và `get()==null` |
| Typed get | `cache.get(key, String.class)==null` không đủ kết luận miss |
| Native map | Marker được lưu thay cho Java null |
| Reference | Object gốc và cached object là cùng instance |
| Mutation | Sửa object gốc làm kết quả get đổi nếu store-by-reference |
| @Cacheable null | Hai lần gọi cùng key, body chỉ chạy một lần |
| unless null | Hai lần cùng key, body chạy hai lần |
| Từ chối null | `setAllowNullValues(false)` trước put, null bị từ chối |
| Copy mode | `setStoreByValue(true)` với value Serializable, get không trả cùng reference |
| Serializability | Không serializable có thể gây lỗi |
| Thay đổi flags | Xác nhận cached entries có thể bị reset |
| Nhiều instance | Không có tự động đồng bộ trong JVM khác |

Unit test chỉ so sánh `equals` không đủ để xác định copy/reference; hãy kiểm tra identity bằng `==`/`assertSame` và thay đổi state trong test. Khi test cached-null, phải kiểm tra `ValueWrapper` chứ không chỉ so sánh giá trị method trả về.

## 10. Lỗi thường gặp

**“ConcurrentHashMap không nhận null thì @Cacheable không thể cache null.”** Sai trong `ConcurrentMapCacheManager` mặc định: Spring dùng holder nội bộ cho null value.

**“Cache.get(key) trả null tức là entry chứa null.”** Sai ở dạng trả `ValueWrapper`: `null` wrapper là miss; non-null wrapper có thể chứa null.

**“Cache.get(key, Type.class) trả null chắc chắn miss.”** Không chắc: typed lookup không phân biệt cached-null và miss.

**“Sửa DTO trả về từ cache chỉ ảnh hưởng request hiện tại.”** Không đúng nếu cache giữ cùng reference. Dùng immutable snapshot, defensive copy hoặc store-by-value.

**“ConcurrentMapCache thread-safe nghĩa là mọi value cũng thread-safe.”** Sai: map-level concurrency không làm object mutable bên trong an toàn.

**“Bật storeByValue=true là có Redis/TTL/persistence.”** Sai: đây chỉ là chiến lược copy bằng serialization ở local cache.

**“Tắt allowNullValues là đủ để phương thức trả null được bỏ qua.”** Không mặc nhiên; hãy dùng `unless` hoặc đảm bảo phương thức không tạo kết quả null cần put.

**“Thay flags sau khi cache đã có data không ảnh hưởng gì.”** Sai. Manager có thể reset cache và entries khi thay những cờ này.

## 11. Câu hỏi tự kiểm tra

1. **Vì sao Spring có thể lưu user-level null trong native ConcurrentHashMap?** Vì adapter chuyển null thành một marker không null, rồi giải mã khi đọc.
2. **Khác biệt giữa `cache.get("A")==null` và `wrapper.get()==null`?** Trường hợp đầu là miss; trường hợp sau, nếu wrapper tồn tại, là cached-null hit.
3. **Vì sao method @Cacheable trả null có thể chỉ chạy một lần?** Vì null đã được cache như một entry có marker, nên lần sau hit.
4. **Điều gì thay đổi khi dùng `unless="#result == null"`?** Spring không put result null; lần sau vẫn có thể miss.
5. **Tại sao sửa object ở bên ngoài cache lại làm value cached thay đổi?** Vì mặc định cache giữ cùng reference tới object mutable.
6. **Bật `setStoreByValue(true)` cần điều kiện gì?** Value phải serialize được, chấp nhận chi phí copy và kiểm tra tương thích schema.
7. **`setAllowNullValues(false)` có làm object không còn chia sẻ reference không?** Không. Hai cờ độc lập.
8. **Store-by-value có tự động an toàn cho cluster không?** Không; nó không thay thế backend phân tán/TTL/invalidation.

## 12. Kết luận

Với cache trong bộ nhớ dựa trên `ConcurrentMapCacheManager`, hai mặc định phải được xem là quyết định kỹ thuật có tác động tới hành vi nghiệp vụ:

- **`allowNullValues=true`:** kết quả null được cache qua marker; phải dùng `Cache.ValueWrapper` để phân biệt hit null với miss.
- **`storeByValue=false`:** value được giữ theo reference; caller mutate object có thể làm thay đổi dữ liệu cache không chủ ý.

Chọn chính sách null có cân nhắc negative-cache staleness, và chọn mô hình lưu value có cân nhắc tính mutable, concurrency, serialization và chi phí vận hành. Cache abstraction giúp đơn giản hóa API, nhưng không loại bỏ những đặc tính riêng của provider.

## Tài liệu chính thức

- Spring Framework 6.2 — Cache Abstraction: https://docs.spring.io/spring-framework/reference/6.2/integration/cache.html
- Spring Framework 6.2 — Configuring Cache Storage: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/store-configuration.html
- ConcurrentMapCacheManager Javadoc (6.2.16): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html
- ConcurrentMapCache Javadoc (6.2.18): https://www.springframework.org/spring/docs/6.2.18/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html
- Spring Cache API Javadoc (6.2.16): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/Cache.html
- Declarative Caching (6.2): https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
