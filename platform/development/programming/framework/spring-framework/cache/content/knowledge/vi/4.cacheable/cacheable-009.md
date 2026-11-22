# Kiểm chứng hành vi @Cacheable bằng số lần thực thi phương thức

> **Ngữ cảnh:** Spring Framework Cache — nhóm `@Cacheable`. Mục đích của bài là **chứng minh một cách quan sát được** rằng những lời gọi lặp có cùng cache key có thể nhận lại kết quả từ cache mà **không chạy lại thân phương thức nghiệp vụ**. Trọng tâm là phép đếm thực thi, cách xây dựng thí nghiệm có kiểm soát và kiểm thử tự động.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **số lần gọi phương thức từ client** với **số lần thân phương thức gốc được thực thi** khi Spring Cache hoạt động.
2. Tự xây dựng thí nghiệm cache miss/hit bằng `AtomicInteger`, log và các lời gọi có key giống/khác nhau.
3. Dự đoán chính xác bộ đếm trước và sau thao tác `evict` hoặc `clear`.
4. Viết một kiểm thử JUnit dùng Spring ApplicationContext để xác nhận caching bằng assertion, không dựa riêng vào tốc độ hoặc log.
5. Chẩn đoán các tình huống khiến kết quả đếm khác kỳ vọng: thiếu `@EnableCaching`, self-invocation, key, provider, TTL, `condition`, `unless` và cạnh tranh đồng thời.

## 2. Chính xác thì ta đếm cái gì?

Giả sử có phương thức nghiệp vụ:

```java
@Cacheable(cacheNames = "catalog", key = "#p0")
public String find(String code) {
    // Thân phương thức: giả lập truy vấn hoặc tính toán
    return "item:" + code;
}
```

Đây là **mã minh họa**, chưa phải chương trình độc lập. Trong ứng dụng cấu hình caching đúng, khi một bean khác gọi `find("A")` **thông qua Spring proxy**:

1. Interceptor của Spring dùng tên cache `catalog` và key `"A"` để tra cache.
2. Nếu **miss**, Spring thực thi thân `find` rồi lưu kết quả (nếu chính sách cho phép).
3. Nếu **hit**, interceptor trả kết quả có sẵn; thân `find` **không được gọi**.

Vì vậy cần tách hai chỉ số:

| Chỉ số | Ý nghĩa | Có tăng khi cache hit không? |
| --- | --- | --- |
| **Client calls** | Số lần bên ngoài gọi API của bean Spring | Có, mỗi lời gọi tăng một |
| **Body executions** | Số lần mã bên trong phương thức `@Cacheable` thực sự chạy | Không, đối với hit thành công |
| **Cache lookups** | Số lần framework/provider thực hiện thao tác tra cứu | Tùy chính sách và đường gọi; không đồng nghĩa số lần chạy thân phương thức |
| **Nguồn dữ liệu được truy vấn** | Số lần nghiệp vụ thực sự truy cập database hoặc API gốc | Phụ thuộc việc truy vấn nằm trong thân phương thức, các nhánh logic và lớp cache khác |

**Đặt bộ đếm ngay bên trong thân phương thức**. Nếu tăng bộ đếm ở controller hoặc ngay trước khi gọi `service.find(...)`, bạn sẽ đo số lời gọi của client; chỉ số đó vẫn tăng trong trường hợp hit và không chứng minh Spring đã bỏ qua phần xử lý tốn kém.

## 3. Kịch bản thí nghiệm: cùng key, khác key, rồi vô hiệu hóa

Ta thiết kế kịch bản tuần tự, không có lời gọi đồng thời, với cache ban đầu trống, không có TTL và không có cơ chế tự xóa:

| Bước | Hành động | Hit/Miss dự kiến | Số lần chạy thân phương thức tích lũy |
| --- | --- | --- | --- |
| 0 | Tạo cache mới, bộ đếm bằng 0 | Chưa đọc | 0 |
| 1 | `find("A")` | Miss: chưa có key A | 1 |
| 2 | `find("A")` | Hit: đã có A | 1 |
| 3 | `find("B")` | Miss: key B khác A | 2 |
| 4 | `find("A")` | Hit: A vẫn còn | 2 |
| 5 | `evict("A")`, sau đó `find("A")` | Miss do đã xóa A | 3 |
| 6 | `find("B")` | Hit nếu B vẫn tồn tại | 3 |

Tại bước 4: **4 lời gọi từ client nhưng thân phương thức chỉ chạy 2 lần**. Tại bước 5: thao tác `evict` chính nó không chạy `find`; lần đọc A tiếp theo mới làm bộ đếm tăng.

Đây là giả thuyết có thể kiểm chứng. Nếu thí nghiệm thực tế cho kết quả khác, chưa thể khẳng định ngay `@Cacheable` bị lỗi: phải kiểm tra cache key, đường gọi qua proxy, điều kiện annotation, số instance, provider và state của cache.

## 4. Ví dụ chạy được: Java 17 + Spring Boot + Simple Cache

Ví dụ này sử dụng Spring Boot **3.5.9**, JDK 17+, Maven và cache Simple (`ConcurrentMapCacheManager`) để không cần Redis hay database. Phiên bản 3.5.9 được dùng như một bản có thể tái tạo ví dụ; khi áp dụng cho dự án thật, nên sử dụng phiên bản bản vá đang được hỗ trợ trong dòng Boot của dự án.

### 4.1. Cấu trúc tệp

```text
cache-execution-proof/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/cache/
    │   │   ├── CacheProofApplication.java
    │   │   ├── CacheConfiguration.java
    │   │   └── CatalogService.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/example/cache/
            └── CacheProofTest.java
```

### 4.2. Maven — `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.9</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>cache-execution-proof</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

`spring-boot-starter-cache` cung cấp tích hợp Spring Cache; `spring-boot-starter-test` cung cấp hạ tầng Spring Test và JUnit Jupiter để viết kiểm thử. Parent của Boot quản lý phiên bản các dependency. Chưa cần Caffeine hay Redis vì ta chọn Simple cache chỉ để kiểm chứng hiện tượng.

### 4.3. Cấu hình cache — `CacheConfiguration.java`

```java
package example.cache;

import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {
}
```

`@EnableCaching` kích hoạt cơ chế xử lý `@Cacheable`. Việc đặt trong class cấu hình riêng giúp mục đích rõ ràng và cho phép các bộ kiểm thử khác lựa chọn có import caching hay không.

### 4.4. Dịch vụ có bộ đếm — `CatalogService.java`

```java
package example.cache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final AtomicInteger bodyExecutions = new AtomicInteger();

    @Cacheable(cacheNames = "catalog", key = "#p0")
    public String find(String sku) {
        int number = bodyExecutions.incrementAndGet();
        System.out.println("BODY " + sku + " -> " + number);
        return "item:" + sku;
    }

    public int executionCount() {
        return bodyExecutions.get();
    }
}
```

Giải thích từng lựa chọn:

- `bodyExecutions.incrementAndGet()` nằm **bên trong `find`**, vì vậy tăng khi thân phương thức thực sự chạy; `AtomicInteger` an toàn hơn `int++` khi nhiều thread dùng chung bean.
- `@Cacheable(cacheNames = "catalog", key = "#p0")` dùng đối số thứ nhất làm key. `#p0` không lệ thuộc vào việc giữ tên tham số `sku` trong bytecode.
- `find` là public method của một `@Service` do Spring quản lý; client sẽ lấy bean từ context để lời gọi đi qua proxy.
- `executionCount` là một phương thức đọc bộ đếm **không được cache**. Đọc nó không làm tăng số lần thực thi của `find`.
- `"item:" + sku` mô phỏng kết quả ổn định của nguồn dữ liệu. Ứng dụng thật có thể thay bằng truy vấn database hoặc gọi API trong thân `find`.

### 4.5. Ứng dụng chính — `CacheProofApplication.java`

```java
package example.cache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class CacheProofApplication {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(CacheProofApplication.class, args)) {
            CatalogService service = context.getBean(CatalogService.class);

            System.out.println("A1=" + service.find("A"));
            System.out.println("A2=" + service.find("A"));
            System.out.println("B1=" + service.find("B"));
            System.out.println("A3=" + service.find("A"));
            System.out.println("count=" + service.executionCount());

            CacheManager manager = context.getBean(CacheManager.class);
            System.out.println(
                    "cacheManager=" + manager.getClass().getSimpleName()
            );
        }
    }
}
```

Điểm quan trọng nhất là `context.getBean(CatalogService.class)`. Dịch vụ được gọi từ bên ngoài bean qua đối tượng Spring quản lý; nếu bạn dùng `new CatalogService()`, các annotation cache sẽ không được áp dụng cho object đó.

### 4.6. Provider và log — `application.properties`

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=OFF
spring.cache.type=simple
spring.cache.cache-names=catalog
```

`spring.cache.type=simple` cố định Simple provider cho thí nghiệm. Cache tên `catalog` được xác định rõ; Simple provider lưu trong bộ nhớ JVM, không có TTL hoặc chính sách eviction tự động trong cấu hình ví dụ này. `logging.level.root=OFF` nhằm giúp quan sát các dòng `System.out.println` của chính chương trình; không tác động tới cơ chế cache.

### 4.7. Chạy và đối chiếu kết quả

Ở thư mục `cache-execution-proof` (cần JDK 17+, Maven và kết nối Maven Central lần đầu):

```bash
java -version
mvn -q spring-boot:run
```

Các dòng **do mã của ứng dụng in ra** theo đúng thứ tự, không tính thông báo của công cụ build:

```text
BODY A -> 1
A1=item:A
A2=item:A
BODY B -> 2
B1=item:B
A3=item:A
count=2
cacheManager=ConcurrentMapCacheManager
```

Diễn giải:

- `A1`: cache miss, chạy thân phương thức, in `BODY A -> 1`.
- `A2`: hit cùng key A, không có dòng `BODY` mới.
- `B1`: miss với B, bộ đếm tăng lên 2.
- `A3`: vẫn hit với A, không có dòng `BODY` mới.
- `count=2`: bằng số key khác nhau đã cần tính trong thí nghiệm tuần tự này, **không phải quy luật bất biến** cho mọi workload.
- `ConcurrentMapCacheManager`: chứng minh provider Simple đã được chọn, thay vì giả định chỉ vì đã thêm annotation.

Để quan sát cả lời gọi **sau khi xóa key**, dùng kiểm thử tự động ở phần kế tiếp. Một lần thực thi chương trình mới có bộ đếm 0 và Simple cache mới; việc chạy lại ứng dụng **không giữ nguyên cache trong tiến trình cũ**.

## 5. Kiểm chứng bằng JUnit: assert số lần chạy thân phương thức

Dùng log để học dễ hiểu nhưng có thể bị nhiễu, bị lọc hoặc khó kiểm chứng trong CI. Kiểm thử nên so sánh giá trị bộ đếm trước/sau từng lời gọi.

Tạo `src/test/java/example/cache/CacheProofTest.java`:

```java
package example.cache;

import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class CacheProofTest {
    @Autowired
    private CatalogService service;

    @Autowired
    private CacheManager cacheManager;

    @Test
    void provesHitMissAndEvictionByExecutionCount() {
        Cache cache = Objects.requireNonNull(
                cacheManager.getCache("catalog"),
                "Missing catalog cache"
        );
        cache.clear();

        int baseline = service.executionCount();

        assertEquals("item:A", service.find("A"));
        assertEquals(baseline + 1, service.executionCount());

        assertEquals("item:A", service.find("A"));
        assertEquals(baseline + 1, service.executionCount());

        assertEquals("item:B", service.find("B"));
        assertEquals(baseline + 2, service.executionCount());

        assertEquals("item:A", service.find("A"));
        assertEquals(baseline + 2, service.executionCount());

        cache.evict("A");

        assertEquals("item:A", service.find("A"));
        assertEquals(baseline + 3, service.executionCount());

        assertEquals("item:B", service.find("B"));
        assertEquals(baseline + 3, service.executionCount());
    }
}
```

Chạy:

```bash
mvn -q test
```

Kết quả mong đợi: tiến trình Maven trả **exit code 0** và JUnit test thành công. Với `-q`, Maven có thể không in một dòng “BUILD SUCCESS”; các dòng `BODY` chỉ xuất hiện khi phương thức thực sự chạy. Chúng ta không dùng số dòng log làm nguồn chứng minh chính: chính các assertion `baseline + 1`, `baseline + 2`, `baseline + 3` là bằng chứng.

**Vì sao dùng `baseline` thay vì bắt buộc bằng 0?** Một Spring Test ApplicationContext có thể được dùng lại trong môi trường nhiều test; trạng thái của bean đôi khi đã thay đổi. `cache.clear()` làm sạch các mục cache, nhưng không tự đặt lại `AtomicInteger`. So sánh với `baseline` giúp bài kiểm thử tập trung đúng mức tăng do từng lời gọi, không phụ thuộc trạng thái trước đó. Trong dự án lớn, còn cần kiểm soát test chạy song song và các bean chia sẻ cache.

**Vì sao lấy service bằng `@Autowired`?** Spring tạo và có thể proxy bean. Tự viết `new CatalogService()` trong một unit test thuần sẽ chạy code Java thông thường, bỏ qua Spring Cache interceptor. Một bài test cache đúng phải sử dụng Spring context hoặc thiết lập proxy tương đương.

**Vì sao gọi `cache.evict("A")` trực tiếp?** Ta chủ động loại key A khỏi cache để kiểm tra việc quay lại trạng thái miss, không phải phụ thuộc vào TTL hay thời điểm scheduler. Phép kiểm tra này tập trung vào `@Cacheable`. Trong ứng dụng thật, `@CacheEvict` có thể được dùng tại phương thức cập nhật dữ liệu.

## 6. Một cách đo sai: đếm ở phía caller

Mã sau (minh họa, chưa có `main`) chỉ đo số lời gọi của client:

```java
int requests = 0;
requests++;
service.find("A");
requests++;
service.find("A");

System.out.println("requests=" + requests); // requests=2
```

Giả sử call đầu là miss, call sau là hit, `requests` vẫn bằng 2. Bạn **không thể suy ra** thân `find` đã thực thi hai lần. Muốn đo số lần xử lý gốc, đặt bộ đếm bên trong `find` như ví dụ hoàn chỉnh. Khi có layer cache thứ hai ở repository/HTTP client, cũng nên định nghĩa rõ đang đo lượt thực thi của **phương thức nào** và truy cập tới nguồn dữ liệu nào.

## 7. Những trường hợp khiến bộ đếm không đúng dự đoán

### 7.1. Thiếu @EnableCaching hoặc thiếu CacheManager phù hợp

Thêm `spring-boot-starter-cache` không tự chứng minh `@Cacheable` đã kích hoạt. Cần bật caching bằng `@EnableCaching`; cache name phải được provider/manager chấp nhận; lời gọi phải qua Spring bean. Hãy kiểm tra type `CacheManager`, log và hai lời gọi cùng key.

### 7.2. Gọi nội bộ trong chính bean (self-invocation)

Trong chế độ proxy mặc định, lời gọi bằng `this` từ cùng object thường bỏ qua interceptor:

```java
@Service
public class CatalogService {
    @Cacheable(cacheNames = "catalog")
    public String find(String sku) {
        // phần xử lý gốc
        return "item:" + sku;
    }

    public String internalCall(String sku) {
        return this.find(sku);
    }
}
```

Đây là **đoạn minh họa độc lập với project mẫu ở trên**, không phải tệp thay thế để copy đè. Gọi `internalCall("A")` hai lần qua Spring bean có thể làm thân `find` chạy cả hai lần, vì mỗi lần `this.find` không đi qua proxy. Để kiểm chứng đúng đường caching, hãy dùng lời gọi từ **một bean khác** hoặc từ test đã inject service.

### 7.3. Khác key dù nhìn giống tác vụ

`find("A")` và `find("B")` là hai key khác nhau. Nếu key sinh ra chứa timestamp, đối tượng không có `equals/hashCode` phù hợp, tenant hoặc locale, hit rate và số lần chạy có thể khác. Khi dùng SpEL key, kiểm tra biểu thức `#p0`, `#p1`… và đối số cụ thể của từng lần gọi.

Đừng sửa key để ép mọi lời gọi cùng hit nếu kết quả nghiệp vụ thực sự phụ thuộc nhiều tham số; key thiếu ngữ cảnh có thể trả **sai dữ liệu hoặc rò rỉ giữa người dùng**.

### 7.4. Điều kiện cache và chính sách không lưu kết quả

Ví dụ minh họa annotation:

```java
@Cacheable(
    cacheNames = "catalog",
    key = "#p0",
    condition = "#p0.length() > 1",
    unless = "#result == null"
)
public String find(String code) {
    return repository.lookup(code);
}
```

Đoạn trên cần có bean `repository` thực tế; nó chỉ dùng để giải thích. `condition` được xét trước khi gọi phương thức: với mã quá ngắn, caching không được áp dụng và mỗi lần gọi đều có thể chạy thân phương thức. `unless` được xét sau khi có kết quả: nếu kết quả là `null`, Spring bỏ qua bước lưu cache cho lần đó; các lần gọi sau có thể tiếp tục chạy lại. Kết quả thực tế còn phụ thuộc các annotation và chính sách provider khác.

### 7.5. TTL, eviction, restart hoặc cache khác instance

Một key đã hit không có nghĩa sẽ mãi hit. Mục cache có thể hết hạn, bị `@CacheEvict` hoặc thao tác `clear` loại bỏ, hoặc bị eviction do đầy bộ nhớ. Local cache của hai instance khác nhau có hai trạng thái riêng. Bộ đếm trong JVM cũng khởi đầu lại khi ứng dụng restart.

Trước khi assert, phải xác định **trạng thái ban đầu của cache**, thời điểm cache còn hiệu lực và bạn đang quan sát **instance nào**.

### 7.6. Có nhiều yêu cầu cùng miss một key

Nếu nhiều thread đồng thời gọi key A khi cache trống, `@Cacheable` thông thường **không cam kết thân phương thức chỉ chạy một lần**. Nhiều yêu cầu có thể cùng thấy miss rồi tính lại. Vì vậy bảng kịch bản ở phần 3 giả định lời gọi tuần tự.

`@Cacheable(sync = true)` yêu cầu cache provider phối hợp để chỉ tính một giá trị cho cùng key khi cạnh tranh; khả năng này tùy provider. Cơ chế `sync` có những ràng buộc như chỉ một cache và không sử dụng `unless`. Ngay cả với `sync = true`, vẫn cần hiểu tính chất của provider thực tế, đặc biệt trong môi trường phân tán.

Để bài test **ổn định**, hãy kiểm chứng cơ bản bằng lời gọi tuần tự trước. Nếu cần kiểm chứng chống cache stampede, viết bài test đồng thời riêng, kiểm soát số thread, thời điểm bắt đầu và provider; đừng đưa lịch chạy thread ngẫu nhiên vào bài test hit/miss cơ bản.

## 8. Kiểm tra thêm: tác động của @CacheEvict và @CachePut đến phép đếm

Nên phân biệt rõ các annotation:

- `@Cacheable`: có thể **không thực thi** thân phương thức nếu hit.
- `@CachePut`: thường **thực thi phương thức** rồi dùng kết quả để cập nhật cache; không dùng để chứng minh bỏ qua công việc lặp.
- `@CacheEvict`: áp dụng thao tác xóa cache liên quan đến phương thức được đánh dấu. Khi xóa thành công, một lần gọi `@Cacheable` tiếp theo có thể miss và thực thi lại thân phương thức.

Ví dụ ứng dụng sau khi cập nhật sản phẩm thành công nên xóa giá trị cache theo key tương ứng. Nếu xóa trước khi dữ liệu nguồn được commit, một request khác có thể nạp lại bản cũ; bài kiểm thử cache cần chú ý ranh giới giao dịch và thời điểm invalidation nếu có update.

## 9. Tăng độ tin cậy của bài kiểm chứng

Một bài test có sức thuyết phục nên bảo đảm:

1. **Đúng đối tượng đo:** bộ đếm nằm bên trong phương thức gốc hoặc dùng spy/metric ghi nhận hoạt động thực tế của nguồn.
2. **Đúng đường gọi:** lấy bean từ `ApplicationContext`, không tạo object bằng `new` khi kiểm thử annotation.
3. **Đúng cache:** xác nhận `CacheManager` thực tế và tên cache trước khi kết luận.
4. **Đúng điều kiện ban đầu:** xóa cache có chủ đích, lấy baseline, tránh test phụ thuộc thứ tự.
5. **Đúng đối số:** cùng key cho hit, khác key cho miss.
6. **Đúng phạm vi:** test đơn luồng cho cơ chế cơ bản; test song song và đa instance riêng.
7. **Đúng kết quả:** assert cả giá trị trả về lẫn số lần chạy thân phương thức, tránh chỉ đo thời gian.
8. **Đúng mức kỳ vọng:** một cache hit chỉ cho biết interceptor đã phục vụ từ cache; điều đó chưa nói cache luôn mới, có ích về hiệu năng hay bảo đảm đúng nghiệp vụ.

### Vì sao chỉ đo thời gian không đủ?

Một phương thức có thể nhanh hơn lần hai vì JIT compiler, kết nối DB được tái sử dụng, buffer cache hoặc dữ liệu đã nạp trong tầng khác, dù Spring Cache không hề hit. Ngược lại, một hit cũng có thể biến động thời gian vì GC hoặc tranh chấp CPU. Bộ đếm bên trong phần xử lý gốc và assertion cho phép chứng minh hành vi được cache trực tiếp hơn.

Trong production, hãy dùng thêm metric của provider/cache manager (hit, miss, eviction), truy vấn nguồn và độ trễ p95/p99. Bộ đếm thủ công rất hữu ích để học và debug nhưng không thay thế giám sát lâu dài.

## 10. Bài tập tự luyện

**Bài tập 1 — Dự đoán bộ đếm.** Cache trống, bộ đếm 0, không TTL. Gọi tuần tự `A, A, B, A, B, C`. Hỏi thân phương thức chạy mấy lần? Trả lời: **3** nếu key đúng theo mã, các giá trị được lưu và không có invalidation — mỗi key A, B, C lần đầu cần tính.

**Bài tập 2 — Thêm invalidation.** Sau chuỗi trên, xóa key B rồi gọi `A, B, B`. Hỏi bộ đếm tăng thêm bao nhiêu? Trả lời: **1** — A vẫn hit, B đầu là miss, B sau hit.

**Bài tập 3 — Chẩn đoán.** Trong test, hai lần `service.find("A")` đều làm bộ đếm tăng. Hãy kiểm tra theo thứ tự: bean có được Spring tạo không, `@EnableCaching` đã bật chưa, lời gọi đi qua proxy không, key có thật sự như nhau không, có cache manager và tên cache đúng không, kết quả có bị `condition`/`unless` chặn lưu hay không, cache có bị xóa giữa hai lần không.

**Bài tập 4 — Thảo luận.** Cùng một key bị 20 yêu cầu đồng thời gọi khi cache trống. Có nên mặc định mong đợi bộ đếm chỉ tăng 1? Trả lời: **Không**, vì default caching không bảo đảm khóa đồng bộ các miss; cần xét `sync = true`, provider và cách thiết kế test đồng thời.

## Tài liệu chính thức

- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Understanding the Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache/strategies.html)
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
- [Spring Boot 3.5.9 release](https://spring.io/blog/2025/12/18/spring-boot-3-5-9-available-now/)

**Ghi nhớ:** Số lần client gọi không phải số lần thân `@Cacheable` thực thi. Một phép kiểm chứng đúng dùng Spring bean đã được proxy, cache có trạng thái được kiểm soát, bộ đếm bên trong thân phương thức và assertion cho các trường hợp hit, miss và eviction. Từ đó mới đánh giá được cache có thực sự loại bỏ xử lý lặp hay không.