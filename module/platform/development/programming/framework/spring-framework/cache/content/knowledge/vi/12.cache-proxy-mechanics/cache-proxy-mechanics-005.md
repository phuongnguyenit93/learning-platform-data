# Annotation trên giao diện so với lớp cài đặt trong Spring Cache

## Mục tiêu

Bài học thuộc nhóm **Cơ chế proxy**. Sau khi học, bạn có thể:

- Phân biệt khai báo `@Cacheable`, `@CachePut`, `@CacheEvict` trên **interface** và trên **phương thức của lớp triển khai**.
- Giải thích JDK dynamic proxy và class-based proxy (CGLIB) ảnh hưởng thế nào đến phương thức mà Spring có thể chặn.
- Hiểu vì sao Spring khuyên đặt cache annotation trên **lớp cụ thể**, dù một số khai báo trên interface vẫn hoạt động khi dùng proxy mode.
- Viết ứng dụng Spring Boot Java 17+ kiểm chứng một method implementation được cache qua interface proxy.
- Phát hiện self-invocation, method không public/final, bean tạo ngoài container và nhầm lẫn giữa Java annotation inheritance với Spring annotation lookup.

**Quy tắc thực hành:** trong dự án Spring Cache, ưu tiên đặt annotation trên phương thức `public` của **concrete service class** rồi gọi service qua Spring bean. Interface giữ hợp đồng nghiệp vụ; lớp triển khai gắn chính sách cache cụ thể. Cách này rõ ràng, thuận lợi khi đổi cơ chế proxy hoặc tích hợp AspectJ.

## 1. Hai vị trí có thể khai báo annotation

Giả sử có hợp đồng tìm sách:

```java
public interface BookQuery {
    String findById(String id);
}
```

Bạn có thể chọn một trong hai cách, **không cần khai báo cả hai cùng lúc**.

### Cách A — Đặt annotation trên interface

```java
public interface BookQuery {
    @Cacheable(cacheNames = "books", key = "#p0")
    String findById(String id);
}

@Service
public class BookQueryImpl implements BookQuery {
    @Override
    public String findById(String id) {
        return loadFromRepository(id);
    }
}
```

Trong mã minh họa, `loadFromRepository` là hàm nghiệp vụ chưa triển khai; đoạn này thể hiện **vị trí annotation**, không phải ví dụ độc lập để biên dịch. Lớp cài đặt có thể không chứa annotation, trong khi Spring caching proxy mode có cơ chế tìm metadata trên interface.

### Cách B — Đặt annotation trên lớp triển khai (khuyến nghị)

```java
public interface BookQuery {
    String findById(String id);
}

@Service
public class BookQueryImpl implements BookQuery {
    @Override
    @Cacheable(cacheNames = "books", key = "#p0")
    public String findById(String id) {
        return loadFromRepository(id);
    }
}
```

Với cách B, chính phương thức thực thi mang quy tắc cache. Spring có thể tìm cache operation từ **most specific method** trên target class khi lời gọi đi qua proxy. Cách B không phụ thuộc việc người đọc hợp đồng interface có hiểu hết chiến lược backend, TTL hay invalidation của service.

**Lưu ý:** Java không tự “sao chép” method annotation từ interface sang method override trong implementation. Ngay cả `@Inherited` của Java cũng không làm method annotation tự kế thừa từ interface. Spring có bộ đọc annotation/operation riêng, nên **đừng suy luận hành vi runtime chỉ bằng `BookQueryImpl.class.getMethod(...).getAnnotations()`**.

## 2. Spring Cache chặn lời gọi bằng cách nào?

Với `@EnableCaching` ở `mode = AdviceMode.PROXY` (cấu hình mặc định), Spring tạo hoặc sử dụng một **proxy** cho bean được cache. Client gọi vào proxy, proxy nhờ caching interceptor xem có hit hay không; nếu miss mới chạy method đích.

```text
Caller / Controller / CommandLineRunner
               |
               v
       Spring proxy của BookQuery
               |
               v
  CacheInterceptor + cache operation metadata
       /                         \
   cache HIT                  cache MISS
       |                         |
       |                    BookQueryImpl.findById()
       |                         |
       |                    put kết quả vào cache
       \_________________________/
               |
               v
             Kết quả
```

Điều quan trọng là **đường gọi** và **metadata annotation**, không phải chỉ vị trí chữ `@Cacheable` trong file nguồn. Nếu chương trình gọi thẳng đối tượng được tạo bằng `new` hoặc gọi `this.findById(...)` bên trong cùng target bean, proxy có thể không tham gia, nên annotation không có tác dụng ở proxy mode.

Spring AOP có hai kiểu proxy thường gặp:

| Khía cạnh | JDK dynamic proxy | Class-based proxy (CGLIB) |
| --- | --- | --- |
| Proxy đại diện cho | Các **interface** mà bean triển khai. | Một **subclass** của lớp đích. |
| Lời gọi có thể được intercept | Các method được expose qua interface của proxy. | Các method có thể override/intercept trên lớp đích. |
| Kiểu thường dùng để inject | Interface `BookQuery`. | Có thể dùng interface hoặc concrete type nếu phù hợp cấu hình. |
| Yêu cầu | Bean có interface phù hợp. | Class không `final`; method cần advice không `final`/`private`. |
| Annotation trên concrete implementation | Spring Cache có thể resolve metadata trên target method dù caller dùng interface. | Spring Cache cũng đọc metadata từ concrete method. |
| Annotation chỉ nằm trên interface | Có thể được nhận diện trong Spring **proxy mode**; cần kiểm thử phiên bản/cấu hình cụ thể. | Không nên dựa vào giả định từ Java annotation inheritance; Spring hiện đại có cơ chế metadata lookup riêng, cần kiểm thử. |

**Không nhầm hai câu hỏi:**

1. *Proxy có thể chặn lời gọi này không?* Phụ thuộc JDK/CGLIB, method visibility, `final`, self-invocation và đường inject/gọi.
2. *Khi đã chặn, Spring tìm thấy cache operation nào?* Phụ thuộc nơi khai báo annotation, cách Spring đọc metadata, cấu hình và phiên bản.

Một lỗi có thể nằm ở bất kỳ câu hỏi nào. Ví dụ annotation đúng trên implementation vẫn không cứu được lời gọi `this.findById(id)` không đi qua proxy.

## 3. Annotation trên interface: được hỗ trợ đến đâu?

Tài liệu Spring Framework hiện hành về caching khuyên khai báo `@Cache*` trên lớp/phương thức cụ thể. Tài liệu cũng nêu annotation trên interface **có thể hoạt động với `mode="proxy"`**; trái lại, với `mode="aspectj"`, cấu hình cache chỉ khai báo ở interface **không được weaving infrastructure nhận diện**.

Vì vậy nên phân biệt:

- **Trong proxy mode:** Spring có khả năng tìm cache metadata gắn ở interface; hành vi chính xác với JDK proxy hoặc class-based proxy nên được kiểm chứng trên **phiên bản Spring thực tế của dự án**. Đừng mặc định mọi runtime, mọi cách tạo proxy và mọi framework integration sẽ xử lý giống nhau.
- **Trong AspectJ weaving mode:** đặt cache annotation trên concrete implementation để weaver có annotation trên phần mã cần xử lý. Interface-only declaration không phải cấu hình an toàn cho chế độ này.
- **Khi chuyển phiên bản hoặc cấu hình:** một dự án từng chạy với JDK proxy có thể chuyển sang class-based proxy qua cờ cấu hình/AOP khác. Đặt annotation trên implementation giúp chính sách cache rõ hơn và giảm phụ thuộc vào cách framework tìm annotation trên interface.
- **Với annotation khác (`@Transactional`, `@Async`...):** chúng có semantics, proxy và metadata resolver riêng. Không suy luận “đặt interface luôn được” hoặc “đặt interface không bao giờ được” cho mọi loại annotation.

Một số tài liệu Spring cũ từng mô tả chặt chẽ rằng annotation ở interface chỉ nên dựa vào JDK interface proxy. Tài liệu Spring Framework mới mô tả rộng hơn về proxy mode. Khi phải duy trì hệ thống nhiều phiên bản, **chọn concrete-method annotation và test integration** là cách giảm mơ hồ.

## 4. Vì sao nên đặt annotation trên concrete implementation?

Có bốn lý do thực tế:

1. **Gắn chính sách sát công việc:** caching là chính sách thực thi của một implementation: cache name, key, condition, `unless`, backend và vòng đời dữ liệu. Hai implementation của cùng interface có thể có nguồn dữ liệu và freshness khác nhau.
2. **Dễ đọc và review:** người sửa query thấy ngay `@Cacheable` và biết khi nào logic không chạy. Điều này đặc biệt quan trọng nếu method có side effect hoặc kiểm tra phân quyền.
3. **Ổn định hơn khi thay proxy/weaving:** implementation có metadata trực tiếp, trong khi interface-only phụ thuộc khả năng tra cứu annotation và không phù hợp AspectJ weaving.
4. **Tránh xung đột metadata:** nếu interface ghi `@Cacheable("publicBooks")` nhưng implementation ghi `@Cacheable("privateBooks")`, việc ưu tiên/ghép annotation dễ gây nhầm. Định nghĩa quy tắc cache ở một vị trí chủ đạo và test key/cache được dùng.

Điều đó **không cấm** interface chứa annotation trong mọi trường hợp. Với thư viện API nội bộ được kiểm soát chặt phiên bản Spring và chỉ sử dụng proxy mode, annotation trên interface có thể là một chủ đích. Khi chọn hướng đó, viết integration test xác nhận cache hit/miss cho chính bean proxy.

## 5. Ví dụ chạy được: interface contract, annotation tại implementation

Demo dùng Java 17+ và một dự án Spring Boot Gradle hiện có. Nó cố ý dùng **JDK dynamic proxy** để chứng minh annotation đặt trên implementation **vẫn có hiệu lực dù caller inject interface**.

Trong `build.gradle`, dùng starter cache (giữ nguyên plugin/version và các dependency khác của dự án):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
```

**File `src/main/resources/application.properties`:**

```properties
# Chọn interface-based proxy rõ ràng cho demo.
spring.aop.proxy-target-class=false
```

**File `src/main/java/example/cacheproxy/BookQuery.java`:**

```java
package example.cacheproxy;

public interface BookQuery {
    String findById(String id);
    int sourceReadCount();
}
```

Interface ở đây **không có** annotation; nó chỉ mô tả những method mà caller có thể sử dụng qua proxy.

**File `src/main/java/example/cacheproxy/BookQueryImpl.java`:**

```java
package example.cacheproxy;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class BookQueryImpl implements BookQuery {

    private final AtomicInteger sourceReads = new AtomicInteger();

    @Override
    @Cacheable(cacheNames = "books", key = "#p0")
    public String findById(String id) {
        System.out.println("SOURCE_READ #" + sourceReads.incrementAndGet());
        return "Book-" + id;
    }

    @Override
    public int sourceReadCount() {
        return sourceReads.get();
    }
}
```

Annotation nằm trên method `public` của lớp cài đặt. Mỗi lần thật sự chạy `findById`, bộ đếm `sourceReads` tăng và in một dòng.

**File `src/main/java/example/cacheproxy/CacheProxyDemoApplication.java`:**

```java
package example.cacheproxy;

import org.springframework.aop.support.AopUtils;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching(proxyTargetClass = false)
public class CacheProxyDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CacheProxyDemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books");
    }

    @Bean
    CommandLineRunner demo(BookQuery query) {
        return args -> {
            System.out.println("JDK proxy = " + AopUtils.isJdkDynamicProxy(query));
            System.out.println("first = " + query.findById("B1"));
            System.out.println("second = " + query.findById("B1"));
            System.out.println("sourceReads = " + query.sourceReadCount());
        };
    }
}
```

Chạy tại thư mục dự án:

```bash
./gradlew bootRun
# Windows PowerShell: .\gradlew.bat bootRun
```

Các dòng **`System.out` do demo tạo ra**, bỏ qua log Spring Boot và Gradle, có thứ tự:

```text
JDK proxy = true
SOURCE_READ #1
first = Book-B1
second = Book-B1
sourceReads = 1
```

Vì sao?

1. `BookQueryImpl` là Spring bean và thực thi `BookQuery`, có method public mang `@Cacheable`; `@EnableCaching` bật interceptor.
2. Cấu hình proxy class = false cùng thuộc tính AOP của Boot chọn JDK dynamic proxy cho trường hợp có interface.
3. `CommandLineRunner` nhận bean dưới kiểu **`BookQuery`**, tức là gọi qua proxy, không tạo trực tiếp bằng `new`.
4. Lần `findById("B1")` đầu miss, thân method in `SOURCE_READ #1` và trả `Book-B1`; Spring cache kết quả dưới key `"B1"`.
5. Lần thứ hai cùng key hit nên thân implementation không chạy; `sourceReadCount()` vẫn bằng 1.

Demo dùng một nguồn giả lập nên không có database, TTL, concurrency hay transaction. `ConcurrentMapCacheManager` phục vụ việc quan sát hit/miss, không có TTL mặc định. Các file thuộc **một dự án Spring Boot**, không phải mã Java một file biên dịch bằng `javac` không kèm dependency.

### Thử class-based proxy trên cùng implementation

Giữ annotation tại `BookQueryImpl.findById`, chỉ thay hai cấu hình để chọn class-based proxy:

```java
@EnableCaching(proxyTargetClass = true)
```

```properties
spring.aop.proxy-target-class=true
```

Khởi động lại ứng dụng để tránh state cache từ lượt chạy trước. Với `BookQueryImpl` không `final` và method được cache public, việc cache vẫn hoạt động. Dòng `JDK proxy = ...` lúc này dự kiến là `false` vì proxy đã chuyển sang class-based; `SOURCE_READ` vẫn chỉ xuất hiện một lần cho hai lượt gọi cùng key. Có thể thay dòng kiểm tra bằng `AopUtils.isCglibProxy(query)` để quan sát `true`.

**Không bắt buộc thay proxy để “sửa” annotation trên implementation:** chính sách cache đúng ở concrete method đã phù hợp với cả hai cách proxy trong điều kiện method có thể được intercept.

## 6. Thử đưa annotation sang interface: diễn giải kết quả cẩn thận

Từ demo, thử biến thể sau **trong môi trường học tập**:

- Chuyển nguyên `@Cacheable(cacheNames="books", key="#p0")` từ `BookQueryImpl.findById` sang `BookQuery.findById`.
- Bỏ annotation ở concrete implementation, để tránh hai nguồn cấu hình.
- Giữ proxy mode và chạy lại, quan sát `SOURCE_READ`, `AopUtils.isJdkDynamicProxy` và kết quả lần hai.
- Thử với class-based proxy và phiên bản Spring đang dùng; ghi nhận thực tế thay vì giả định từ annotation inheritance của Java.
- Nếu chuyển sang `mode=AdviceMode.ASPECTJ`, không xem interface-only annotation là đủ; cần annotation trên concrete method và cấu hình AspectJ weaving thật sự.

Đây là **một thao tác so sánh**, không phải mã gốc bắt buộc của demo. Nếu không thấy hit, xác định đúng nguyên nhân bằng kiểm tra proxy, nguồn annotation metadata và cấu hình caching. Không kết luận lỗi “interface annotation luôn không hoạt động” chỉ từ một thử nghiệm thiếu proxy.

## 7. Những lỗi không liên quan vị trí annotation nhưng thường bị chẩn đoán nhầm

### 7.1. Self-invocation

```java
@Service
public class BookQueryImpl implements BookQuery {
    @Cacheable(cacheNames = "books", key = "#p0")
    public String findById(String id) {
        return "Book-" + id;
    }

    public String findTwice(String id) {
        return this.findById(id) + "," + this.findById(id);
    }

    @Override
    public int sourceReadCount() { return 0; }
}
```

Đoạn trên **chỉ để minh họa**; nếu ghép vào dự án phải điều chỉnh đúng class, khai báo `@Override` và import. Hai lời gọi `this.findById` trong cùng bean đi trực tiếp vào target, bỏ qua proxy ở proxy mode; vị trí annotation ở interface hay implementation không giải quyết được. Tách phần gọi sang bean khác hoặc gọi qua injected proxy của service.

### 7.2. Inject concrete type khi bean là JDK proxy

```java
// Không phù hợp nếu bean được proxy chỉ qua interface:
@Autowired
private BookQueryImpl bookQueryImpl;
```

Với JDK dynamic proxy, proxy không phải subclass của `BookQueryImpl`; inject bằng concrete type có thể thất bại. Dùng `BookQuery`:

```java
@Autowired
private BookQuery bookQuery;
```

Hai field minh họa thuộc một component được Spring quản lý. Nếu cần phụ thuộc trực tiếp vào method chỉ có ở concrete class, cân nhắc lại hợp đồng interface hoặc chọn class-based proxy một cách có chủ đích và kiểm thử.

### 7.3. Class/method final, private và visibility

- Class-based proxy cần subclass nên **không thể override final class/method**; private method cũng không được intercept kiểu subclass.
- JDK proxy chỉ expose các method qua interface; một method riêng của implementation không nằm trong interface không gọi được bằng JDK proxy reference.
- Với cache annotations, đường đơn giản và dễ mang đi giữa cấu hình là đặt trên **method public**, không dựa vào các ngóc ngách visibility của từng Spring version.
- Java record là final; đừng tự giả định record service sẽ hoạt động với class-based AOP proxy.

### 7.4. Quên kích hoạt caching hoặc chọn sai CacheManager

Cần `@EnableCaching` và một `CacheManager` hợp lệ (hoặc cấu hình Spring Boot tương ứng). Nếu annotation ghi `cacheNames="books"` nhưng manager không có vùng `books`, lời gọi có thể thất bại khi resolve cache. Đây là lỗi cấu hình cache name, không phải do annotation ở interface.

### 7.5. Gọi bean trong giai đoạn khởi tạo

Proxy phải được tạo và khởi tạo trước khi hành vi AOP hoạt động đáng tin cậy. Không dùng `@PostConstruct` gọi vào chính method cache của bean để chứng minh proxy; callback khởi tạo có thể chạy trước điểm thích hợp.

### 7.6. AspectJ không cùng cơ chế với proxy

Với `AdviceMode.ASPECTJ`, Spring sử dụng AspectJ weaving để gắn logic caching vào bytecode. Self-invocation có thể được xử lý theo weaving, nhưng cần dependency/weaving đúng. Annotation chỉ trên interface không được AspectJ cache aspect nhận diện như annotation trên method concrete. Vì vậy, tránh “chuyển sang AspectJ là mọi annotation trên interface cũng sẽ hoạt động”.

## 8. Bảng quyết định cho dự án thực tế

| Tình huống | Cách viết nên chọn | Vì sao |
| --- | --- | --- |
| Service có interface, gọi qua JDK proxy | Annotation trên **implementation method public** | Spring có thể tra operation ở target method; hợp đồng interface sạch. |
| Service dùng class-based proxy | Annotation trên **implementation method public**, class/method không final | Rõ nơi policy áp dụng; method có thể được subclass intercept. |
| Service có nhiều implementation khác nhau | Từng implementation tự định nghĩa policy cache | Cache name, key/freshness có thể khác giữa implementation. |
| Code chỉ có interface-only cache annotation | Chạy integration test trên proxy mode/phiên bản đang triển khai | Cần xác nhận Spring tìm metadata như mong đợi. |
| Dự kiến dùng AspectJ weaving | Annotation trên concrete method | Không dựa vào metadata interface-only. |
| Cần chỉ rõ key, TTL, provider | Đặt key/cache config nơi thực thi; TTL ở backend | Interface annotation không giải quyết lifecycle backend. |
| Method bị gọi trong cùng bean | Thiết kế lại ranh giới lời gọi để đi qua proxy | Vị trí annotation không sửa được self-invocation. |

### Checklist trước khi merge

1. [ ] Bean được Spring quản lý; không dùng `new` ngoài container rồi chờ cache advice.
2. [ ] `@EnableCaching` và `CacheManager`/cache name đã cấu hình đúng.
3. [ ] Đã xác định JDK hay class-based proxy bằng cấu hình và/hoặc `AopUtils`.
4. [ ] Method cache public và nằm trên đường gọi **qua proxy**.
5. [ ] Annotation `@Cacheable`, `@CachePut`, `@CacheEvict` ưu tiên ở concrete method; key/cache name nhất quán.
6. [ ] Nếu dùng annotation tại interface, đã có integration test cho proxy type/Spring version đang deploy.
7. [ ] Không phụ thuộc vào interface annotation khi dùng AspectJ weaving.
8. [ ] Test lần gọi thứ nhất miss, lần hai hit bằng bộ đếm thật; test các nhánh update/evict và key khác.
9. [ ] Có bảo đảm phân quyền vẫn được thực thi cả khi cache hit; không đặt authorization chỉ bên trong method có thể bị cache bỏ qua.

## Bài tập

1. Chạy demo gốc và kiểm tra `JDK proxy = true`, `SOURCE_READ #1` chỉ xuất hiện một lần.
2. Chuyển annotation sang interface và giữ JDK proxy. So sánh hành vi cache bằng bộ đếm, không chỉ bằng giá trị trả về.
3. Đổi sang class-based proxy (khởi động lại), xác minh `AopUtils.isCglibProxy` và hit/miss. Ghi lại sự khác nhau khi metadata nằm trên interface hoặc implementation trong phiên bản bạn dùng.
4. Thử inject `BookQueryImpl` khi đang dùng JDK proxy; phân tích vì sao nên inject interface.
5. Thêm phương thức `findByIdTwice` gọi `this.findById` bên trong implementation; quan sát khác biệt so với hai lời gọi từ `CommandLineRunner` và sửa bằng cách chuyển lời gọi qua bean khác.
6. Thêm `@CacheEvict(cacheNames="books", key="#p0")` vào một method update public của concrete class; xác minh sau update, lần đọc đầu mới miss rồi cache lại.
7. Với một dự án có kế hoạch chuyển `AdviceMode.ASPECTJ`, kiểm kê tất cả annotation cache ở interface rồi đưa về concrete methods và viết integration test.

## Tài liệu chính thức

- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — Understanding the Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Boot — Caching: https://docs.spring.io/spring-boot/reference/io/caching.html
