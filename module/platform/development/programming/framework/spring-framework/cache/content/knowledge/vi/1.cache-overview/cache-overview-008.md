# Kiến thức nền và trình tự học Spring Cache

## Mục tiêu của bài

Sau bài này, bạn có thể giải thích vì sao ứng dụng cần cache, phân biệt cache hit/miss và nguồn dữ liệu gốc, mô tả cách Spring Cache chặn lời gọi phương thức, lựa chọn đúng `@Cacheable`, `@CachePut`, `@CacheEvict`, và sắp xếp một lộ trình học từ ví dụ đơn giản đến kiểm thử, vận hành. Đây là bài nền tảng của nhóm **Tổng quan**, vì vậy ưu tiên mô hình tư duy và trình tự thực hành trước khi đi sâu cấu hình từng nhà cung cấp cache.

Kiến thức nên có: Java 17+, class/method và collection, khái niệm Spring bean/Dependency Injection; biết sơ bộ request → service → repository/database. Hiểu Spring AOP/proxy ở mức cơ bản sẽ giúp giải thích các trường hợp annotation không chạy.

## 1. Cache là gì và lúc nào đáng dùng?

Cache lưu tạm kết quả hoặc dữ liệu được truy cập nhiều để lần sau phục vụ nhanh hơn, giảm thao tác tốn thời gian như truy vấn database, gọi dịch vụ khác hoặc tính toán. **Nguồn dữ liệu gốc (source of truth)** vẫn là nơi quyết định giá trị đúng; cache là bản sao có thể cũ và có thể bị xóa rồi tạo lại.

Ví dụ: `getProduct("P01")` phải đọc database mất 80 ms. Với cùng khóa `P01`, lần đầu là **cache miss**: chạy phương thức, đọc nguồn, đưa kết quả vào cache. Lần thứ hai là **cache hit**: trả giá trị từ cache mà không chạy thân phương thức. Thời gian 80 ms chỉ là số minh họa, không phải cam kết hiệu năng.

| Khái niệm | Cần hiểu chính xác |
| --- | --- |
| Cache entry | Một cặp khóa → giá trị trong một cache có tên. |
| Cache key | Danh tính của dữ liệu cần lấy; hai lời gọi phải cùng key khi chúng thực sự có thể dùng chung kết quả. |
| Hit / miss | Có giá trị phù hợp trong cache / phải lấy hoặc tính từ nguồn. |
| Invalidation / eviction | Loại bỏ một hoặc nhiều entry để lần đọc sau nạp lại. |
| TTL (time to live) | Khoảng thời gian sống của entry theo chính sách nhà cung cấp cache, nếu được cấu hình. |
| Stale data | Giá trị trong cache không còn khớp dữ liệu gốc. |
| Cache stampede | Nhiều request cùng miss cho một khóa và đồng thời đánh vào nguồn. |

**Nên cân nhắc cache** khi đọc lặp lại nhiều, kết quả tương đối ổn định, việc nạp lại tốn kém, và chấp nhận được quy tắc cập nhật/độ trễ dữ liệu. **Không nên mặc định cache** dữ liệu có độ chính xác thời gian thực cao, dữ liệu nhạy cảm theo người dùng nếu key không phân biệt tenant/quyền truy cập, hoặc phép tính rẻ có tỷ lệ lặp rất thấp. Cache đổi lấy độ phức tạp về tính nhất quán, bộ nhớ và quan sát vận hành.

Phân biệt phạm vi: **Spring Cache** chủ yếu cache kết quả lời gọi phương thức trong ứng dụng; nó không tự thay thế HTTP caching (`Cache-Control`/ETag), cache cấp hai của ORM hay thiết kế lưu trữ database.

## 2. Spring Cache cung cấp những gì?

Spring Cache là **abstraction** (lớp trừu tượng): định nghĩa cách yêu cầu cache, không tự quyết định hệ lưu trữ hay chính sách hết hạn. Hai giao diện cần nhớ:

- `org.springframework.cache.Cache`: thao tác với một cache cụ thể, ví dụ lấy/đặt/xóa entry.
- `org.springframework.cache.CacheManager`: quản lý và tìm cache theo tên, ví dụ cache `products`.

Khi bật `@EnableCaching` và phương thức thuộc Spring bean được gọi **qua proxy**:

1. Spring xác định cache và key theo annotation.
2. Với `@Cacheable`, kiểm tra cache. **Hit:** trả giá trị đã lưu, không chạy thân phương thức. **Miss:** chạy thân phương thức, rồi lưu kết quả phù hợp trước khi trả về.
3. Với `@CachePut`, luôn chạy phương thức rồi cập nhật cache bằng giá trị trả về.
4. Với `@CacheEvict`, xóa entry theo quy tắc của annotation.

`@EnableCaching` chỉ kích hoạt cơ chế advice. Cần có `CacheManager` và một backend cache; trong ứng dụng Spring Boot có starter phù hợp, Boot có thể tự cấu hình cache manager dựa trên dependency. Một cache đơn giản dựa trên `ConcurrentHashMap` hữu ích để học, nhưng không có sẵn TTL/giới hạn dung lượng cho môi trường production.

**Giới hạn quan trọng của proxy mặc định:** gọi `this.getProduct(id)` từ phương thức khác **trong cùng bean** không đi qua proxy, nên `@Cacheable` trên `getProduct` sẽ không được áp dụng cho lời gọi đó. Hãy gọi qua bean Spring từ bên ngoài, đặt ranh giới service rõ ràng; ở bài đầu ưu tiên annotation trên phương thức `public` của bean được Spring quản lý. Tự tạo object bằng `new` bên ngoài container cũng làm mất cơ chế Spring quản lý.

## 3. Ba annotation cốt lõi và lựa chọn đúng

| Annotation | Khi phương thức chạy? | Tác động lên cache | Tình huống |
| --- | --- | --- | --- |
| `@Cacheable` | Chỉ khi cache không có giá trị phù hợp | Ghi kết quả khi miss | Đọc danh mục, cấu hình, tra cứu |
| `@CachePut` | **Luôn chạy** | Ghi/cập nhật bằng kết quả trả về | Phương thức cập nhật nguồn rồi trả đối tượng mới |
| `@CacheEvict` | Chạy bình thường | Xóa entry hoặc toàn bộ cache được chỉ định | Sau khi sửa/xóa dữ liệu, buộc đọc lại |

Các thuộc tính nên học theo thứ tự:

- `cacheNames` (hoặc `value`): tên cache; đặt theo loại dữ liệu và nhất quán giữa đọc/ghi/xóa.
- `key`: biểu thức SpEL tạo khóa, ví dụ `key = "#p0"` dùng đối số đầu tiên; `#p0` không lệ thuộc cấu hình giữ tên tham số khi biên dịch.
- `condition`: xét **trước** lúc gọi phương thức để quyết định có áp dụng cache hay không.
- `unless`: xét **sau** khi có kết quả, thường dùng để tránh cache kết quả không phù hợp, ví dụ `unless = "#result == null"`.
- `allEntries = true` trong `@CacheEvict`: xóa mọi entry của cache chỉ định; không dùng tùy tiện vì có thể gây miss hàng loạt.
- `beforeInvocation = true`: evict trước khi chạy phương thức; mặc định evict sau khi phương thức hoàn thành thành công.

Với key mặc định, Spring thường dùng toàn bộ tham số đầu vào: không tham số → `SimpleKey.EMPTY`, một tham số → chính đối số đó, nhiều tham số → `SimpleKey` gồm các đối số. Dù dùng key mặc định hay SpEL, phải xét tính ổn định của `equals/hashCode`, tham số mutable, cùng một mã nhưng khác tenant/ngôn ngữ/quyền, và sự tương ứng giữa key đọc với key cập nhật/xóa. Không đặt `@Cacheable` và `@CachePut` tùy tiện trên cùng phương thức vì một annotation muốn bỏ qua execution khi hit, annotation kia muốn luôn chạy.

## 4. Ví dụ thực hành có thể chạy (Spring Boot, Java 17+)

Ví dụ giả lập nguồn dữ liệu bằng `ConcurrentHashMap` để nhìn rõ lần thực sự đọc nguồn. Đưa các file sau vào **một dự án Spring Boot dùng Gradle/Groovy**, đã có plugin Spring Boot và Java 17+; thêm starter vào `build.gradle` (giữ nguyên các dependencies khác của dự án):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
```

**File `src/main/java/example/cache/CacheConfig.java`:** bật cache và chủ động chọn backend bộ nhớ cho demo.

```java
package example.cache;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfig {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books");
    }
}
```

**File `src/main/java/example/cache/BookService.java`:** dữ liệu gốc là `store`; biến đếm chỉ tăng khi thân `getTitle` thực sự chạy.

```java
package example.cache;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class BookService {
    private final Map<String, String> store =
            new ConcurrentHashMap<>(Map.of("b1", "Java cơ bản"));
    private final AtomicInteger sourceReads = new AtomicInteger();

    @Cacheable(cacheNames = "books", key = "#p0")
    public String getTitle(String id) {
        System.out.println("SOURCE read #" + sourceReads.incrementAndGet());
        return store.get(id);
    }

    @CachePut(cacheNames = "books", key = "#p0")
    public String rename(String id, String newTitle) {
        store.put(id, newTitle);
        return newTitle;
    }

    @CacheEvict(cacheNames = "books", key = "#p0")
    public void evict(String id) {
        // Demo: chỉ loại entry cache, không thay đổi dữ liệu gốc.
    }
}
```

**File `src/main/java/example/cache/CacheDemoApplication.java`:** gọi service từ bean khác, qua proxy do Spring quản lý.

```java
package example.cache;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CacheDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(BookService books) {
        return args -> {
            System.out.println(books.getTitle("b1"));  // miss
            System.out.println(books.getTitle("b1"));  // hit
            System.out.println(books.rename("b1", "Spring Cache"));
            System.out.println(books.getTitle("b1"));  // hit với giá trị mới
            books.evict("b1");
            System.out.println(books.getTitle("b1"));  // miss sau evict
        };
    }
}
```

Chạy trong thư mục dự án:

```bash
./gradlew bootRun
# Windows PowerShell: .\gradlew.bat bootRun
```

Các dòng **`System.out` của ví dụ** theo thứ tự (không tính log khởi động Spring Boot):

```text
SOURCE read #1
Java cơ bản
Java cơ bản
Spring Cache
Spring Cache
SOURCE read #2
Spring Cache
```

Giải thích: lần lấy đầu là miss nên `sourceReads` tăng; lần hai là hit nên không tăng. `rename` luôn chạy, sửa `store` rồi `@CachePut` đặt `Spring Cache` vào cache với đúng key `b1`. Lần đọc tiếp vẫn hit nhưng nhận giá trị mới. `evict` loại cache entry, nên lần cuối đọc nguồn lần hai. Demo chỉ chạy với key tồn tại; xử lý dữ liệu không tìm thấy/null cần một quyết định cache riêng.

**Lưu ý chạy:** đây là ba class đặt trong một dự án Spring Boot có sẵn, không phải một file Java độc lập để chạy trực tiếp bằng `javac`. Với Spring Boot đã cấu hình Gradle, `bootRun` là lệnh phù hợp; chọn starter và phiên bản nhất quán với dự án.

## 5. Key và tính nhất quán: phần dễ sai nhất

Khi đưa cache vào service thật, phải viết rõ hợp đồng: **nguồn gốc dữ liệu là gì, cache tên gì, key chứa các thành phần nào, khi nào cập nhật, khi nào xóa, được phép cũ trong bao lâu**.

- **Cùng dữ liệu, cùng key:** ví dụ đọc `getById(42)`, cập nhật `update(42)` và xóa `delete(42)` phải phối hợp trên cùng cache/key. Key sai tạo dữ liệu cũ kéo dài.
- **Phân vùng quyền/tenant:** không cache kết quả riêng người dùng dưới key chỉ có `productId` nếu quyền, giá hay ngôn ngữ làm thay đổi kết quả; cân nhắc các thành phần tương ứng trong key.
- **Thời điểm invalidation:** xóa cache sau khi nguồn thay đổi thành công; với transaction có rollback và nhiều lời gọi đồng thời, phải kiểm thử thứ tự thực thi và có thể cần cơ chế cập nhật sau commit. Cache annotation không tự giải quyết nhất quán giao dịch.
- **TTL không đồng nghĩa luôn đúng:** TTL giới hạn thời gian tồn tại khi provider hỗ trợ, nhưng trong cửa sổ đó dữ liệu vẫn có thể stale; khi cần nhất quán hơn, evict hoặc cập nhật chủ động.
- **Không cache vô điều kiện:** cân nhắc null, exception, kết quả biến thiên theo thời gian/quyền, đối tượng mutable và các thao tác có side effect. `@Cacheable` có thể bỏ qua toàn bộ thân phương thức ở hit.
- **Đồng thời:** nhiều miss cùng lúc có thể cùng tính toán. `@Cacheable(sync = true)` có thể phối hợp việc nạp cùng key khi provider hỗ trợ, nhưng không phải cơ chế khóa phân tán toàn cục; hiểu khả năng của backend trước khi dùng.

## 6. Chọn backend theo nhu cầu

| Lựa chọn | Phù hợp để học / áp dụng | Điều cần tự cấu hình hoặc kiểm chứng |
| --- | --- | --- |
| `ConcurrentMapCacheManager` (in-memory) | Demo, test, ứng dụng nhỏ; nhẹ và dễ quan sát | Không có TTL/dung lượng giới hạn mặc định; cache nằm trong từng instance và mất khi khởi động lại. |
| Caffeine (local cache) | Truy cập rất nhanh trong một JVM, cần giới hạn kích thước hoặc expiry | Cấu hình maximum size/TTL theo Caffeine; nhiều instance có nhiều bản cache riêng. |
| Redis (shared/distributed cache) | Nhiều instance cần truy cập cùng store cache | Kết nối, serializer, TTL, key prefix, lỗi mạng, vận hành và chính sách nhất quán. |

Spring Cache tách annotation khỏi backend, nhưng **ngữ nghĩa TTL, eviction, giới hạn bộ nhớ, null và đồng thời phụ thuộc provider**. Không giả định đổi backend là tương đương tuyệt đối. Với một ứng dụng nhiều replica, local cache không tự đồng bộ giữa các replica. Chọn backend sau khi có yêu cầu về thời gian sống, quy mô và độ nhất quán, không chọn chỉ vì công nghệ phổ biến.

## 7. Trình tự học đề xuất theo năng lực

| Chặng | Học và thực hành gì? | Dấu hiệu đã hiểu |
| --- | --- | --- |
| 1. Nền tảng | Cache hit/miss, key/value, nguồn dữ liệu, stale data, TTL, invalidation, chi phí bộ nhớ. | Tự vẽ được luồng đọc có/không có cache; nêu được ít nhất hai rủi ro. |
| 2. Spring container/proxy | Bean, lời gọi qua proxy, `@EnableCaching`, `Cache`, `CacheManager`. | Giải thích được vì sao self-invocation không kích hoạt `@Cacheable` mặc định. |
| 3. Đọc có cache | Chạy `@Cacheable` với backend bộ nhớ, quan sát hit/miss bằng bộ đếm. | Lần thứ hai cùng key không chạy thân phương thức. |
| 4. Ghi và xóa | Thử `@CachePut`, `@CacheEvict`, `allEntries`, quy tắc key thống nhất. | Sau update đọc thấy dữ liệu mới; sau evict lần đọc tiếp là miss. |
| 5. Chính sách lưu | Thử `key`, `condition`, `unless`; quyết định có cache null và dữ liệu theo người dùng hay không. | Chứng minh hai request khác ngữ cảnh không trả nhầm cache entry. |
| 6. Backend và tuổi thọ | So sánh ConcurrentMap, Caffeine, Redis; thử cấu hình expiry/size ở provider. | Mô tả được local cache khác shared cache và ai chịu trách nhiệm TTL. |
| 7. Nhất quán, đồng thời | Thử cập nhật nguồn, rollback transaction, hai request cùng miss, nhiều instance. | Biết khi nào phải evict sau commit và khi nào `sync` chưa đủ. |
| 8. Kiểm thử, vận hành | Viết test hit/miss/invalidation; đo hit rate, số truy vấn thật, độ trễ, memory, lỗi backend. | Có bằng chứng cache giảm chi phí mà không trả dữ liệu sai. |

**Bài tập nối tiếp:** dùng demo trên, thêm key `b2` và đếm số lần đọc nguồn; so sánh kết quả khi thay key, khi gọi hai lần cùng key, sau `rename`, sau `evict`. Sau đó tạo một lời gọi nội bộ `this.getTitle("b1")` trong `BookService` để quan sát sự khác biệt với gọi qua Spring bean. Cuối cùng cấu hình TTL với một provider có hỗ trợ và tự xác nhận hành vi sau khi entry hết hạn.

## 8. Lỗi phổ biến và checklist tự kiểm tra

- **Annotation không có tác dụng:** chưa bật `@EnableCaching`, thiếu `CacheManager`, object không do Spring quản lý, method không đi qua proxy hoặc self-invocation.
- **Trả dữ liệu sai người/sai ngữ cảnh:** key thiếu tenant, locale, phân quyền hay điều kiện nghiệp vụ; cùng key bị dùng cho nhiều kết quả khác nhau.
- **Dữ liệu cũ sau update/delete:** thiếu `@CacheEvict`/`@CachePut`, sai cache name/key, invalidation trước khi transaction commit hoặc cập nhật cache không cùng nguồn.
- **Bộ nhớ tăng, dữ liệu không hết hạn:** tưởng Spring Cache tự có TTL/giới hạn; phải kiểm tra khả năng và cấu hình provider.
- **Hiệu năng không cải thiện:** ít truy cập lặp lại, key quá phân mảnh, serialization/network tốn kém hoặc stampede khi miss. Cần đo trước/sau, không chỉ thấy annotation mà kết luận nhanh.
- **Test phụ thuộc thứ tự chạy:** cache tồn tại giữa các testcase; dùng cache manager phù hợp, cô lập state hoặc dọn cache rõ ràng.
- **Dùng `@CachePut` như `@Cacheable`:** `@CachePut` luôn chạy phương thức nên không giúp bỏ qua phép tính/đọc nguồn khi hit.

Trước khi coi một bài thực hành hoàn tất, tự trả lời: (1) entry được lưu ở đâu? (2) key được tính từ gì? (3) ai quyết định entry hết hạn? (4) dữ liệu gốc thay đổi thì entry nào bị ảnh hưởng? (5) gọi từ đâu để proxy có hiệu lực? (6) bằng chứng hit/miss và dữ liệu đúng là gì?

## Tài liệu chính thống để đọc tiếp

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Boot — Caching: https://docs.spring.io/spring-boot/reference/io/caching.html
