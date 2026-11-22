# Mối liên hệ giữa lời gọi phương thức, khóa và kết quả được lưu

## 1. Ba thành phần của một lần truy cập cache

Trong Spring Framework, `@Cacheable` gắn với **lời gọi một phương thức**. Cache lưu một ánh xạ **khóa → giá trị** bên trong một cache có tên. Có thể hình dung một mục lưu trữ bằng bộ ba:

```text
(cacheName, key) -> cachedValue
```

- **Lời gọi phương thức** cung cấp ngữ cảnh: phương thức được gọi qua Spring, đối số truyền vào, các biểu thức cấu hình cache và thời điểm thực thi.
- **Khóa (`key`)** là danh tính của mục cần tìm trong cache, thường được sinh từ các đối số. Khóa phải phản ánh đủ những yếu tố làm thay đổi kết quả.
- **Giá trị (`value`)** là kết quả phương thức trả về sau một lần thực thi thành công và được cache chấp nhận lưu. Khi trúng cache, Spring trả lại giá trị này mà không chạy phần thân phương thức.

Ví dụ, nếu phương thức `describe("p-1", "vi")` trả về mô tả tiếng Việt của sản phẩm, một thiết kế phù hợp là:

```text
cacheName = descriptions
key       = "p-1:vi"
value     = "Mô tả tiếng Việt của p-1"
```

Gọi lại với cùng khóa có thể lấy lại cùng giá trị; gọi `describe("p-1", "en")` phải dùng khóa khác vì nội dung tiếng Anh khác. **Tên phương thức, tên class và kiểu trả về không tự động là một phần của khóa mặc định**. Cache name tách các không gian khóa: `descriptions["p-1:vi"]` và `prices["p-1:vi"]` là hai mục ở hai cache khác nhau.

## 2. Spring xử lý một lời gọi `@Cacheable` như thế nào?

Giả sử có khai báo:

```java
@Cacheable(cacheNames = "descriptions", key = "#p0 + ':' + #p1")
public String describe(String productId, String language) {
    return loadFromDatabase(productId, language);
}
```

Đây là **đoạn minh họa**, `loadFromDatabase` tượng trưng cho thao tác đọc dữ liệu; ví dụ chạy đầy đủ nằm ở mục 5.

Luồng điển hình khi lời gọi đi qua proxy cache của Spring:

1. Spring xác định cache mang tên `descriptions` và tính khóa từ đối số, ở đây là `productId + ":" + language`.
2. Spring tìm giá trị tại khóa đó. Nếu **hit** (đã có mục phù hợp), kết quả được trả về ngay; `loadFromDatabase` không chạy.
3. Nếu **miss**, Spring gọi phương thức thực, nhận kết quả và thử lưu kết quả theo khóa đã tính (trừ khi điều kiện/veto không cho lưu hoặc backend phát sinh lỗi).
4. Kết quả của lần gọi hiện tại được trả về cho bên gọi. Lần gọi tiếp theo có cùng cache và khóa có thể hit.

```text
Caller
  |
  v
Spring cache interceptor
  |-- xác định cacheName + key
  |-- cache.get(key)
  |       |-- HIT  -> trả cachedValue, bỏ qua method body
  |       '-- MISS -> chạy method body -> lấy result
  |                              |-- đủ điều kiện -> cache.put(key, result)
  |                              '-- trả result
  '-- return cho Caller
```

Hai lời gọi có **đối số bằng nhau theo chiến lược tạo khóa** có thể dùng chung mục cache; hai lời gọi có cùng tên phương thức nhưng tạo ra khóa khác nhau sẽ có mục độc lập. Ngược lại, **cùng khóa không đảm bảo giá trị còn đúng với dữ liệu nguồn hiện tại**: tính mới của cache phụ thuộc cơ chế cập nhật, xóa và hết hạn.

## 3. Khóa mặc định được tạo ra từ đâu?

Khi không khai báo `key` hay `keyGenerator` riêng, Spring sử dụng `SimpleKeyGenerator`. Quy tắc trong Spring Framework hiện đại:

| Số đối số phương thức | Khóa mặc định |
| --- | --- |
| Không có đối số | `SimpleKey.EMPTY` |
| Một đối số khác `null` và không phải mảng | Chính đối số đó |
| Một đối số `null` hoặc mảng | `SimpleKey` chứa đối số đó |
| Từ hai đối số trở lên | Một đối tượng `SimpleKey` chứa các đối số theo thứ tự |

Ví dụ với `@Cacheable("examples")`:

- `find()` → khóa `SimpleKey.EMPTY`.
- `find("A")` → khóa `"A"`.
- `find("A", "vi")` → khóa `SimpleKey["A", "vi"]`; đổi thứ tự hoặc giá trị đối số tạo khóa khác.

Hệ quả quan trọng:

- **Không tự cộng tên method vào khóa.** Nếu `findById("A")` và `findDescription("A")` cùng dùng cache `examples`, đều dùng khóa mặc định `"A"` thì có thể đụng khóa và trả sai kiểu/nội dung. Hãy dùng cache name khác hoặc tạo khóa có namespace thích hợp.
- Với đối số là object, tính ổn định của khóa phụ thuộc `equals()`/`hashCode()`. Object thay đổi thuộc tính sau khi đưa vào cache có thể làm khóa không còn truy xuất ổn định, đặc biệt với cache dựa trên hash.
- Hai instance đại diện cùng định danh nghiệp vụ có thể tạo hai khóa khác nhau nếu object không định nghĩa so sánh theo giá trị. Thường nên dùng ID bất biến trong khóa thay cho toàn bộ entity.
- Backend phân tán có thể serialize hoặc chuyển đổi khóa; không mặc nhiên coi mọi loại đối tượng khóa đều dùng được trên Redis, JCache hoặc cache khác.

**Lưu ý:** việc chọn key dựa trên **đối số truyền vào**, không dựa vào kết quả phương thức vừa tính. Để tạo khóa rõ ràng, dùng SpEL `key = "#p0"`, `key = "#p0 + ':' + #p1"` hoặc một `KeyGenerator` tùy chỉnh. `#p0`/`#a0` là đối số thứ nhất, `#p1`/`#a1` là đối số thứ hai; tên như `#productId` chỉ khả dụng khi tên tham số được giữ đủ cho Spring đọc.

## 4. Thiết kế khóa theo ý nghĩa của kết quả

Giả sử kết quả có dạng:

```text
description = f(productId, language, tenantId, dataVersion)
```

Nếu `language` hoặc `tenantId` thực sự ảnh hưởng nội dung, bỏ chúng khỏi key có thể khiến người dùng nhận nhầm ngôn ngữ hoặc dữ liệu của tenant khác. Nếu `dataVersion` được quản lý bằng xóa cache sau cập nhật, không nhất thiết phải đưa version vào key; điều cốt lõi là có một chiến lược nhất quán để giữ dữ liệu hợp lệ.

| Cách thiết kế | Hệ quả |
| --- | --- |
| `key = "#p0"` cho `describe(id, language)` | Các ngôn ngữ của cùng ID dùng chung khóa: dễ trả sai mô tả |
| `key = "#p0 + ':' + #p1"` | ID và ngôn ngữ đều ảnh hưởng khóa; thích hợp với dữ liệu ví dụ |
| `key = "#p0 + #p1"` | Có thể nối chuỗi mơ hồ: `("ab","c")` và `("a","bc")` cùng thành `"abc"` |
| `key = "new org.springframework.cache.interceptor.SimpleKey(#p0, #p1)"` | Giữ hai thành phần khóa tách biệt mà không phụ thuộc dấu phân cách |

Với hệ thống thực, cân nhắc thêm phiên bản schema, tenant, quyền truy cập hoặc các bộ lọc **nếu chúng ảnh hưởng kết quả**. Không đưa mật khẩu/token bí mật vào khóa hoặc log; tránh khóa chứa đối tượng lớn, biến đổi liên tục. Dù cùng khóa, TTL, eviction và chính sách bộ nhớ vẫn do cache provider quyết định.

## 5. Ví dụ Java 17+ chạy được: quan sát hit, miss và kết quả trả về

Ví dụ sử dụng Spring Boot 3.3.5, Java 17+, Maven, `@EnableCaching` và `ConcurrentMapCacheManager` (cache trong bộ nhớ của tiến trình). Cấu trúc:

```text
cache-demo/
├── pom.xml
└── src/main/java/example/cache/
    ├── CacheDemoApplication.java
    └── ProductService.java
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>cache-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/example/cache/CacheDemoApplication.java`**

```java
package example.cache;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class CacheDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheDemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("descriptions");
    }

    @Bean
    CommandLineRunner runDemo(ProductService service) {
        return args -> {
            System.out.println(service.describe("p-1", "vi"));
            System.out.println(service.describe("p-1", "vi"));
            System.out.println(service.describe("p-1", "en"));
            System.out.println(service.describe("p-1", "vi"));
        };
    }
}
```

**`src/main/java/example/cache/ProductService.java`**

```java
package example.cache;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final AtomicInteger databaseLoads = new AtomicInteger();

    @Cacheable(cacheNames = "descriptions", key = "#p0 + ':' + #p1")
    public String describe(String productId, String language) {
        int loadNumber = databaseLoads.incrementAndGet();
        return "load#" + loadNumber + " [" + productId + "," + language + "]";
    }
}
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn spring-boot:run
```

Bốn dòng được `CommandLineRunner` in ra (bỏ qua log khởi động của Spring Boot):

```text
load#1 [p-1,vi]
load#1 [p-1,vi]
load#2 [p-1,en]
load#1 [p-1,vi]
```

Giải thích từng lần gọi:

| Lần gọi | Khóa SpEL | Hit/miss | Phương thức thực chạy? | Kết quả |
| --- | --- | --- | --- | --- |
| `describe("p-1","vi")` lần 1 | `p-1:vi` | Miss | Có, tăng bộ đếm lên 1 | `load#1 [p-1,vi]` |
| `describe("p-1","vi")` lần 2 | `p-1:vi` | Hit | Không | Dùng lại `load#1 [p-1,vi]` |
| `describe("p-1","en")` | `p-1:en` | Miss | Có, tăng bộ đếm lên 2 | `load#2 [p-1,en]` |
| `describe("p-1","vi")` lần 3 | `p-1:vi` | Hit | Không | Dùng lại kết quả đầu tiên |

Ví dụ cố ý dùng bộ đếm thay cho database để phân biệt **thực thi phương thức** với **trả kết quả từ cache**. Giá trị `load#1` không có nghĩa cache tự tính lại kết quả; đó là chính giá trị lần gọi đầu được lưu. `ConcurrentMapCacheManager` chỉ tồn tại trong tiến trình, mất dữ liệu khi ứng dụng dừng; ví dụ không chứng minh khả năng chia sẻ cache giữa nhiều instance.

## 6. Khi dữ liệu thay đổi: kết quả cache có còn đúng không?

Giả sử kết quả mô tả trong nguồn dữ liệu đổi từ `"Bản cũ"` sang `"Bản mới"`. Nếu mục `descriptions["p-1:vi"]` vẫn còn thì lần đọc tiếp theo vẫn có thể trả `"Bản cũ"` mà không gọi phương thức. Vì thế phải xác định rõ **lúc nào cập nhật hoặc xóa khóa**.

Các annotation thường dùng:

- `@Cacheable`: ưu tiên đọc cache; khi miss mới gọi phương thức và lưu kết quả.
- `@CachePut`: **luôn gọi** phương thức, sau đó dùng kết quả trả về để cập nhật cache theo khóa cấu hình. Phù hợp khi việc ghi cũng trả về đúng dữ liệu cần cache.
- `@CacheEvict`: xóa mục theo khóa; mặc định xóa **sau khi phương thức hoàn thành thành công**. `allEntries = true` xóa toàn bộ mục trong cache tương ứng; `beforeInvocation = true` thực hiện xóa trước lời gọi.
- `@Caching`: nhóm nhiều thao tác cache trên một phương thức; cần xem kỹ thứ tự và xung đột.
  
Ví dụ khai báo trên một phương thức cập nhật dữ liệu (đây chỉ là **đoạn minh họa**, cần tự cung cấp kho dữ liệu):

```java
@CacheEvict(cacheNames = "descriptions", key = "#p0 + ':' + #p1")
public void updateDescription(String productId, String language, String newText) {
    repository.save(productId, language, newText);
}
```

Khi cập nhật `("p-1","vi")` thành công, mục `p-1:vi` bị xóa; lượt `describe("p-1","vi")` kế tiếp miss và đọc dữ liệu mới. **Khóa của thao tác ghi/xóa phải tương thích với khóa của thao tác đọc** (cùng cache name, cùng thứ tự/thành phần đối số). Đừng dùng `@CachePut` và `@Cacheable` chung trên một phương thức chỉ để vừa buộc chạy vừa hy vọng bỏ qua chạy: hai mục tiêu này xung đột và khó dự đoán.

Với dữ liệu có thể bị chỉnh sửa từ dịch vụ khác, thao tác annotation trên một ứng dụng không đủ đảm bảo các node khác tự làm mới. TTL, pub/sub, invalidation phân tán hoặc versioned key là quyết định thiết kế ở tầng provider/hệ thống.

## 7. Điều kiện và trường hợp không lưu kết quả

Hai thuộc tính của `@Cacheable` dễ bị nhầm:

```java
@Cacheable(
    cacheNames = "descriptions",
    key = "#p0 + ':' + #p1",
    condition = "#p1 != 'debug'",
    unless = "#result == null"
)
public String describe(String productId, String language) {
    // Đọc dữ liệu thật; thân phương thức chỉ được chạy khi cần.
    return loadFromDatabase(productId, language);
}
```

*Đoạn trên minh họa annotation, không phải chương trình chạy độc lập.*

- `condition` được đánh giá **trước khi tra cache**. Khi biểu thức sai, lời gọi đi thẳng đến phương thức thực mà không đọc/ghi cache theo annotation này.
- `unless` được đánh giá **sau khi phương thức tạo ra kết quả** và có thể dùng `#result` để từ chối lưu. Nó không khiến một cache hit phải gọi lại phương thức.
- Khi phương thức ném exception, mặc định đó không phải một giá trị kết quả để `@Cacheable` lưu. Null/`Optional.empty()` có được chấp nhận lưu và thể hiện ra sao còn tùy loại cache, cấu hình và khả năng hỗ trợ của provider; tránh suy diễn rằng mọi cache đều giống nhau.

Một cache key đúng vẫn chưa đủ để bảo đảm một kết quả sẽ được lưu: còn phải xét `condition`, `unless`, trạng thái provider, eviction và hết hạn.

## 8. Proxy, thời điểm thực thi và các ngộ nhận thường gặp

**Proxy:** Ở chế độ mặc định, cache advice hoạt động khi lời gọi đi **qua proxy do Spring quản lý**. Gọi trực tiếp từ một phương thức khác **trong cùng object** bằng `this.describe(...)` thường bỏ qua cache interceptor. Ví dụ chạy ở trên nhận `ProductService` qua dependency injection nên có interception; nếu tự tạo `new ProductService()` thì annotation cũng không tự có tác dụng. Ưu tiên đặt annotation trên phương thức `public` của Spring bean và gọi từ bean khác thông qua injection. Cần `@EnableCaching` hoặc cấu hình tương đương.

**Đồng thời:** Hai request cùng miss một khóa có thể cùng chạy truy vấn trước khi mục cache được điền. `@Cacheable(sync = true)` yêu cầu phối hợp tải giá trị cho cùng khóa khi provider hỗ trợ, nhưng có giới hạn (một cache, không dùng `unless`, không kết hợp thao tác cache khác) và không thay thế khóa phân tán/transaction.

**Transaction và dữ liệu mới:** Nếu cập nhật dữ liệu nguồn chưa commit mà cache đã put/evict, có thể xảy ra cửa sổ không nhất quán. Hãy thiết kế thời điểm invalidate theo ranh giới transaction; Spring Cache không tự biến kết quả được lưu thành dữ liệu luôn nhất quán.

**Mất cache:** Restart, TTL, giới hạn dung lượng hoặc eviction có thể làm lần gọi tưởng là hit thành miss. Kết quả lần miss có thể khác vì dữ liệu nguồn đổi, ngay cả khi khóa giống hệt.

**Nhiều phương thức:** Hai method khác nhau dùng cùng cache name và tạo cùng key có thể cùng tham chiếu một entry. Nếu dữ liệu/kiểu trả về không tương thích, đây là lỗi thiết kế key/cache name. Tránh dùng một cache chung mơ hồ chỉ vì các method đều liên quan đến sản phẩm.

## 9. Checklist kiểm tra thiết kế và lỗi thường gặp

Khi đọc một method có `@Cacheable`, tự trả lời lần lượt:

1. **Cache nào?** `cacheNames`/`CacheManager` chọn không gian lưu nào?
2. **Key nào?** Mặc định dùng đối số nào, hay có SpEL/`KeyGenerator` riêng? ID, locale, tenant, filter, version có ảnh hưởng giá trị không?
3. **Miss làm gì?** Có lời gọi I/O hay tính toán tốn kém nào chạy; kết quả dự kiến có tái sử dụng an toàn không?
4. **Hit trả gì?** Người dùng có thể nhận giá trị cũ khi dữ liệu nguồn đã thay đổi không?
5. **Khi nào làm mới?** Ghi dữ liệu có `@CachePut`/`@CacheEvict` với **cùng key**? Có TTL hoặc invalidation liên node không?
6. **Interceptor có chạy?** Method thuộc Spring bean, public, được gọi qua proxy chứ không phải self-invocation?
7. **Có trường hợp không cache?** Kiểm tra `condition`, `unless`, null/exception và hỗ trợ của provider.

Các dấu hiệu lỗi điển hình:

- Bỏ `language`/`tenantId` khỏi khóa trong khi kết quả phụ thuộc chúng → rò rỉ hoặc trả nhầm dữ liệu.
- Khóa sinh bằng nối chuỗi không phân tách hay đối tượng có `hashCode()` thay đổi → collision/miss bất ngờ.
- Lệnh đọc dùng `"p-1:vi"` nhưng lệnh evict dùng `"p-1"` → xóa sai khóa, dữ liệu cũ tiếp tục được trả.
- Giả định `@Cacheable` luôn gọi method để kiểm tra dữ liệu mới → thực tế hit bỏ qua method.
- Giả định annotation có hiệu lực khi gọi `this.method()` → proxy mặc định không chặn lời gọi nội bộ.
- Giả định cache local tự đồng bộ giữa các instance hoặc tự hết hạn → phụ thuộc backend và cấu hình cụ thể.

## 10. Tự kiểm tra kiến thức

**Tình huống A.** `getPrice("A", "VND")` và `getPrice("A", "USD")` cùng dùng khóa `"A"`. Nếu giá khác theo đơn vị tiền, điều gì sai?

Trả lời: Hai lời gọi chia sẻ một mục cache dù đầu ra khác; cần thêm currency vào key hoặc tách cache theo ngữ cảnh.

**Tình huống B.** `getPrice("A", "VND")` lần 1 truy vấn database, lần 2 không truy vấn. Sau đó database đổi giá nhưng chưa evict. Lần 3 trả gì?

Trả lời: Có thể vẫn trả giá đã lưu ở lần 1; key trùng khiến hit. Muốn giá mới phải cập nhật/xóa entry hoặc để nó hết hạn theo chính sách provider.

**Tình huống C.** Hai method có cùng một đối số `"A"`, cùng `cacheNames = "items"` và không đặt `key`. Chúng có luôn độc lập không?

Trả lời: Không. Mặc định một đối số tạo key là chính `"A"`; nếu hai phương thức chia sẻ cache, chúng có nguy cơ dùng chung entry. Tên phương thức không tự có trong key.

**Tình huống D.** Vì sao ví dụ `CommandLineRunner` cho ra load#1, load#1, load#2, load#1?

Trả lời: Các lần 1 và 3 miss do hai key khác nhau; lần 2 và lần 4 hit key `p-1:vi` nên trả lại kết quả đã lưu của lần 1.

## Tài liệu tham khảo

- Spring Framework — Cache Abstraction, đặc biệt mục `@Cacheable`, Default Key Generation và Conditional Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Javadoc `@Cacheable`: https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Boot — Caching: https://docs.spring.io/spring-boot/reference/io/caching.html
