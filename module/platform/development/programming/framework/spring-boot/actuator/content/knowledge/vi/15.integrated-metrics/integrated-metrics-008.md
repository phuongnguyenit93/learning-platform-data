# Theo dõi cache hit, miss, kích thước và điều kiện hỗ trợ của cache provider

## 1. Ta đang đo điều gì trong một hệ thống có cache?

Bộ nhớ đệm (cache) giữ lại kết quả để những lần đọc sau có thể dùng lại. Ví dụ, cùng truy vấn sản phẩm `A`, lần đầu ứng dụng phải tính toán hoặc đọc cơ sở dữ liệu; lần sau có thể trả kết quả đã lưu. Tuy nhiên, có cache trong cấu hình chưa chứng minh cache đang giúp ứng dụng. Ta cần quan sát cả việc tra cứu lẫn dữ liệu đang giữ:

- **Hit:** thao tác tra cứu tìm được giá trị đã lưu cho khóa cần đọc.
- **Miss:** thao tác tra cứu không tìm được giá trị có thể dùng; ứng dụng có thể phải nạp dữ liệu hoặc trả về kết quả rỗng.
- **Kích thước:** số phần tử đang được nhà cung cấp cache báo cáo tại thời điểm đo.

Từ đó có ba câu hỏi khác nhau: dữ liệu có được dùng lại không, nguồn dữ liệu phía sau có đang bị gọi nhiều không, và cache đang giữ bao nhiêu phần tử? Không thể dùng một con số để trả lời cả ba.

Trong Spring Boot Actuator, luồng đo thường là:

```text
Thao tác đọc/ghi cache
        ↓
Thống kê của nhà cung cấp cache
        ↓
Bộ kết nối số đo (meter binder)
        ↓
Micrometer MeterRegistry
        ↓
/actuator/metrics hoặc hệ thống giám sát như Prometheus
```

`CacheManager` quản lý các cache; thư viện như Caffeine hoặc Redis thực hiện lưu trữ và cung cấp thống kê. Micrometer đưa thống kê vào các số đo thống nhất. Actuator giúp đăng ký, truy vấn và xuất chúng. Mở endpoint không tự tạo ra dữ liệu mà nhà cung cấp chưa thu thập.

Bài này dùng Spring Boot **3.3.x**, Java **17 trở lên**; dự án dùng Java 21 có thể chạy nguyên ví dụ. Các chi tiết riêng của thư viện được nêu rõ để tránh xem mọi cache như có cùng khả năng đo.

## 2. Tên số đo, loại số đo và giới hạn diễn giải

Bộ kết nối cache của Micrometer dùng các tên cơ bản dưới đây, nhưng chỉ đăng ký những khả năng mà bộ kết nối tương ứng cung cấp. Đặc biệt, không được suy từ việc có `cache.gets` rằng chắc chắn cũng có `cache.size`. [Đối chiếu CacheMeterBinder của Micrometer 1.13](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/binder/cache/CacheMeterBinder.java).

| Tên Micrometer | Loại | Cách đọc |
| --- | --- | --- |
| `cache.gets` với `result=hit` | FunctionCounter | Số lần tra cứu tìm thấy dữ liệu theo thống kê của cache |
| `cache.gets` với `result=miss` | FunctionCounter, nếu hỗ trợ | Số lần tra cứu không tìm thấy dữ liệu |
| `cache.size` | Gauge, nếu hỗ trợ | Số phần tử được báo cáo ở thời điểm lấy mẫu |
| `cache.puts` | FunctionCounter | Đại lượng thêm/nạp dữ liệu mà bộ kết nối ánh xạ từ thư viện; phải kiểm tra ý nghĩa cụ thể |
| `cache.evictions` | FunctionCounter, nếu hỗ trợ | Số lần loại bỏ theo thống kê eviction của thư viện |

**FunctionCounter** đọc một bộ đếm tích lũy của đối tượng được theo dõi. **Gauge** lấy giá trị hiện tại, có thể tăng hoặc giảm. Vì vậy, lấy tốc độ tăng của hit/miss là hợp lý; lấy `rate(cache_size[5m])` để gọi là “kích thước cache” là sai loại câu hỏi.

Các nhãn (tag) giúp phân biệt cache cùng tên ở các bộ quản lý khác nhau. Với cấu hình tự động của Boot 3.3, chú ý `cache`, `name`, `cache.manager`, và riêng `cache.gets` có `result`. Giá trị `cache.manager` được suy từ tên bean và có quy tắc bỏ hậu tố `cacheManager` trong một số tên; đừng tự đoán giá trị trên hệ thống thực tế. [Mã đăng ký và gắn nhãn của Spring Boot](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/cache/CacheMetricsRegistrarConfiguration.java).

Một hit không nhất thiết là một HTTP request thành công. Một request có thể không truy cập cache, truy cập nhiều khóa hoặc dùng nhiều tầng cache. Một miss cũng không phải mặc nhiên là lỗi: khóa mới, dữ liệu hết hạn hoặc dữ liệu chủ động bị xóa đều có thể dẫn tới miss bình thường.

### Kích thước không phải dung lượng bộ nhớ

`cache.size = 1.000` nghĩa là khoảng một nghìn phần tử theo cách thư viện báo cáo, **không phải 1.000 byte**. Hai cache có cùng số phần tử vẫn có thể dùng bộ nhớ khác nhau rất nhiều vì kích thước khóa, giá trị và cấu trúc quản lý khác nhau.

Với Caffeine, số đo này dựa trên `estimatedSize()`. Việc dọn phần tử hết hạn hoặc thực hiện bảo trì có thể khiến số lượng báo cáo chưa phản ánh ngay mọi thay đổi. Khi điều tra hết hạn, phân biệt “không còn trả về khi đọc” và “đã được loại khỏi mọi cấu trúc nội bộ”. Không dùng một lần đọc gauge làm bằng chứng tuyệt đối về số đối tượng còn trong heap.

### `cache.puts` và eviction phụ thuộc thư viện

Trong bộ kết nối Caffeine của Micrometer 1.13, `cache.puts` đọc `CacheStats.loadCount()`. Lệnh `put` thủ công không được bộ thống kê đó tính như một lần nạp qua hàm nạp. Điều này giải thích vì sao cache đã có dữ liệu nhưng số đo `cache.puts` vẫn bằng 0. `cache.size` cũng dùng số lượng ước tính của Caffeine. [Đối chiếu CaffeineCacheMetrics](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/binder/cache/CaffeineCacheMetrics.java).

Tương tự, thao tác xóa chủ động không nhất thiết làm tăng `cache.evictions`. Cần phân biệt xóa do ứng dụng yêu cầu, hết hạn và loại bỏ theo chính sách dung lượng. Không đặt quy tắc “cứ giảm size thì eviction phải tăng” cho mọi nhà cung cấp.

## 3. Điều kiện để Spring Boot tự ghi nhận cache metrics

Trước khi nhìn vào biểu đồ, kiểm tra đủ các mắt xích:

1. Có Actuator và một `MeterRegistry` hoạt động.
2. Có `CacheManager` cùng cache thực tế mà ứng dụng đang sử dụng.
3. Có bộ kết nối tương thích với loại cache đó.
4. Đã bật thống kê của nhà cung cấp nếu thư viện yêu cầu.
5. Cache tồn tại khi Boot đăng ký số đo, hoặc đã được đăng ký rõ ràng nếu tạo muộn.
6. Có thao tác thực sự đi qua cache đang theo dõi.

Trong Boot 3.3, danh sách hỗ trợ đo tự động gồm **Cache2k, Caffeine, Hazelcast, JCache tương thích JSR-107 và Redis**. Cache được biết tại lúc khởi động được tự đăng ký; cache tạo sau giai đoạn này cần đăng ký thêm. [Tài liệu cache metrics của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.cache).

| Loại cache | Điều kiện hoặc giới hạn cần kiểm tra |
| --- | --- |
| Caffeine | Bật `recordStats` trước khi tạo cache; số phần tử là ước tính |
| Redis qua Spring Data Redis | Bật thống kê phía ứng dụng; không coi các số đếm này là toàn bộ hoạt động trên Redis server |
| JCache, ví dụ Ehcache 3 qua JCache | Kiểm tra cấu hình thống kê của nhà cung cấp và đường tích hợp JCache đang dùng |
| Hazelcast, Cache2k | Kiểm tra loại tích hợp và khả năng thống kê của phiên bản thư viện thực tế |
| `ConcurrentMapCacheManager` đơn giản | Không có trong danh sách bộ kết nối tự động nói trên; có cache hoạt động không bảo đảm xuất hiện bộ số đo hit/miss chuẩn |
| Cache tự viết hoặc một lớp bọc tùy biến | Có thể cần bộ kết nối riêng; phải hiểu được thống kê và cách lấy cache gốc |

Danh sách nhà cung cấp mà Spring Boot có thể **cấu hình để lưu cache** rộng hơn danh sách được **tự đo cache metrics**. Hai khả năng này không đồng nghĩa. Nếu có nhiều thư viện trên classpath, hãy xác minh loại `CacheManager` thực tế; `spring.cache.type` hữu ích khi Boot đang tự cấu hình bộ quản lý. [Tài liệu cấu hình cache của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/io/caching.html).

Với Caffeine, `recordStats()` là công tắc thu thập thống kê. Nếu quên bật, số đo có thể vẫn được đăng ký nhưng hit/miss không phản ánh lưu lượng như mong đợi; nhìn thấy tên meter chưa đủ để xác nhận đường đo hoạt động. [Hướng dẫn thống kê của Caffeine](https://github.com/ben-manes/caffeine/wiki/Statistics).

## 4. Thí nghiệm hoàn chỉnh với Caffeine và Actuator

Thí nghiệm dưới đây gọi dịch vụ bốn lần, qua Spring proxy, để tạo một chuỗi tra cứu có thể dự đoán. Không cần cơ sở dữ liệu, Redis server hay API nghiệp vụ để tạo lưu lượng.

### 4.1. Tạo dự án riêng

Đây là dự án minh họa độc lập, không phải yêu cầu sửa cấu hình Gradle của repository đang học. Dùng Gradle hỗ trợ Java 21, chẳng hạn Gradle 8.5, với cấu trúc:

```text
cache-metrics-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/cachemetrics/CacheMetricsDemoApplication.java
    └── resources/application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'cache-metrics-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'com.github.ben-manes.caffeine:caffeine'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Để BOM của Boot quản lý phiên bản Micrometer và Caffeine, tránh phối các phiên bản tùy ý. `spring-boot-starter-cache` đưa vào phần hỗ trợ cache của Spring; Caffeine vẫn là thư viện triển khai cần khai báo. Prometheus registry chỉ cần khi muốn dùng định dạng Prometheus.

`src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health,metrics,prometheus
```

Cấu hình này dành cho thí nghiệm tại máy cá nhân. Trong hệ thống có bảo mật, quyền truy cập endpoint vẫn tuân theo cấu hình bảo mật của ứng dụng.

### 4.2. Chương trình Java

Lưu nguyên nội dung dưới đây vào `CacheMetricsDemoApplication.java` đúng thư mục đã nêu:

```java
package example.cachemetrics;

import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import com.github.benmanes.caffeine.cache.Caffeine;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class CacheMetricsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheMetricsDemoApplication.class, args);
    }

    @Bean
    CaffeineCacheManager cacheManager() {
        CaffeineCacheManager manager = new CaffeineCacheManager("products");
        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(100)
                .recordStats());
        return manager;
    }

    @Bean
    ProductService productService() {
        return new ProductService();
    }

    @Bean
    ApplicationRunner sample(ProductService service, CacheManager cacheManager,
            MeterRegistry registry) {
        return args -> {
            System.out.println("DEMO value=" + service.find("A"));
            System.out.println("DEMO value=" + service.find("A"));
            System.out.println("DEMO value=" + service.find("B"));
            System.out.println("DEMO value=" + service.find("B"));

            double hits = registry.get("cache.gets")
                    .tags("cache", "products", "result", "hit")
                    .functionCounter().count();
            double misses = registry.get("cache.gets")
                    .tags("cache", "products", "result", "miss")
                    .functionCounter().count();
            double size = registry.get("cache.size")
                    .tag("cache", "products").gauge().value();
            double puts = registry.get("cache.puts")
                    .tag("cache", "products").functionCounter().count();

            System.out.printf(Locale.ROOT,
                    "DEMO loads=%d hits=%.0f misses=%.0f size=%.0f puts=%.0f%n",
                    service.loads(), hits, misses, size, puts);

            var cache = Objects.requireNonNull(cacheManager.getCache("products"));
            cache.evict("A");
            double afterEvict = registry.get("cache.size")
                    .tag("cache", "products").gauge().value();
            double evictions = registry.get("cache.evictions")
                    .tag("cache", "products").functionCounter().count();
            System.out.printf(Locale.ROOT,
                    "DEMO after-explicit-evict size=%.0f evictions=%.0f%n",
                    afterEvict, evictions);
        };
    }

    public static class ProductService {
        private final AtomicInteger calls = new AtomicInteger();

        @Cacheable(cacheNames = "products", key = "#p0")
        public String find(String id) {
            calls.incrementAndGet();
            return "product-" + id;
        }

        public int loads() {
            return calls.get();
        }
    }
}
```

Bộ quản lý được đặt tên bean là `cacheManager` và khai báo trước cache `products`. `recordStats()` được thiết lập trong quá trình cấu hình trước khi bean bộ quản lý được đưa vào sử dụng. Không có bộ đếm tự viết giả lập hit/miss; các giá trị được đọc từ những meter mà Boot đăng ký.

`ProductService` là một bean riêng. Runner nhận bean qua Spring rồi gọi `find`, nên lời gọi đi qua cơ chế cache. Không tạo dịch vụ bằng `new ProductService()` trong runner và không thay bằng lời gọi `this.find()` bên trong chính dịch vụ. Thuộc tính `key = "#p0"` chọn tham số thứ nhất, không phụ thuộc việc biên dịch có giữ tên tham số Java hay không. [Ngữ nghĩa của Cacheable và biểu thức khóa](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/annotation/Cacheable.html).

### 4.3. Chạy và đối chiếu stdout

Nếu đã có Gradle wrapper, chạy:

```powershell
.\gradlew.bat bootRun
```

Hoặc khi đã cài Gradle phù hợp:

```powershell
gradle bootRun
```

Lần chạy đầu cần truy cập kho phụ thuộc để tải plugin và thư viện. Các dòng có tiền tố `DEMO` phải là:

```text
DEMO value=product-A
DEMO value=product-A
DEMO value=product-B
DEMO value=product-B
DEMO loads=2 hits=2 misses=2 size=2 puts=0
DEMO after-explicit-evict size=1 evictions=0
```

Đây là phần stdout của thí nghiệm, không phải toàn bộ log khởi động Spring Boot. Kết quả giả định một lần khởi động mới, chạy tuần tự, không có tác vụ khác truy cập cache và không có tùy biến bộ kết nối.

| Thao tác | Kết quả tra cứu | Thân `find` có chạy? | Số phần tử sau thao tác |
| --- | --- | --- | --- |
| `find("A")` lần 1 | Miss | Có | 1 |
| `find("A")` lần 2 | Hit | Không | 1 |
| `find("B")` lần 1 | Miss | Có | 2 |
| `find("B")` lần 2 | Hit | Không | 2 |
| `cache.evict("A")` | Không phải tra cứu | Không | 1 |

Hai lần miss dẫn đến hai lần thực thi phương thức. Với `@Cacheable` mặc định trong ví dụ, Spring tra cứu cache rồi ghi kết quả trả về; đây không phải hai lần nạp được `CacheStats.loadCount()` của Caffeine ghi nhận. Vì vậy `puts=0` vẫn nhất quán với `size=2` ở dòng trước khi xóa.

`cache.evict("A")` là xóa chủ động nên thí nghiệm cho thấy size giảm xuống 1, còn `evictions` vẫn là 0. Không suy rộng kết quả này thành “Caffeine không có eviction”: khi loại bỏ do chính sách của thư viện, thống kê có thể khác.

Có thể chạy thí nghiệm không mở HTTP bằng lệnh sau; khi đó dùng stdout để kiểm tra, không dùng các lệnh `curl` ở phần tiếp theo:

```powershell
.\gradlew.bat bootRun --args="--spring.main.web-application-type=none"
```

## 5. Đọc từng chuỗi số đo qua Actuator

Khi ứng dụng chạy theo chế độ web mặc định, dùng `curl.exe` trong PowerShell để tránh nhầm với tên thay thế của một lệnh PowerShell:

```powershell
curl.exe "http://localhost:8080/actuator/metrics"
curl.exe "http://localhost:8080/actuator/metrics/cache.gets"
curl.exe "http://localhost:8080/actuator/metrics/cache.gets?tag=cache:products&tag=cache.manager:cacheManager&tag=result:hit"
curl.exe "http://localhost:8080/actuator/metrics/cache.gets?tag=cache:products&tag=cache.manager:cacheManager&tag=result:miss"
curl.exe "http://localhost:8080/actuator/metrics/cache.size?tag=cache:products&tag=cache.manager:cacheManager"
```

Hãy xem `availableTags` trước khi lọc, đặc biệt nếu ứng dụng có nhiều bộ quản lý. Trong ví dụ chỉ có một cache `products` và bean tên `cacheManager`, nên các bộ lọc trên xác định đúng chuỗi.

Sau khi runner hoàn tất:

- Chuỗi hit có `COUNT = 2.0`.
- Chuỗi miss có `COUNT = 2.0`.
- `cache.size` có `VALUE = 1.0`, vì cuối runner đã xóa `A`.

Nếu đọc `cache.gets` không lọc `result`, giá trị tổng hợp có thể cộng cả hit và miss. Không gọi tổng này là số lần hit. Trong ứng dụng nhiều cache, tiếp tục lọc theo cache và bộ quản lý; không dùng tổng của cả hệ thống để kết luận về một cache riêng.

Đọc endpoint metrics không tự gọi lại `find`, vì vậy việc làm mới endpoint không phải cách tạo thêm hit/miss. Muốn sinh lưu lượng mới, cần có thao tác mới đi qua cache đang quan sát.

## 6. Tính tỷ lệ hit/miss theo khoảng thời gian

Gọi `H` là số hit và `M` là số miss. Với một khoảng quan sát không có khởi động lại hoặc đặt lại bộ đếm:

```text
ΔH = H_cuối − H_đầu
ΔM = M_cuối − M_đầu
Số lượt tra cứu trong khoảng = ΔH + ΔM
Tỷ lệ hit = ΔH / (ΔH + ΔM)
Tỷ lệ miss = ΔM / (ΔH + ΔM)
```

Nếu tổng bằng 0, không có lượt tra cứu để tính tỷ lệ. Hãy hiển thị “không có lưu lượng” thay vì kết luận cache tốt 100% hoặc hỏng 100%. Trong thí nghiệm, trước lần xóa chủ động có 2 hit và 2 miss, nên tỷ lệ hit là 50%; thao tác xóa không làm thay đổi số lượt tra cứu.

Ví dụ số liệu giả định: đầu khoảng có 900 hit và 100 miss, cuối khoảng có 990 hit và 110 miss. Tỷ lệ hit trong khoảng là `90 / (90 + 10) = 90%`. Đây là phép tính trên phần tăng, không phải lấy hit hiện tại chia cho số phần tử cache.

### 6.1. Tên Prometheus và truy vấn mẫu

Với cách đặt tên thông thường của Prometheus registry, `cache.gets` được xuất thành `cache_gets_total`, `cache.size` thành `cache_size`, còn nhãn `cache.manager` thành `cache_manager`. Kiểm tra dữ liệu thực tế trước khi viết truy vấn:

```powershell
curl.exe "http://localhost:8080/actuator/prometheus" | Select-String "cache_gets_total|cache_size|cache_puts_total|cache_evictions_total"
```

Ví dụ tốc độ miss theo từng cache và bộ quản lý, cộng lưu lượng từ các instance trong cùng `job`:

```promql
sum by (job, cache, cache_manager) (
  rate(cache_gets_total{result="miss"}[5m])
)
```

Tỷ lệ hit theo cùng cách nhóm:

```promql
sum by (job, cache, cache_manager) (
  rate(cache_gets_total{result="hit"}[5m])
)
/
sum by (job, cache, cache_manager) (
  rate(cache_gets_total{result=~"hit|miss"}[5m])
)
```

Mẫu số chỉ chọn `hit|miss` có chủ đích: một nhà cung cấp có thể thêm giá trị `result` khác. Không mặc nhiên đưa mọi kết quả phụ vào số lượt tra cứu đã xác định hit hoặc miss.

Dùng `rate` trên từng chuỗi trước khi cộng giúp xử lý việc các tiến trình khởi động lại với bộ đếm mới. `increase` thích hợp khi cần phần tăng theo một khoảng; không dùng phép trừ hai snapshot tích lũy một cách mù quáng qua lần khởi động lại. [Ngữ nghĩa rate và increase trong Prometheus](https://prometheus.io/docs/prometheus/latest/querying/functions/).

Cần ít nhất các mẫu thu thập phù hợp để tính tốc độ. Thí nghiệm chỉ sinh bốn lượt rồi dừng truy cập cache, nên sau một thời gian cửa sổ quan sát sẽ không còn hoạt động mới; điều này không làm các bộ đếm tích lũy quay về 0. Khi mẫu số của tỷ lệ bằng 0, truy vấn có thể trả `NaN`; dashboard cần biểu diễn trạng thái không có lưu lượng rõ ràng.

### 6.2. Đừng lấy trung bình giản đơn các tỷ lệ

Giả sử instance thứ nhất có 90 hit trên 100 lượt; instance thứ hai có 1 hit trên 1 lượt. Tỷ lệ gộp là `91 / 101`, khoảng **90,10%**, không phải trung bình `(90% + 100%) / 2 = 95%`.

Tương tự, tổng size của hai cache Caffeine cục bộ là tổng số phần tử đang giữ trên hai tiến trình; đó không chắc là số khóa duy nhất vì cùng khóa có thể xuất hiện ở cả hai nơi. Với một bộ nhớ đệm phân tán, phép cộng các gauge còn phải xét chúng mô tả phần dữ liệu cục bộ hay cùng một tập dữ liệu toàn cụm.

Một tỷ lệ hit cao cũng chưa đủ kết luận hiệu năng tốt. Hãy đối chiếu thêm độ trễ, số lần thực sự gọi nguồn dữ liệu, chi phí tính toán và yêu cầu dữ liệu còn mới. Một cache trả dữ liệu cũ nhanh không tự nhiên trở thành thiết kế đúng.

## 7. Cache được tạo sau lúc khởi động

Khi danh sách tên cache cố định, nên khai báo trước. Ví dụ Java đã dùng `new CaffeineCacheManager("products")`; bộ quản lý này ở chế độ tên cố định và không tự tạo một cache tên bất kỳ.

Nếu Boot tự cấu hình Caffeine thay vì dùng bean Java riêng, có thể khai báo tương đương:

```properties
spring.cache.type=caffeine
spring.cache.cache-names=products
spring.cache.caffeine.spec=maximumSize=100,recordStats
```

Đây là **phương án thay thế** cho bean `cacheManager()` trong ví dụ. Không thêm các thuộc tính rồi mặc định chúng sẽ ghi đè cấu hình của một `CacheManager` do mình tự tạo.

Nếu ứng dụng thực sự cần cache tạo muộn, phải nối cache đó vào registry tại nơi kiểm soát vòng đời của nó. Đoạn dưới là phương thức cấu hình minh họa, không phải chương trình độc lập và không ghép vào ví dụ tên cố định ở trên:

```java
import java.util.Objects;

import io.micrometer.core.instrument.Tag;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.actuate.metrics.cache.CacheMetricsRegistrar;
import org.springframework.cache.Cache;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;

// Giả định bean cacheManager dùng new CaffeineCacheManager(),
// đã bật recordStats và cho phép tạo cache theo tên lúc chạy.
@Bean
ApplicationRunner registerLateCache(CaffeineCacheManager cacheManager,
        CacheMetricsRegistrar registrar) {
    return args -> {
        Cache lateCache = Objects.requireNonNull(cacheManager.getCache("prices"));
        boolean bound = registrar.bindCacheToRegistry(
                lateCache, Tag.of("cache.manager", "cacheManager"));
        if (!bound) {
            throw new IllegalStateException("No compatible cache metrics binder");
        }
    };
}
```

`bindCacheToRegistry` trả `false` nếu không tìm được bộ kết nối tương thích; việc gọi phương thức này không tự bổ sung thống kê còn thiếu cho mọi loại cache. [Hợp đồng CacheMetricsRegistrar](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/metrics/cache/CacheMetricsRegistrar.java).

Đăng ký một lần theo vòng đời cache, không đăng ký lại theo từng request. Giữ cùng cách đặt nhãn với các cache có sẵn. Nếu xóa rồi tạo một đối tượng cache mới cùng tên, cần xử lý việc thay thế số đo đang trỏ vào đối tượng cũ; đăng ký lặp cùng tên và cùng nhãn không bảo đảm tự chuyển nguồn đọc sang đối tượng mới.

Cũng tránh tạo tên cache từ từng người dùng hoặc từng request chỉ để tiện theo dõi. Số lượng tổ hợp nhãn tăng theo các tên đó có thể làm số chuỗi thời gian lớn ngoài dự kiến.

## 8. Redis: thống kê của ứng dụng và số liệu của server

Khi dùng Redis, phải xác định **đang đo ở đâu**. Thống kê của `RedisCache` trong ứng dụng không phải bộ đếm toàn cục của Redis server. Các ứng dụng khác, thao tác trực tiếp bằng Redis client, hoặc công cụ quản trị không nhất thiết đi qua đối tượng cache đang được Actuator theo dõi.

Spring Data Redis mặc định không bật thống kê `RedisCache`; `RedisCacheManagerBuilder.enableStatistics()` cho phép thu thập hit/miss cục bộ của phía ứng dụng. [Tài liệu Redis Cache về phạm vi thống kê](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html).

Nếu Boot đang tự cấu hình Redis cache manager, một tùy biến phù hợp trong lớp cấu hình là:

```java
import org.springframework.boot.autoconfigure.cache.RedisCacheManagerBuilderCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
RedisCacheManagerBuilderCustomizer enableRedisCacheStatistics() {
    return builder -> builder.enableStatistics();
}
```

Đây là lựa chọn cho dự án đã có cấu hình và thư viện Redis tương ứng, không phải đoạn cần thêm vào thí nghiệm Caffeine. Nếu tự tạo `RedisCacheManager`, bật thống kê trực tiếp trên builder của bộ quản lý đó và xác minh bean thực tế đang dùng.

Trong bộ kết nối Redis của Boot **3.3**, `size()` và `evictionCount()` không cung cấp giá trị, vì vậy các meter `cache.size` và `cache.evictions` không được đăng ký bởi bộ kết nối này. Có hit/miss Redis nhưng không có hai meter này có thể là đúng khả năng hỗ trợ, không phải lỗi endpoint. [Mã RedisCacheMetrics của Boot 3.3](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/metrics/cache/RedisCacheMetrics.java).

Do đó, không thay số liệu thiếu bằng 0 để khẳng định Redis đang rỗng. Muốn biết bộ nhớ, số khóa hoặc eviction phía server cần nguồn quan sát Redis phù hợp và phải định nghĩa đúng phạm vi: toàn server, một database logic hay một nhóm khóa của cache. Không tự dùng số khóa của cả Redis làm số phần tử của riêng cache `products`.

## 9. Chẩn đoán theo dấu hiệu

| Dấu hiệu | Các bước kiểm tra có căn cứ |
| --- | --- |
| Không thấy tên `cache.gets` | Xác minh Actuator/registry, loại cache, bộ kết nối tương thích, cache đã tồn tại lúc đăng ký hay chưa |
| Có tên meter nhưng hit/miss đứng ở 0 | Kiểm tra công tắc thống kê và thao tác có đi qua đúng cache/đúng instance hay không |
| Gọi một phương thức nhiều lần mà thân phương thức luôn chạy | Kiểm tra lời gọi qua Spring proxy, khóa, điều kiện cache và việc dữ liệu có bị xóa giữa các lần gọi |
| Có hit/miss nhưng không có `cache.size` | Kiểm tra khả năng của bộ kết nối trước; riêng Redis Boot 3.3 không cung cấp size |
| Size tăng mà `cache.puts` không tăng | Kiểm tra cách thư viện định nghĩa put/load; thí nghiệm Caffeine minh họa trường hợp này |
| Đọc tổng thấy số lượng cao bất ngờ | Lọc theo `result`, cache, bộ quản lý và instance; xem có đang cộng nhiều chuỗi hay không |
| Không truy cập được `/actuator/metrics` | Kiểm tra endpoint được expose, đường dẫn quản trị, cổng và quyền truy cập; đừng vội kết luận thống kê cache hỏng |
| Tỷ lệ hit giảm sau triển khai | Đối chiếu thời điểm khởi động mới và giai đoạn làm nóng cache trước khi thay đổi dung lượng |
| Tỷ lệ hit thấp kéo dài dù có truy cập lặp | Kiểm tra khóa có ổn định không, thời gian hết hạn, chính sách dung lượng và thao tác xóa; xác nhận bằng lưu lượng đại diện |
| Size cao nhưng độ trễ không cải thiện | Đo đường truy cập nguồn và độ trễ thực tế; các phần tử giữ lại có thể ít được dùng lại hoặc cache không nằm trên đoạn xử lý tốn kém |

Khi so sánh hai cấu hình, giữ bài toán và lưu lượng tương đương. Thay cả dung lượng, TTL, kiểu khóa và tập truy cập cùng lúc sẽ khiến khó biết yếu tố nào tạo ra khác biệt. Không có một ngưỡng hit ratio duy nhất đúng cho mọi cache.

## 10. Thực hành và tự kiểm tra

Thực hiện từng thay đổi trên một lần khởi động mới của dự án minh họa:

1. **Đổi thành bốn khóa khác nhau:** gọi `A`, `B`, `C`, `D` mỗi khóa một lần. Trước lần xóa cuối, dự đoán hit = 0, miss = 4, số lần chạy thân dịch vụ = 4, size = 4. Đối chiếu kết quả thay vì đoán từ số lần gọi HTTP.
2. **Chỉ gọi `A` bốn lần:** trước lần xóa cuối, dự đoán hit = 3, miss = 1, số lần chạy thân dịch vụ = 1, size = 1. Sau khi xóa `A`, size phải về 0 trong thí nghiệm này.
3. **Bỏ `recordStats()` rồi chạy lại:** đối chiếu kết quả trả về và số lần chạy thân dịch vụ với hit/miss. Mục tiêu là thấy cache vẫn có thể dùng lại dữ liệu trong khi đường thống kê không cho thông tin cần thiết. Khôi phục cấu hình sau thí nghiệm.
4. **So sánh snapshot và khoảng thời gian:** dùng số liệu giả định ở mục 6 để tự tính phần tăng. Giải thích tại sao không thể lấy tỷ lệ từ `cache.size`.
5. **Giải thích dữ liệu thiếu:** nếu Redis có `cache.gets` nhưng không có `cache.size`, hãy nêu khả năng hỗ trợ của bộ kết nối trước khi đề xuất sửa cấu hình.

Khi đọc một dashboard cache, phải trả lời được: **cache nào, bộ quản lý nào, tiến trình hoặc cụm nào, khoảng thời gian nào, và nhà cung cấp thực sự hỗ trợ số đo nào?** Chỉ sau đó các con số hit, miss và kích thước mới có đủ ngữ cảnh để dùng cho quyết định.
