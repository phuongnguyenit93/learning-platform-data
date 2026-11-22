# Truy cập `#root.methodName`, `targetClass`, `args` và `caches` trong Spring Cache

## 1. Root object của Spring Cache SpEL

Spring Cache cho phép dùng Spring Expression Language (SpEL) trong thuộc tính `key`, `condition` của `@Cacheable`, cũng như một số thuộc tính của `@CachePut` và `@CacheEvict`. Mỗi khi một phương thức được xử lý qua Spring Cache interceptor, framework tạo *evaluation context* riêng để SpEL biết phương thức nào đang được gọi, đối số nào đã được truyền và những cache nào được chọn.

Trong ngữ cảnh đó, **`#root` là root object của thao tác cache hiện tại**. Bốn thuộc tính cần học:

| Biểu thức | Giá trị và kiểu | Ý nghĩa |
| --- | --- | --- |
| `#root.methodName` | `String`, ví dụ `"find"` | Tên phương thức Java được gọi. |
| `#root.targetClass` | `Class<?>`, ví dụ `CatalogService.class` | Lớp của đối tượng đích. |
| `#root.args` | Mảng `Object[]`, ví dụ `["B-7", "vi"]` | Đối số thực tế theo thứ tự truyền vào, chỉ số bắt đầu ở 0. |
| `#root.caches` | Tập hợp các `org.springframework.cache.Cache` | Các cache đã được resolve cho thao tác hiện tại. |

Giả sử `CatalogService.find("B-7")` được gắn `@Cacheable(cacheNames = "catalog")`. Khi gọi **qua Spring-managed proxy**, có thể hình dung ngữ cảnh như sau:

~~~text
service.find("B-7")
       |
       v
Spring Cache interceptor
       +-- #root.methodName  = "find"
       +-- #root.targetClass = CatalogService.class
       +-- #root.args        = ["B-7"]
       +-- #root.caches      = [Cache("catalog")]
       |
       v
Đánh giá SpEL cho key / condition
       |
       +-- cache hit  -> dùng dữ liệu cache
       +-- cache miss -> chạy method rồi lưu kết quả nếu được phép
~~~

`#root` mô tả **lời gọi**, không phải nội dung một entry cache hay danh sách toàn bộ cache trên hệ thống. Đây là ngữ cảnh do Spring Cache tạo; nếu tự dùng `SpelExpressionParser` bên ngoài cache interceptor, các giá trị này sẽ không tự động có mặt.

## 2. Sử dụng từng thuộc tính

### 2.1. `#root.methodName` — tên phương thức

`#root.methodName` trả về tên method, ví dụ `"find"`. Spring cũng cung cấp `#root.method` là metadata về phương thức; `#root.method.name` là một cách khác để lấy tên.

Ứng dụng thường gặp: tạo tiền tố để các method khác nhau dùng cùng một cache không đè key của nhau.

~~~java
@Cacheable(cacheNames = "catalog",
           key = "#root.methodName + ':' + #p0")
~~~

Đây là trích đoạn annotation đặt lên phương thức phù hợp. Với `find("B-7")`, key là `find:B-7`; với `findSummary("B-7")`, key là `findSummary:B-7`.

Tuy nhiên, `methodName` **không phải chữ ký đầy đủ**. Hai overload `find(String)` và `find(long)` vẫn có cùng tên. Nếu các giá trị tham số khác nhau có thể bị chuyển thành cùng một chuỗi, hãy thiết kế cách mã hóa key rõ ràng hoặc dùng `KeyGenerator`.

### 2.2. `#root.targetClass` — lớp đích

`#root.targetClass` là đối tượng `Class<?>`, **không** mặc định là một chuỗi tên lớp. Trên Java 17+, có thể truy cập tên qua SpEL:

~~~text
#root.targetClass
#root.targetClass.simpleName
#root.targetClass.name
#root.targetClass.packageName
~~~

Với lớp `demo.CatalogService`, `simpleName` thường cho `"CatalogService"` và `name` cho `"demo.CatalogService"`. `simpleName` có thể trùng nhau giữa các package. Nếu key chung cần phân biệt tên lớp, `name` thường rõ hơn.

Phân biệt: `#root.target` là **đối tượng đích đang được gọi**, còn `#root.targetClass` là **lớp của đối tượng đó**. Dùng metadata lớp để tạo key có thể có tác dụng phân vùng, nhưng cũng khiến key thay đổi khi rename/refactor package. Không nên thêm tên lớp vào mọi key theo thói quen.

### 2.3. `#root.args` — mảng đối số

Giả sử method có chữ ký `find(String code, String locale)` và được gọi với `find("B-7", "vi")`:

| Cách truy cập | Giá trị |
| --- | --- |
| `#root.args[0]` | `"B-7"` |
| `#root.args[1]` | `"vi"` |
| `#p0` hoặc `#a0` | `"B-7"` |
| `#p1` hoặc `#a1` | `"vi"` |
| `#code` | `"B-7"` nếu tên tham số được Spring khám phá. |

`#root.args[0]`, `#p0` và `#a0` đều truy cập tham số thứ nhất theo **vị trí**. `#code` phụ thuộc việc bytecode chứa tên tham số có thể được khám phá, chẳng hạn biên dịch với cờ `-parameters`.

Ví dụ một kết quả được bản địa hóa phụ thuộc cả mã và ngôn ngữ:

~~~java
@Cacheable(cacheNames = "catalog",
           key = "#root.args[0] + ':' + #root.args[1]")
~~~

Với `find("B-7", "vi")`, key là `B-7:vi`. Chỉ lấy `args[0]` sẽ khiến `find("B-7", "vi")` và `find("B-7", "en")` dùng cùng key dù kết quả cần khác nhau.

**Giới hạn và lựa chọn:**

- Chỉ số bắt đầu từ **0**. `args[1]` trên phương thức chỉ có một tham số sẽ lỗi khi đánh giá.
- Với phương thức không có tham số, không dùng `args[0]`.
- Đối số phức tạp cần chọn trường định danh ổn định (ví dụ `#p0.id` nếu truy cập được), thay vì phụ thuộc vào `toString()` hoặc identity của object.
- Ghép các tham số thành một chuỗi bằng dấu phân cách có thể gây trùng key khi chính dữ liệu chứa dấu đó. Với key phức tạp nên thiết kế cách mã hóa riêng hoặc `KeyGenerator`.
- Không đưa thông tin bí mật vào key nếu backend/log/metrics có thể ghi lại key.

### 2.4. `#root.caches` — các cache thuộc thao tác hiện tại

`#root.caches` là tập hợp các đối tượng `Cache` được giải quyết thông qua `CacheResolver` cho thao tác này. Nó không phải danh sách mọi cache do `CacheManager` biết và không phải tập hợp entry trong cache.

~~~java
@Cacheable(cacheNames = "catalog",
           key = "#root.caches[0].name + ':' + #p0")
~~~

Ở đây `#root.caches[0]` là đối tượng `Cache` thứ nhất, còn `.name` đọc tên từ `Cache#getName()`. Nếu tên cache là `catalog`, tham số là `B-7`, key sẽ là `catalog:B-7`.

Khi annotation khai báo nhiều cache, ví dụ `cacheNames = {"catalog", "catalogBackup"}`, danh sách cache trong ngữ cảnh có thể gồm nhiều phần tử. **Không** hiểu rằng mỗi cache có một key hoàn toàn độc lập chỉ vì dùng `#root.caches[0].name`; key của thao tác được dùng khi làm việc với những cache được chọn.

Nếu custom `CacheResolver` không cung cấp cache, truy cập `[0]` không an toàn. Trong đa số trường hợp, tên cache đã phân tách namespace, nên không cần đặt lại tên cache vào key. Ví dụ này chủ yếu cho thấy cách truy cập metadata.

## 3. Demo chạy được với Spring Boot 3, Java 17+

Ta tạo key từ đủ bốn thuộc tính:

~~~text
#root.methodName + '|' +
#root.targetClass.simpleName + '|' +
#root.args[0] + '|' +
#root.caches[0].name
~~~

Khi lời gọi là `CatalogService.find("B-7")` và cache tên `catalog`, key dự kiến: `find|CatalogService|B-7|catalog`.

Dùng một dự án Gradle với `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

Tạo file `src/main/java/demo/CacheSpelApplication.java`:

~~~java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class CacheSpelApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheSpelApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("catalog");
    }

    @Bean
    CatalogService catalogService() {
        return new CatalogService();
    }

    @Bean
    CommandLineRunner demo(CatalogService service, CacheManager manager) {
        return args -> {
            System.out.println("1 = " + service.find("B-7"));
            System.out.println("2 = " + service.find("B-7"));

            String key = "find|CatalogService|B-7|catalog";
            Cache cache = manager.getCache("catalog");
            if (cache == null) {
                throw new IllegalStateException("Missing catalog cache");
            }
            System.out.println("key = " + key);
            System.out.println("from cache = " + cache.get(key, String.class));
        };
    }
}

class CatalogService {
    @Cacheable(
            cacheNames = "catalog",
            key = "#root.methodName + '|' + "
                    + "#root.targetClass.simpleName + '|' + "
                    + "#root.args[0] + '|' + "
                    + "#root.caches[0].name"
    )
    public String find(String code) {
        System.out.println("LOAD " + code);
        return "title:" + code;
    }
}
~~~

Chạy `./gradlew bootRun` khi dự án có Gradle Wrapper (Windows: `gradlew.bat bootRun`); hoặc `gradle bootRun` nếu đã cài Gradle tương thích. Bên cạnh banner và log khởi động của Spring Boot, chương trình sẽ in các dòng demo sau theo thứ tự:

~~~text
LOAD B-7
1 = title:B-7
2 = title:B-7
key = find|CatalogService|B-7|catalog
from cache = title:B-7
~~~

**Diễn giải từng bước:**

1. `@EnableCaching` bật khả năng xử lý annotation. `CatalogService` được đăng ký bằng `@Bean`; lời gọi từ `CommandLineRunner` đi qua đối tượng Spring quản lý.
2. Lượt `find("B-7")` đầu tiên là **cache miss**, nên thân method chạy và in `LOAD B-7`; sau đó `title:B-7` được lưu.
3. Lượt thứ hai có cùng metadata và đối số nên key không đổi. Đây là **cache hit**, không chạy lại thân `find`, vì vậy chỉ thấy một dòng `LOAD`.
4. `Cache#get(key, String.class)` xác nhận key tương ứng đang chứa giá trị đã lưu.

Các phần của key:

| Thuộc tính | Giá trị demo |
| --- | --- |
| `#root.methodName` | `find` |
| `#root.targetClass.simpleName` | `CatalogService` |
| `#root.args[0]` | `B-7` |
| `#root.caches[0].name` | `catalog` |

Key hoàn chỉnh là `find|CatalogService|B-7|catalog`. Trong Java, literal của annotation được nối bằng `+` tại thời điểm biên dịch, vì vậy Spring nhận một chuỗi SpEL duy nhất.

`ConcurrentMapCacheManager` là cache cục bộ trong RAM, không có TTL mặc định và không đồng bộ tự động giữa nhiều instance. Nó được chọn để minh họa biểu thức; provider khác có chính sách lưu dữ liệu riêng.

## 4. Tạo điều kiện và tránh sai key

### 4.1. `condition` được đánh giá trước khi dùng cache

Một ví dụ cho phương thức có tham số đầu kiểu `String`:

~~~java
@Cacheable(cacheNames = "catalog",
           key = "#root.args[0]",
           condition = "#root.args[0] != null and !#root.args[0].isBlank()")
~~~

Khi `condition` là `false`, thao tác cache của annotation này bị bỏ qua nhưng thân phương thức vẫn thực thi. Biểu thức trên chỉ phù hợp với chữ ký đã nêu; không thể áp dụng nguyên xi cho tham số không phải `String`.

`#root` biểu diễn metadata của lời gọi; còn `#result` biểu diễn kết quả trả về sau khi method chạy và **không có sẵn** trong `key` hay `condition` của `@Cacheable`. `#result` có thể dùng trong `unless` của `@Cacheable`, key của `@CachePut` hoặc biểu thức của `@CacheEvict` sau lời gọi (`beforeInvocation = false`), tùy ngữ cảnh.

### 4.2. Đồng bộ quy tắc key khi cập nhật/xóa

Nếu `@Cacheable` trên method `find` dùng key `#root.methodName + ':' + #p0`, nó tạo `find:B-7`. Sao chép y nguyên biểu thức đó sang `@CacheEvict` trên method `update` lại tạo `update:B-7`. Hai key **không bằng nhau**, nên eviction không xóa bản ghi mà `find` đã lưu.

Giải pháp là thống nhất quy tắc key giữa đường đọc và đường ghi: khi bài toán đơn giản, dùng `key = "#p0"` cho cả `@Cacheable` và `@CacheEvict`; khi phức tạp, xây dựng một key generator hoặc helper có kiểm thử rõ ràng. Thêm tên method/class vào key chỉ hợp lý khi đã tính đến đường invalidation.

### 4.3. `#root` không giải quyết mọi bài toán nhất quán

SpEL xác định một key cụ thể; nó không tự xóa entry khi database bị thay đổi từ một service khác. Nếu dữ liệu được đọc theo tenant, locale hoặc phiên bản, các yếu tố đó cần xuất hiện trong key phù hợp. TTL, sự kiện invalidation và lựa chọn cache backend là các quyết định riêng về độ mới và tính nhất quán dữ liệu.

## 5. Các lỗi thường gặp

| Lỗi / hiểu nhầm | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Viết `#methodName` và coi nó như `#root.methodName`. | Thuộc tính `methodName` thuộc root object, không mặc định là biến riêng. | Dùng `#root.methodName`. |
| Xem `#root.targetClass` như tên lớp dạng `String`. | Nó là `Class<?>`. | Dùng `.name` hoặc `.simpleName` khi cần tên. |
| Lấy `#root.args[1]` với method một tham số. | Chỉ số vượt kích thước mảng. | Đối chiếu chữ ký; chỉ số từ 0. |
| Biểu thức `#code` không tìm thấy. | Tên tham số có thể không được lưu trong bytecode. | Dùng `#p0`, `#a0` hoặc `#root.args[0]`. |
| Nhầm `#root.caches` với mọi cache trong ứng dụng. | Nó chỉ chứa cache được resolve cho thao tác. | Kiểm tra `cacheNames` hoặc `CacheResolver`. |
| `#root.caches[0].name` không hoạt động. | Resolver không đưa ra phần tử thứ nhất hoặc cấu hình sai. | Xác minh cache được chọn trước khi dùng `[0]`. |
| Gọi hai lần vẫn thấy method chạy hai lần. | Caching chưa bật, key thay đổi, entry bị hết hạn hoặc lời gọi nội bộ bỏ qua proxy. | Kiểm tra `@EnableCaching`, proxy, key và chính sách provider. |
| `@CacheEvict` không xóa đúng entry. | Biểu thức key giữa method đọc và ghi khác nhau. | So sánh key thực tế và thống nhất quy tắc. |

Đặc biệt, gọi `this.find(...)` bên trong chính `CatalogService` thường không đi qua Spring proxy trong chế độ proxy mặc định. Khi đó `@Cacheable` có thể không được thực thi. Hãy gọi qua bean do Spring quản lý và kiểm tra provider hoặc log để phân biệt lỗi proxy với lỗi SpEL.

## 6. Tự kiểm tra

**Câu 1.** Với `find("B-7", "vi")`, biểu thức nào lấy đối số thứ hai?

Trả lời: `#root.args[1]`, `#p1` hoặc `#a1`.

**Câu 2.** `#root.caches[0]` và `#root.caches[0].name` khác nhau thế nào?

Trả lời: biểu thức thứ nhất lấy đối tượng `Cache`, biểu thức thứ hai lấy tên của cache đó.

**Câu 3.** `#root.targetClass` có cùng ý nghĩa với `#root.target` không?

Trả lời: không. Giá trị thứ nhất là `Class<?>` của đối tượng đích; giá trị thứ hai là chính đối tượng đích.

**Câu 4.** Tại sao không nên sao chép `#root.methodName + ':' + #p0` nguyên xi từ method `find` sang method `update` để evict?

Trả lời: tiền tố method đổi từ `find` sang `update`, tạo hai key khác nhau. Eviction phải nhắm đúng key đã được cache.

**Câu 5.** Khi nào nên dùng `#p0` thay vì `#code`?

Trả lời: khi cần truy cập theo vị trí, không phụ thuộc khả năng Spring đọc được tên tham số trong bytecode.

**Ghi nhớ:** `#root.methodName`, `#root.targetClass`, `#root.args` và `#root.caches` cung cấp metadata của lời gọi cache hiện tại. Hãy chọn đủ tham số ảnh hưởng đến kết quả, giữ key ổn định và thống nhất key giữa các thao tác đọc, cập nhật, xóa.

Tài liệu tham khảo: [Spring Framework Reference — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html).
