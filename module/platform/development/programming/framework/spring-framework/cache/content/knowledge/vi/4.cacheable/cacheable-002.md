# Áp dụng @Cacheable ở cấp lớp và từng phương thức trong Spring Framework

## 1. @Cacheable hoạt động ở hai phạm vi nào?

Trong Spring Cache, `@Cacheable` mô tả chính sách lưu **kết quả lời gọi phương thức** theo khóa. Lần gọi đầu với một khóa chưa được lưu thường là **cache miss**: Spring chạy phương thức và lưu giá trị nếu điều kiện cho phép. Lần sau nếu cache có giá trị tương ứng là **cache hit**: interceptor trả dữ liệu cache mà thông thường không thực thi thân phương thức.

Annotation `org.springframework.cache.annotation.Cacheable` cho phép đặt trên `METHOD` **hoặc** `TYPE` (lớp). Khác biệt nằm ở phạm vi những phương thức nhận chính sách này:

| Cách khai báo | Những phương thức được cache | Cách dùng phù hợp |
| --- | --- | --- |
| **Cấp phương thức**: đặt `@Cacheable` trước `findById` | Riêng phương thức được đánh dấu; phương thức khác trong cùng lớp không tự nhận chính sách. | Service có lẫn đọc và ghi; mỗi truy vấn có nhu cầu cache khác nhau. |
| **Cấp lớp**: đặt `@Cacheable` trước `class` | Các phương thức của lớp được Spring cache interceptor xử lý; trong proxy mode thông dụng, chú trọng phương thức `public` được gọi **qua Spring proxy**. | Một lớp chỉ dành cho thao tác đọc có thể cache và dùng quy tắc khóa nhất quán. |

**Điểm cần nhớ:** `@Cacheable` đặt trên lớp *có thể thực sự cache các method của lớp dù các method đó không mang annotation riêng*. Trong khi đó, `@CacheConfig` đặt trên lớp **không kích hoạt cache**: nó chỉ cung cấp cấu hình dùng chung cho các cache operation được khai báo.

Đặt annotation không có nghĩa mọi lời gọi đều được cache: cần bật `@EnableCaching`, có `CacheManager` thích hợp, gọi qua bean/proxy đủ điều kiện và đáp ứng `condition`, `unless` cùng chính sách của provider.

## 2. @Cacheable cấp phương thức: chọn đúng thao tác đọc

Một service có nhiều trách nhiệm nên khai báo cache ở những method thực sự cần tối ưu:

~~~java
@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "productNames", key = "#p0")
    public String findName(String productId) {
        return repository.findName(productId);
    }

    public String findCategory(String productId) {
        return repository.findCategory(productId);
    }

    public void updateName(String productId, String newName) {
        repository.updateName(productId, newName);
    }
}
~~~

*Đoạn trên minh họa cách khai báo; giả định dự án đã định nghĩa `ProductRepository`, bật caching và có cache tên `productNames`. Nó không phải chương trình Java độc lập.*

Giả sử một client dùng Spring bean gọi `findName("p1")` hai lần:

1. Lần đầu, khóa `p1` trong `productNames` chưa có → **miss**, repository được gọi và giá trị có thể được cache.
2. Lần hai, nếu khóa vẫn còn hiệu lực → **hit**, Spring trả kết quả mà không chạy `findName`.
3. Gọi `findCategory("p1")` hai lần vẫn thực thi repository **hai lần** vì method ấy không có `@Cacheable` và lớp cũng không có `@Cacheable`.
4. `updateName(...)` vẫn thực thi bình thường, nhưng **không tự xóa** giá trị của `findName` trong cache. Khi dữ liệu nguồn thay đổi, cần áp dụng invalidation hoặc cập nhật cache (chẳng hạn một chính sách `@CacheEvict` phù hợp).

`cacheNames` chọn nơi lưu giá trị; `key` quyết định định danh phần tử. Biểu thức `#p0` chỉ **tham số thứ nhất**, hữu ích khi Java không giữ tên tham số trong bytecode. Nếu không viết `key`, Spring dùng bộ tạo khóa mặc định dựa trên danh sách tham số.

Cách khai báo ở method làm rõ tại nơi đọc code rằng `findName` có cache còn `findCategory` không. Nó cũng giúp định nghĩa riêng từng cache, khóa, điều kiện và chiến lược cập nhật khi các method có đặc điểm khác nhau.

## 3. @Cacheable cấp lớp: phạm vi rộng hơn

Nếu một lớp chỉ gồm các thao tác đọc có thể cache, có thể đưa `@Cacheable` lên class:

~~~java
@Service
@Cacheable(
    cacheNames = "productReadModels",
    key = "#root.methodName + ':' + #p0"
)
public class ProductReadService {
    private final ProductRepository repository;

    public ProductReadService(ProductRepository repository) {
        this.repository = repository;
    }

    public String findName(String productId) {
        return repository.findName(productId);
    }

    public String findCategory(String productId) {
        return repository.findCategory(productId);
    }
}
~~~

*Đây là đoạn minh họa, chưa phải file chạy độc lập.*

Cả `findName("p1")` và `findCategory("p1")` đều có chính sách cache của lớp. Biểu thức `#root.methodName` là tên phương thức đang được gọi trong ngữ cảnh SpEL của Spring Cache:

- `findName("p1")` tạo khóa `findName:p1`.
- `findCategory("p1")` tạo khóa `findCategory:p1`.

### Vì sao khóa ở cấp lớp rất quan trọng?

Bộ tạo khóa mặc định `SimpleKeyGenerator` thường chỉ dựa trên **các tham số**, không tự thêm tên method. Với hai method cùng nhận `"p1"` và cùng cache `productReadModels`, cả hai có thể dùng một khóa `p1`. Khi đó kết quả `findName` được lưu trước có thể bị `findCategory` trả nhầm, dù hai method phải trả các kiểu/nội dung khác nhau.

Giải pháp là chọn namespace cache riêng cho từng loại kết quả hoặc tạo khóa có xét danh tính phương thức, như `#root.methodName + ':' + #p0`. Nếu một phương thức cần khóa phức tạp hơn, có thể dùng `key` hoặc `keyGenerator` phù hợp ở cấp method.

**Không đặt `@Cacheable` trên cả lớp chỉ để “tối ưu đồng loạt”.** Nếu về sau thêm phương thức có side effect như `update`, `sendEmail`, `incrementCounter`, `charge`, lần hit có thể khiến thân phương thức bị bỏ qua. Đặt annotation cấp lớp chỉ an toàn khi phạm vi các method được cache được hiểu rõ và phù hợp về nghiệp vụ.

## 4. Ví dụ hoàn chỉnh: quan sát cả hai cách bằng Java 17+ và Spring Boot 3.x

Ví dụ dùng `spring-boot-starter-cache`, `@EnableCaching` và `ConcurrentMapCacheManager`. Hai vùng cache độc lập (`byClass` và `byMethod`) giúp thấy rõ hành vi của từng kiểu khai báo. `ConcurrentMapCacheManager` lưu trong RAM của tiến trình; demo tập trung vào phạm vi annotation, không có yêu cầu TTL hay Redis.

Trong **dự án Spring Boot 3.x đã cấu hình plugin Java/Spring Boot**, thêm dependency vào `build.gradle` (Groovy DSL):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

Tạo file **`src/main/java/com/example/cacheplacement/CachePlacementApplication.java`** với mã Java hoàn chỉnh:

~~~java
package com.example.cacheplacement;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class CachePlacementApplication {

    public static void main(String[] args) {
        SpringApplication.run(CachePlacementApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("byClass", "byMethod");
    }

    @Bean
    ProductSource productSource() {
        return new ProductSource();
    }

    @Bean
    ClassLevelService classLevelService(ProductSource source) {
        return new ClassLevelService(source);
    }

    @Bean
    MethodLevelService methodLevelService(ProductSource source) {
        return new MethodLevelService(source);
    }

    @Bean
    CommandLineRunner compare(ClassLevelService byClass,
                              MethodLevelService byMethod) {
        return args -> {
            System.out.println("C1=" + byClass.findName("p1"));
            System.out.println("C2=" + byClass.findName("p1"));
            System.out.println("C3=" + byClass.findCategory("p1"));
            System.out.println("C4=" + byClass.findCategory("p1"));

            System.out.println("M1=" + byMethod.findName("p1"));
            System.out.println("M2=" + byMethod.findName("p1"));
            System.out.println("M3=" + byMethod.findCategory("p1"));
            System.out.println("M4=" + byMethod.findCategory("p1"));
        };
    }

    public static class ProductSource {
        public String loadName(String id) {
            System.out.println("DB name " + id);
            return "Bàn phím " + id;
        }

        public String loadCategory(String id) {
            System.out.println("DB category " + id);
            return "Phụ kiện " + id;
        }
    }

    // Cả hai method có chính sách cache chung ở cấp lớp.
    @Cacheable(
        cacheNames = "byClass",
        key = "#root.methodName + ':' + #p0"
    )
    public static class ClassLevelService {
        private final ProductSource source;

        public ClassLevelService(ProductSource source) {
            this.source = source;
        }

        public String findName(String id) {
            return source.loadName(id);
        }

        public String findCategory(String id) {
            return source.loadCategory(id);
        }
    }

    // Chỉ findName được cache.
    public static class MethodLevelService {
        private final ProductSource source;

        public MethodLevelService(ProductSource source) {
            this.source = source;
        }

        @Cacheable(cacheNames = "byMethod", key = "#p0")
        public String findName(String id) {
            return source.loadName(id);
        }

        public String findCategory(String id) {
            return source.loadCategory(id);
        }
    }
}
~~~

Chạy từ thư mục gốc dự án đã cấu hình Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
gradlew.bat bootRun
~~~

Bỏ qua log khởi động của Gradle/Spring Boot; **các dòng do demo chủ động in ra** là:

~~~text
DB name p1
C1=Bàn phím p1
C2=Bàn phím p1
DB category p1
C3=Phụ kiện p1
C4=Phụ kiện p1
DB name p1
M1=Bàn phím p1
M2=Bàn phím p1
DB category p1
M3=Phụ kiện p1
DB category p1
M4=Phụ kiện p1
~~~

| Lần gọi | Gọi `ProductSource`? | Giải thích |
| --- | --- | --- |
| `C1` | Có | `findName:p1` lần đầu miss trong `byClass`. |
| `C2` | Không | Lần thứ hai hit của `findName:p1`. |
| `C3` | Có | `findCategory:p1` là khóa khác, miss. |
| `C4` | Không | Lần thứ hai hit của `findCategory:p1`; đây là hiệu quả của annotation **trên lớp**. |
| `M1` | Có | `findName` có `@Cacheable` cấp method; lần đầu miss trong `byMethod`. |
| `M2` | Không | Lần thứ hai hit của method được đánh dấu. |
| `M3`, `M4` | **Có ở cả hai lần** | `findCategory` không mang annotation và lớp cũng không mang `@Cacheable`. |

Hai service được đưa vào Spring context bằng `@Bean`; `CommandLineRunner` nhận chúng qua dependency injection. Vì vậy lời gọi đi qua proxy của Spring, cho phép cache interceptor hoạt động. Nếu tạo chúng bằng `new` bên ngoài Spring rồi gọi trực tiếp, annotation không tự có hiệu lực.

**Phân biệt cách biên dịch:** File Java ở trên là mã đầy đủ trong một dự án **Spring Boot**, dùng dependency Spring và cơ chế khởi động Spring context. Nó không phải file chỉ dùng JDK thuần để chạy bằng `javac`/ `java` mà thiếu classpath. Lệnh `bootRun` cung cấp môi trường chạy phù hợp.

## 5. @CacheConfig ở cấp lớp khác gì @Cacheable ở cấp lớp?

`@CacheConfig` dùng để chia sẻ các thuộc tính mặc định như `cacheNames`, `keyGenerator`, `cacheManager` hay `cacheResolver`. Bản thân `@CacheConfig` **không tạo cache operation** cho mọi phương thức.

Ví dụ minh họa:

~~~java
@CacheConfig(cacheNames = "products")
@Service
public class SelectiveProductService {

    @Cacheable(key = "#p0")
    public String findName(String id) {
        return loadNameFromSource(id);
    }

    public String findCategory(String id) {
        return loadCategoryFromSource(id);
    }
}
~~~

*Đoạn này chỉ minh họa annotation; hai hàm `loadNameFromSource` và `loadCategoryFromSource` cần được người viết ứng dụng triển khai, nên không biên dịch độc lập.*

Ở đây:

- `findName` được cache bởi vì nó **có `@Cacheable`**; tên cache `products` được lấy từ `@CacheConfig`.
- `findCategory` vẫn không được cache, dù cùng lớp với `@CacheConfig`.
- Tham số của cache operation khai báo ở cấp phương thức có thể ghi đè giá trị mặc định của `@CacheConfig`.
- Khi một method có cache annotation riêng còn class có `@Cacheable`, Spring ưu tiên metadata cache áp dụng trực tiếp trên method. Có thể tùy biến từng phương thức, nhưng cần tránh thiết kế chồng chéo làm người đọc khó xác định cache nào được sử dụng.

Trong đa số service vừa đọc vừa ghi, cách dễ kiểm soát là `@CacheConfig` để dùng chung cấu hình và `@Cacheable` đặt đúng những method cần cache.

## 6. Điều kiện để annotation có hiệu lực

`@EnableCaching` cho phép Spring áp dụng annotation thông qua AOP. Chế độ mặc định là **proxy**, vì vậy cần chú ý các điểm sau:

1. **Spring-managed bean:** Đối tượng tạo bằng `new` không được tự động bọc bởi caching proxy. Dùng bean được Spring quản lý và inject vào caller.
2. **External call:** Một method trong bean gọi `this.findName(id)` sẽ không đi qua proxy trong chế độ thông thường. Đây là *self-invocation*; annotation có thể xuất hiện trong source code nhưng không kích hoạt caching cho lời gọi nội bộ ấy.
3. **Visibility:** Với proxy mode, nên dùng các method `public`. Đừng mặc định `private`, `protected` hay package-private được cache giống `public` trong mọi cấu hình.
4. **Vị trí class/interface:** Spring khuyến nghị đặt các cache annotation trên class triển khai cụ thể và các method của nó, vì annotation ở interface có thể phụ thuộc cách tạo proxy hoặc AspectJ.
5. **Vòng đời bean:** Không dựa vào lời gọi tại `@PostConstruct` để kiểm chứng cơ chế caching; proxy có thể chưa sẵn sàng theo cách bạn kỳ vọng.
6. **Tên và khóa cache:** Hai method khác nhau nhưng chung cache và chung bộ tham số có thể đụng khóa mặc định. Cẩn thận hơn khi áp dụng cache toàn lớp.
7. **Các điều kiện lưu:** `condition` dùng để quyết định áp dụng cache trước lời gọi; `unless` có thể từ chối lưu sau khi method chạy. Mỗi cache provider còn có chính sách riêng về lưu `null`, xóa, giới hạn dung lượng và hết hạn.

### Tương tác với phương thức ghi

`@Cacheable` phù hợp với **kết quả đọc** có thể dùng lại. Nó không tự theo dõi việc thay đổi database. Cả ở cấp lớp lẫn cấp method, khi có đường ghi dữ liệu cần thiết kế invalidation bằng `@CacheEvict`, cập nhật cache bằng `@CachePut`, TTL hoặc phối hợp sự kiện theo yêu cầu nhất quán.

Đặc biệt nguy hiểm nếu một lớp có `@Cacheable` ở trên cùng và sau đó được bổ sung method có side effect như `placeOrder`, `charge`, `incrementCounter`, `sendNotification`. Nếu lời gọi được interceptor cache xử lý và trở thành hit, **thân method có thể không chạy**. Hành vi này sai với thao tác ghi cần được thực thi. Nên tách các method có side effect sang bean riêng hoặc chỉ đánh dấu `@Cacheable` trên từng method đọc.

## 7. Chọn cách đặt annotation theo thiết kế service

| Tình huống | Đề xuất | Lý do |
| --- | --- | --- |
| Service có `findById`, `save`, `delete` | `@Cacheable` chỉ trên `findById` | Không tạo nguy cơ bỏ qua method có side effect. |
| Lớp chuyên đọc, mọi method đủ điều kiện được cache | Có thể dùng `@Cacheable` cấp lớp | Ít lặp annotation, nhưng phải quản lý khóa và kiểm soát method mới. |
| Nhiều method dùng chung `cacheNames`, chỉ vài method cần cache | `@CacheConfig` + `@Cacheable` trên method | Dùng chung cấu hình mà vẫn chọn lọc phạm vi. |
| Các method có khóa, điều kiện hoặc chiến lược invalidation khác nhau | `@Cacheable` trên từng method | Rõ ràng và dễ bảo trì. |
| Dữ liệu phải luôn phản ánh cập nhật mới nhất | Đánh giá lại việc cache và thiết kế consistency | Cấp đặt annotation không quyết định được độ mới của dữ liệu. |

Trước khi chuyển từ method-level lên class-level, nên rà soát tất cả phương thức đủ điều kiện trong lớp và các phương thức dự kiến sẽ được thêm sau này. Đây là thay đổi phạm vi chức năng, không chỉ là cách viết gọn.

## 8. Bài tập tự kiểm tra

**Câu 1.** Một lớp có `@Cacheable("catalog")`; `findName("p1")` và `findCategory("p1")` đều `public`, đều được gọi qua Spring proxy. Cả hai có thể dùng cache không?

**Đáp án:** Có. Đặt annotation ở cấp lớp áp dụng chính sách cache cho các method đủ điều kiện. Tuy nhiên, nếu dùng khóa mặc định và cùng cache, hai method cùng nhận `"p1"` có thể đụng khóa; cần thiết kế khóa có phân biệt kết quả.

**Câu 2.** Thay `@Cacheable("catalog")` bằng `@CacheConfig(cacheNames = "catalog")` mà không thêm annotation ở các method. Có cache hit không?

**Đáp án:** Không có cache operation nào được khai báo để kích hoạt caching cho các lời gọi. `@CacheConfig` chỉ chứa cấu hình mặc định.

**Câu 3.** `@Cacheable` có trên method, nhưng `this.findName("p1")` được gọi từ method khác của cùng bean. Tại sao không quan sát thấy cache hit?

**Đáp án:** Self-invocation không đi qua Spring caching proxy trong chế độ proxy mặc định. Cần gọi qua một bean/proxy hợp lệ hoặc dùng cơ chế weaving thích hợp nếu yêu cầu.

**Câu 4.** Service có method `charge(id)` thực hiện thanh toán. Có nên đặt `@Cacheable` toàn lớp để phương thức này chạy nhanh hơn không?

**Đáp án:** Không. Cache hit có thể bỏ qua thân method, vi phạm yêu cầu thực thi nghiệp vụ. Tính idempotent trong thanh toán cần được giải quyết bằng cơ chế nghiệp vụ, không phải `@Cacheable`.

**Câu 5.** Vì sao demo `C4` không in `DB category p1` nhưng `M4` lại in?

**Đáp án:** `C4` hit nhờ `@Cacheable` ở class `ClassLevelService`; `M4` gọi `findCategory` của `MethodLevelService`, vốn không được cache.

## 9. Tài liệu tham khảo

- [Javadoc `@Cacheable` — Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/annotation/Cacheable.html): phạm vi `TYPE`/`METHOD` và thuộc tính annotation.
- [Declarative Annotation-based Caching — Spring Framework](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): khóa SpEL, `@CacheConfig`, proxy, `@EnableCaching` và các giới hạn thực thi.

**Ghi nhớ:** `@Cacheable` ở **cấp phương thức** tác động tới method được đánh dấu; `@Cacheable` ở **cấp lớp** mở rộng chính sách tới các method của lớp đủ điều kiện. `@CacheConfig` giúp chia sẻ cấu hình khi vẫn muốn chọn chính xác những method được cache.
