# Vì sao tên phương thức không tự nằm trong khóa mặc định của Spring Cache?

## Mục tiêu

Bài học giải thích cách Spring Cache tạo khóa mặc định từ tham số, vì sao tên phương thức không tự động là một phần của khóa, hậu quả khi các phương thức khác nhau dùng chung vùng cache và cùng khóa, cùng các cách thiết kế key an toàn. Sau bài, bạn có thể tự chạy một ví dụ Java 17, nhận diện kết quả sai vì cache hit ngoài ý muốn, rồi khắc phục bằng `cacheNames`, SpEL `key` hoặc `KeyGenerator`.

## 1. Trả lời trực tiếp

Khi dùng `@Cacheable` mà không chỉ định `key` hay `keyGenerator`, Spring thường sử dụng `SimpleKeyGenerator`. Thuật toán **dựa vào các đối số thực tế của lời gọi**. Nó không mặc định thêm tên method, tên class, tên bean hay kiểu trả về vào key.

Ví dụ:

~~~java
@Cacheable(cacheNames = "shared")
public String findUserName(String id) {
    return "USER:" + id;
}

@Cacheable(cacheNames = "shared")
public String findProductName(String id) {
    return "PRODUCT:" + id;
}
~~~

Đây là đoạn minh họa, chưa phải chương trình độc lập. Hai lời gọi `findUserName("42")` và `findProductName("42")` tạo cùng key `"42"`. Nếu cùng dùng một cache `shared`, chúng truy vấn **cùng entry**, bất kể tên phương thức khác nhau:

~~~text
findUserName("42")       findProductName("42")
        |                         |
        +------------+------------+
                     |
          Cache name = "shared"
          Default key = "42"
                     |
                     v
             Cache("shared").get("42")
~~~

Khi `findUserName("42")` chạy trước, nó có thể lưu `"USER:42"`. Sau đó `findProductName("42")` gặp cache hit và trả luôn `"USER:42"`; thân phương thức thứ hai **không chạy**. Đây là nguy cơ sai dữ liệu do hai operation khác nhau dùng chung một địa chỉ cache logic.

Ba khái niệm phải phân biệt:

- **Cache name (`cacheNames`)**: xác định vùng cache, ví dụ `"shared"`, `"users"` hay `"products"`.
- **Cache key**: định danh entry bên trong vùng ấy, ví dụ chuỗi `"42"`.
- **Method name**: tên phương thức Java. Nó có thể được custom generator sử dụng, nhưng **không tự là thành phần của key mặc định**.

Có thể hình dung địa chỉ logic của entry là cặp **(vùng cache đã resolve, key)**. Tên method không tự tạo một vùng lưu trữ mới.

## 2. SimpleKeyGenerator mặc định hoạt động như thế nào?

`org.springframework.cache.interceptor.SimpleKeyGenerator` tạo key theo số lượng và giá trị tham số:

| Tham số của lời gọi | Key mặc định | Ví dụ |
| --- | --- | --- |
| Không có tham số | `SimpleKey.EMPTY` | `getConfig()` |
| Một tham số khác null, không phải mảng | Chính đối tượng tham số | `find("42")` → `"42"` |
| Từ hai tham số trở lên | `SimpleKey` chứa toàn bộ tham số theo thứ tự | `find("42", "vi")` |
| Một tham số null hoặc mảng | `SimpleKey` bọc danh sách tham số | Cần lưu ý trường hợp biên |

Tài liệu hướng dẫn thường diễn đạt giản lược thành 0/1/nhiều tham số; Javadoc và implementation có chi tiết về một tham số null hoặc mảng. Khi kết quả key thực tế quan trọng, hãy kiểm tra đúng phiên bản đang chạy.

Có thể gọi API tĩnh như sau:

~~~java
Object key0 = org.springframework.cache.interceptor
        .SimpleKeyGenerator.generateKey();
Object key1 = org.springframework.cache.interceptor
        .SimpleKeyGenerator.generateKey("42");
Object key2 = org.springframework.cache.interceptor
        .SimpleKeyGenerator.generateKey("42", "vi");
~~~

Đây là snippet sử dụng Spring API: `key0` là `SimpleKey.EMPTY`; `key1` là chuỗi `"42"`; `key2` là `SimpleKey` gồm hai phần tử. Không cần truyền tên method cho ba phép tạo key ấy.

Cùng kiểu tham số nhưng khác giá trị thường tạo key khác. Ngược lại, **hai method khác nhau với cùng giá trị tham số** vẫn có thể tạo key bằng nhau.

### Vì sao KeyGenerator nhận được Method nhưng không tự dùng tên method?

Giao diện mở rộng:

~~~java
public interface KeyGenerator {
    Object generate(Object target,
                    java.lang.reflect.Method method,
                    Object... params);
}
~~~

Đoạn trên thể hiện chữ ký thực của interface để giải thích, không yêu cầu bạn tự khai báo lại trong ứng dụng.

Spring cung cấp cả `target` và `method` để các implementation **có khả năng** xây dựng key tùy biến. Nhưng `SimpleKeyGenerator` mặc định chọn dựa trên `params`. Vì vậy **việc Spring biết method đang chạy** và **việc method name được đưa vào key** là hai chuyện khác nhau.

Đây không phải lỗi framework. Key generation là chính sách ứng dụng có thể tùy chỉnh, còn `cacheNames` đã giúp tổ chức không gian lưu trữ. Khi một vùng cache chứa nhiều loại kết quả khác nhau, lập trình viên phải chủ động định nghĩa danh tính entry phù hợp.

## 3. Tại sao thiết kế key theo tham số vẫn hữu ích?

Giả sử có hai vùng cache riêng:

~~~java
@Cacheable(cacheNames = "users")
public User findUser(String userId) {
    return userRepository.find(userId);
}

@Cacheable(cacheNames = "products")
public Product findProduct(String productId) {
    return productRepository.find(productId);
}
~~~

Đây là snippet minh họa, cần định nghĩa `User`, `Product` và repositories. Cả hai method có thể dùng key mặc định `"42"` mà không trùng entry, bởi `users` và `products` là hai vùng cache khác nhau về mặt abstraction.

Quy tắc key theo tham số có một số hệ quả:

1. ID nghiệp vụ thường là key tự nhiên, dễ theo dõi: cùng `userId` đọc cùng một entry trong cache `users`.
2. Phạm vi cache được quyết định riêng bằng tên cache hoặc resolver, không phải ngầm theo tên Java method.
3. Refactor đổi tên method nhưng giữ nguyên semantics không mặc nhiên làm key mặc định đổi theo tên Java. Tuy nhiên, nếu thay đổi cách biểu diễn hoặc ý nghĩa kết quả, vẫn cần chiến lược versioning/invalidation.
4. Các method có kết quả tương đương **có thể** chia sẻ entry có chủ đích, nếu chúng thật sự phù hợp về dữ liệu và chính sách làm mới.

Điều đáng nhớ: `SimpleKeyGenerator` tránh những va chạm do cách biểu diễn tổ hợp tham số trong phạm vi thuật toán của nó; điều này **không** có nghĩa nó sinh namespace riêng cho từng method. Khi hai operation cố tình hoặc vô tình chọn cùng vùng cache và cùng key, chúng đang dùng cùng một địa chỉ logic. Đây là trùng key, không đơn giản là “hai hash code bằng nhau”.

## 4. Lỗi cache trả nhầm dữ liệu do tên method không có trong key

Giả sử cache `shared` ban đầu trống và cả hai method đều trả `String`:

~~~text
1. Gọi findUserName("42")
   - Key mặc định: "42"
   - Cache("shared").get("42") -> MISS
   - Method chạy, trả "USER:42"
   - Cache.put("42", "USER:42")

2. Gọi findProductName("42")
   - Key mặc định: "42"
   - Cache("shared").get("42") -> HIT
   - Trả luôn "USER:42"
   - Method findProductName KHÔNG chạy
~~~

Spring làm đúng hành vi `@Cacheable`: khi hit, thân method bị bỏ qua. Lỗi là hai method có ý nghĩa kết quả **khác nhau** nhưng dùng một entry.

Nếu một method trả `User` và một method trả `Product`, việc dùng chung entry còn có nguy cơ gây lỗi ép kiểu. Nếu kết quả phụ thuộc `tenantId`, ngôn ngữ hoặc quyền truy cập mà key không chứa thông tin tương ứng, việc tái dùng sai entry có thể làm lộ dữ liệu giữa những ngữ cảnh khác nhau.

Va chạm không chỉ giới hạn trong một class. Hai Spring bean khác nhau nhưng cùng `CacheManager`, cùng cache name và tạo key tương đương cũng có thể đọc trúng entry của nhau.

Một ví dụ đặc biệt: hai method không tham số cùng `@Cacheable("settings")` đều tạo `SimpleKey.EMPTY`. Tên khác nhau vẫn không tự tách chúng.

## 5. Ví dụ Java 17 runnable: chứng minh bằng chương trình

Ví dụ dưới đây dùng Java 17, Maven, Spring Framework 6.2.10 và `ConcurrentMapCacheManager`. Đây là cache trong RAM của JVM, nên không cần database hay Redis. Hai method đầu cố ý cấu hình sai để thấy va chạm; hai method sau dùng prefix để khắc phục.

Cấu trúc thư mục:

~~~text
method-key-demo/
├── pom.xml
└── src/main/java/demo/MethodKeyDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>method-key-demo</artifactId>
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

File `src/main/java/demo/MethodKeyDemo.java`:

~~~java
package demo;

import java.util.Objects;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.SimpleKeyGenerator;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class MethodKeyDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("shared");
        }

        @Bean
        public NameService nameService() {
            return new NameService();
        }
    }

    public static class NameService {

        // Hai method khác nhau nhưng cùng cache name và default key.
        @Cacheable(cacheNames = "shared")
        public String userName(String id) {
            System.out.println("RUN userName(" + id + ")");
            return "USER(" + id + ")";
        }

        @Cacheable(cacheNames = "shared")
        public String productName(String id) {
            System.out.println("RUN productName(" + id + ")");
            return "PRODUCT(" + id + ")";
        }

        // Hai method này chủ động tạo hai namespace key khác nhau.
        @Cacheable(cacheNames = "shared", key = "'user:' + #p0")
        public String userNamePrefixed(String id) {
            System.out.println("RUN userNamePrefixed(" + id + ")");
            return "USER(" + id + ")";
        }

        @Cacheable(cacheNames = "shared", key = "'product:' + #p0")
        public String productNamePrefixed(String id) {
            System.out.println("RUN productNamePrefixed(" + id + ")");
            return "PRODUCT(" + id + ")";
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            NameService service = context.getBean(NameService.class);
            Cache cache = Objects.requireNonNull(
                context.getBean(CacheManager.class).getCache("shared"));

            System.out.println("Default key = "
                    + SimpleKeyGenerator.generateKey("42"));

            System.out.println("User = " + service.userName("42"));
            System.out.println("Product = " + service.productName("42"));
            System.out.println("Cache[42] = "
                    + cache.get("42", String.class));

            System.out.println("Prefixed user = "
                    + service.userNamePrefixed("42"));
            System.out.println("Prefixed product = "
                    + service.productNamePrefixed("42"));

            System.out.println("Both prefixed keys exist = "
                    + (cache.get("user:42") != null
                    && cache.get("product:42") != null));
        }
    }
}
~~~

Chạy tại thư mục có `pom.xml` (cần JDK 17 trở lên và Maven):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.MethodKeyDemo
~~~

Các dòng chương trình tự in:

~~~text
Default key = 42
RUN userName(42)
User = USER(42)
Product = USER(42)
Cache[42] = USER(42)
RUN userNamePrefixed(42)
Prefixed user = USER(42)
RUN productNamePrefixed(42)
Prefixed product = PRODUCT(42)
Both prefixed keys exist = true
~~~

**Dòng quan trọng là `Product = USER(42)`.** Không có dòng `RUN productName(42)` bởi lời gọi thứ hai hit key `"42"` do method thứ nhất đã lưu. Trong khi đó hai method có prefix tạo key `"user:42"` và `"product:42"`, nên mỗi method chạy và giữ kết quả riêng.

Lưu ý ví dụ gọi `context.getBean(NameService.class)` để đi qua Spring proxy; nếu tự tạo đối tượng bằng `new NameService()` ngoài container hoặc self-invocation `this.productName(...)` theo proxy mode, annotation có thể không được áp dụng. Khi đó kết quả kiểm thử sẽ khác, không còn chứng minh đúng hành vi cache.

## 6. Cách sửa thứ nhất: tách cache name theo loại dữ liệu

~~~java
@Cacheable(cacheNames = "users")
public User findUser(String userId) {
    return userRepository.find(userId);
}

@Cacheable(cacheNames = "products")
public Product findProduct(String productId) {
    return productRepository.find(productId);
}
~~~

Đây là snippet minh họa, cần định nghĩa kiểu/repository để biên dịch. Các cache `users` và `products` là hai vùng logic riêng; cùng default key `"42"` không tự trỏ cùng entry. Cách này thường phù hợp khi dữ liệu có TTL, giới hạn dung lượng hoặc chính sách invalidation khác nhau.

Quan trọng: chỉ đặt tên cache riêng là đủ về mặt abstraction khi `CacheManager` thực sự tạo/resolve các cache riêng. Nếu có cấu hình provider ánh xạ sai namespace, cần sửa luôn ở tầng provider.

## 7. Cách sửa thứ hai: giữ chung cache nhưng thêm prefix trong key

~~~java
@Cacheable(cacheNames = "lookup", key = "'user:' + #p0")
public String findUserName(String id) {
    return userRepository.findName(id);
}

@Cacheable(cacheNames = "lookup", key = "'product:' + #p0")
public String findProductName(String id) {
    return productRepository.findName(id);
}
~~~

Snippet này cần repositories thực tế. `#p0` là tham số thứ nhất, tránh phụ thuộc option biên dịch giữ tên parameter. Key là `"user:42"` và `"product:42"`. Đây là cách đơn giản khi ứng dụng **chủ đích dùng chung cache** nhưng các kết quả cần namespace riêng.

Không chỉ thêm prefix theo method rồi bỏ qua những yếu tố thực sự làm đổi kết quả. Ví dụ nếu kết quả phụ thuộc tenant, locale hoặc version thì key phải có các yếu tố đó. Ghép chuỗi một cách mơ hồ dễ gặp tình huống các input khác nhau tạo cùng chuỗi khi chúng chứa dấu phân cách; ứng dụng nhiều tenant còn cần tránh lộ dữ liệu nhạy cảm trong key/log.

Với một cache có nhiều operation, nên đặt quy ước thống nhất cho `@Cacheable`, `@CachePut` và `@CacheEvict` để đọc, ghi và xóa **cùng địa chỉ logic**. Nếu cập nhật key ở method đọc mà không cập nhật eviction, dữ liệu cũ có thể tồn tại ngoài ý muốn.

## 8. Cách sửa thứ ba: viết KeyGenerator tùy biến có xét Method

Giao diện `KeyGenerator` có tham số `Method`, nên ta có thể chủ động đưa method vào key:

~~~java
@Bean("methodAwareKeyGenerator")
public org.springframework.cache.interceptor.KeyGenerator
methodAwareKeyGenerator() {
    return (target, method, params) ->
        new org.springframework.cache.interceptor.SimpleKey(
            method.getDeclaringClass().getName(),
            method.getName(),
            new org.springframework.cache.interceptor.SimpleKey(params)
        );
}
~~~

Đây là snippet cấu hình đặt trong Spring `@Configuration`, không phải chương trình độc lập. Key được xây từ class khai báo method, tên method và tổ hợp tham số. Khi hai method khác tên, key sẽ khác dù `params` giống nhau.

Cách dùng:

~~~java
@Cacheable(
    cacheNames = "lookup",
    keyGenerator = "methodAwareKeyGenerator"
)
public String findUserName(String id) {
    return userRepository.findName(id);
}
~~~

Không ghi `key` và `keyGenerator` đồng thời cho cùng operation; Spring xem chúng là hai cách chỉ định key thay thế nhau.

### Đánh đổi khi dùng method-aware key

- Đổi tên/chuyển method sang class khác sẽ đổi key; một số entry cũ có thể không được hit và cần TTL/clear/migration.
- Chỉ có `method.getName()` chưa đảm bảo phân biệt **overload** cùng tên. Nếu cần, generator phải xét cả signature hoặc kiểu tham số khai báo.
- Một số operation có thể cố ý chia sẻ kết quả; tự động thêm method name làm mất lợi ích chia sẻ đó.
- `SimpleKey` thuận tiện cho `ConcurrentMapCache`, nhưng khi dùng Redis hoặc provider khác cần xác minh serializer/key conversion.
- `@CacheEvict` và `@CachePut` phải sử dụng quy tắc key phù hợp, nếu không entry được ghi sẽ không bị xóa/cập nhật như dự tính.

Vì thế, không nên cấu hình method-aware generator toàn cục chỉ để sửa một cặp method bị đặt chung cache name quá rộng. Tách cache name hoặc tạo key namespace tường minh thường dễ giải thích hơn.

## 9. Các trường hợp biên dễ bị bỏ sót

### Phương thức không có tham số

~~~java
@Cacheable(cacheNames = "settings")
public String countryCode() { return "VN"; }

@Cacheable(cacheNames = "settings")
public String currencyCode() { return "VND"; }
~~~

Cả hai dùng `SimpleKey.EMPTY` mặc định. Nếu cùng cache `settings`, gọi `countryCode()` trước có thể khiến `currencyCode()` nhận `"VN"` từ cache, dù kết quả đúng là `"VND"`. Có thể tách cache name hoặc đặt `key = "'countryCode'"`, `key = "'currencyCode'"`.

### Overload và return type

Default key không tự chứa tên method, kiểu tham số khai báo hay kiểu trả về. Không thể dựa vào việc một method trả `User` còn method khác trả `Product` để cho rằng cache sẽ tự cách ly. Nếu một entry sai kiểu được tái sử dụng, có thể xuất hiện lỗi ép kiểu; nếu cùng kiểu `String`, lỗi càng dễ ẩn vì giá trị trả về vẫn hợp lệ về kiểu Java.

### Bean class không tự tạo namespace

Hai Spring service khác package nhưng cùng cache name, cùng key và cùng manager vẫn có nguy cơ chung entry. Tên bean/class không được tự thêm vào khóa mặc định.

### equals/hashCode và tham số mutable

Key mặc định dựa trên giá trị/đối tượng tham số, nên `equals` và `hashCode` phải ổn định, phù hợp ngữ nghĩa. Dùng object mutable làm key rồi sửa nó sau khi đưa vào hash map có thể làm lookup thất thường. Provider ngoài JVM có thể còn chuyển đổi/serialize key.

### Version dữ liệu và thay đổi logic

Ngay cả một method duy nhất cũng có thể gặp entry không còn phù hợp sau khi nâng cấp ứng dụng. Đổi tên method không tự đổi key mặc định; đổi semantics/định dạng kết quả cần kế hoạch versioning, TTL, invalidation hoặc migration để tránh tái dùng dữ liệu cũ.

### Provider khác nhau

Spring Cache abstraction không quy định cùng một key object sẽ được Redis/Caffeine/ConcurrentMap biểu diễn hệt nhau. Khi debug, xem đồng thời **cache name logic, generated key và key vật lý/serialization** của provider. Cơ chế prefix cache name của Redis không đồng nghĩa Spring đã thêm tên method vào `SimpleKeyGenerator`.

## 10. Checklist kiểm tra nguy cơ va chạm trong dự án

1. Tìm các method dùng cùng `cacheNames` hoặc cùng cache được `CacheResolver` resolve; xét cả `@Cacheable`, `@CachePut` và `@CacheEvict`.
2. Xác định chiến lược key đang dùng: mặc định, `key` SpEL, `keyGenerator` chỉ định trên method hay generator mặc định tùy biến ở cấu hình.
3. Lấy hai lời gọi thực tế có tham số bằng nhau hoặc có khả năng tạo key bằng nhau, rồi tính key theo thuật toán đã chọn.
4. So sánh **ý nghĩa của kết quả**: nếu hai method trả dữ liệu khác nhau nhưng dùng cùng cache/key, phải sửa namespace.
5. Test qua Spring bean proxy, không chỉ gọi object `new` hoặc self-invocation. Theo dõi log body và kiểm tra `CacheManager.getCache(name).get(key)` khi cần.
6. Chọn phương án sửa: cache name tách biệt, key prefix tường minh, hoặc custom generator có đầy đủ định danh.
7. Kiểm tra lại các đường cập nhật và xóa cache, TTL, entry cũ cũng như provider phân tán. Đừng chỉ sửa annotation đọc.
8. Viết test thể hiện hai method khác nhau **không đọc nhầm entry của nhau** khi dùng input giống nhau.

## 11. Câu hỏi tự kiểm tra

**1.** Hai method `a(String id)` và `b(String id)` cùng `@Cacheable("shared")`, cùng gọi với `"7"`. Key mặc định có khác nhau do tên method không?

**Đáp án:** Không. Cả hai thường tạo key `"7"`. Nếu resolve vào cùng vùng `shared`, có thể dùng chung entry.

**2.** Tại sao `KeyGenerator.generate(...)` có tham số `Method` nhưng tên method không tự nằm trong key mặc định?

**Đáp án:** Interface cung cấp `Method` để custom generator có thể dùng. `SimpleKeyGenerator` mặc định lại chỉ tính key từ `params`.

**3.** Hai method không tham số có `@Cacheable("settings")` có key mặc định giống nhau không?

**Đáp án:** Có, đều là `SimpleKey.EMPTY`. Nếu kết quả khác nhau, cần tách cache name hoặc explicit key.

**4.** Hai method ở hai cache name khác nhau đều dùng key `"7"` có va chạm không?

**Đáp án:** Không nếu hai tên được resolve thành hai vùng cache độc lập. Key chỉ xác định entry trong phạm vi vùng cache đã chọn.

**5.** Có phải cứ thêm tên method vào key là giải quyết mọi vấn đề?

**Đáp án:** Không. Còn phải phân biệt overload, class/ngữ cảnh, tham số ảnh hưởng tới kết quả, serialization, và đồng bộ quy tắc giữa `@Cacheable`/`@CachePut`/`@CacheEvict`.

## Ghi nhớ

**`SimpleKeyGenerator` mặc định lấy key từ tham số, không từ tên phương thức.** Hai method khác tên vẫn có thể trùng entry nếu dùng cùng cache name và cùng key. Thiết kế cache an toàn cần xác định rõ **danh tính dữ liệu, vùng cache, cách tạo key và cách invalidation**, thay vì dựa vào tên Java method tự động bảo vệ namespace.

## Tài liệu chính thức

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Declarative Annotation-based Caching (default key): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework 6.2 — SimpleKeyGenerator: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/interceptor/SimpleKeyGenerator.html
- Spring Framework 6.2 — KeyGenerator: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/interceptor/KeyGenerator.html
