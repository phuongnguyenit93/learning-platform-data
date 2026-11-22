# @Cacheable: Ảnh hưởng khi thân phương thức có tác dụng phụ

## Mục tiêu

Hiểu chính xác điều gì xảy ra với **tác dụng phụ (side effect) nằm trong thân phương thức** khi phương thức được đánh dấu `@Cacheable`, vì sao có thể mất thao tác quan trọng ở cache hit, và cách tách phần cần chạy mỗi lần gọi ra khỏi phần được phép dùng lại kết quả.

Sau bài này, bạn phải trả lời được:

1. Khi cache hit, những dòng code nào **không chạy**?
2. Vì sao ghi log, kiểm quyền, cập nhật bộ đếm, gửi sự kiện hoặc ghi database trong một phương thức `@Cacheable` có thể sai?
3. Khi miss, eviction, TTL, điều kiện cache, exception hoặc nhiều request đồng thời, tác dụng phụ xảy ra bao nhiêu lần?
4. Làm sao tổ chức service và kiểm thử để hành vi đúng dù cache hit hay miss?

Bối cảnh: Spring Framework Cache Abstraction, phương thức Java trên **Spring bean được gọi qua proxy có caching advice**. Đây là điều kiện quan trọng; lời gọi nội bộ `this.method()` có thể không đi qua proxy mặc định.

## 1. Tác dụng phụ là gì?

Một phương thức có **tác dụng phụ** khi ngoài việc tạo giá trị trả về, nó còn làm thay đổi trạng thái hoặc tạo ra một hiệu ứng có thể quan sát bên ngoài kết quả trả về. Các ví dụ:

- Ghi database, tăng số lượt xem, trừ tồn kho, cập nhật trạng thái phiên làm việc.
- Gửi email/SMS, phát message, gọi API tạo giao dịch hoặc ghi bản ghi audit.
- Ghi log phục vụ audit mỗi lượt truy cập, tăng bộ đếm request, tính phí, ghi thống kê.
- Thay đổi biến instance/static, thêm phần tử vào collection, tạo file.
- Thực thi quy tắc phân quyền hoặc rate limit đặt **bên trong thân phương thức** (đây là hành vi bắt buộc phải kiểm tra cho mỗi request, dù có hay không có thay đổi trạng thái).

Ngược lại, một truy vấn đọc dữ liệu để tạo kết quả được cache là phần việc **có thể chủ động bỏ qua khi cache hit**. Cache phát huy tác dụng chính nhờ bỏ qua phần việc đó.

Ví dụ dễ mắc lỗi:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product getProduct(String productId) {
    viewCounter.increment(productId);  // Muốn tăng cho MỖI lượt truy cập.
    audit.recordView(productId);       // Muốn ghi cho MỖI lượt truy cập.
    return repository.findById(productId).orElseThrow();
}
```

Đây là **mã minh họa, không phải chương trình độc lập** (các lớp `Product`, `viewCounter`, `audit`, `repository` phụ thuộc hệ thống thật). Nếu lời gọi thứ hai có cùng key là cache hit, **cả `viewCounter.increment(...)` lẫn `audit.recordView(...)` đều không chạy**. Nếu nghiệp vụ yêu cầu ghi mỗi lần đọc, thiết kế trên không đúng.

## 2. Đường đi của lời gọi `@Cacheable`

Trong cơ chế chặn lời gọi thông thường:

```text
Caller
  |
  v
Spring proxy / caching advice
  |
  +-- Xác định cache, key, kiểm tra condition (nếu có)
  |
  +-- Cache HIT ------------------> Trả giá trị đã cache
  |                                  (KHÔNG gọi thân phương thức đích)
  |
  +-- Cache MISS --> Gọi phương thức đích
                       |
                       +-- Chạy code trong thân: đọc nguồn,
                       |   tính toán, và mọi tác dụng phụ nếu có
                       |
                       +-- Có kết quả thành công:
                             kiểm tra unless (nếu có)
                             ghi kết quả vào cache nếu phù hợp
                             trả kết quả
```

**Kết luận quan trọng:** `@Cacheable` là cache kết quả **lời gọi phương thức**. Khi hit, kết quả được trả về từ cache và **toàn bộ thân phương thức bị bỏ qua**, không chỉ riêng câu lệnh truy vấn dữ liệu. Do đó không được đặt hành vi bắt buộc chạy mỗi request ở đó.

Đây là mô tả của **thân phương thức đích**. Một số logic ở lớp ngoài như controller, proxy advice khác hay interceptor vẫn có thể chạy, tùy thứ tự các advice và cách ứng dụng cấu hình. Không suy diễn rằng cache hit luôn bỏ qua mọi logging, security hoặc transaction advice của hệ thống; hãy kiểm thử thứ tự tương tác khi phối hợp AOP/Security/Transaction.

| Tình huống | Thân phương thức đích có chạy? | Tác dụng phụ **bên trong thân** |
| --- | --- | --- |
| Miss, chạy thành công | Có | Xảy ra một lần cho lời gọi đó |
| Hit với key đã có | Không | Không xảy ra |
| Entry hết hạn hoặc bị evict, lần đọc tiếp là miss | Có | Xảy ra lại |
| `condition` đánh giá thành `false` | Có, bỏ qua cơ chế cache cho lời gọi này | Xảy ra |
| Miss nhưng `unless` đánh giá thành `true` | Có, kết quả không được lưu | Xảy ra; lần sau có thể lại xảy ra |
| Thân phương thức ném exception | Có nếu trước đó miss/bỏ qua cache | Tác dụng phụ đã thực hiện trước khi ném lỗi có thể vẫn tồn tại; không có kết quả thành công để cache |
| Nhiều request đồng thời cùng miss | Có thể nhiều lần | Có thể lặp lại hoặc cạnh tranh, tùy backend/cấu hình |

Bảng trên giả định lời gọi thực sự được caching advice chặn và không có lỗi cache khác. `@Cacheable` **không cam kết đúng một lần thực thi** cho một key trong suốt vòng đời ứng dụng.

## 3. Ví dụ chạy được: lỗi side effect và cách tách đúng

Ví dụ dùng **Java 17+ và Spring Boot với Gradle**. Không cần database hay Redis; chủ động chọn `ConcurrentMapCacheManager` để thấy rõ hành vi. Biến `notifications` chỉ là danh sách mô phỏng sự kiện đã gửi; chương trình không thực sự gửi thông báo ra bên ngoài.

Trong dự án Spring Boot đã cấu hình Java 17+ và plugin Spring Boot, thêm dependency vào `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
```

### 3.1. Cấu hình cache cho demo

File `src/main/java/example/cache/CacheConfig.java`:

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
        return new ConcurrentMapCacheManager("unsafeReports", "safeReports");
    }
}
```

### 3.2. Trường hợp sai: side effect nằm trong phương thức `@Cacheable`

File `src/main/java/example/cache/UnsafeReportService.java`:

```java
package example.cache;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class UnsafeReportService {
    private final AtomicInteger bodyRuns = new AtomicInteger();
    private final List<String> notifications = new CopyOnWriteArrayList<>();

    @Cacheable(cacheNames = "unsafeReports", key = "#p0")
    public String getReport(String customerId) {
        int n = bodyRuns.incrementAndGet();
        notifications.add("report-ready:" + customerId);
        System.out.println("BAD BODY " + customerId + " #" + n);
        return "report:" + customerId;
    }

    @CacheEvict(cacheNames = "unsafeReports", key = "#p0")
    public void invalidate(String customerId) {
        // Không sửa dữ liệu; chỉ evict cache entry theo customerId.
    }

    public String state() {
        return "bad bodyRuns=" + bodyRuns.get()
                + ", notifications=" + notifications.size();
    }
}
```

Nếu người dùng gọi `getReport("c1")` nhiều lần, yêu cầu cache hit khiến `notifications.add(...)` bị bỏ qua. Giả sử đó là event nghiệp vụ bắt buộc phát mỗi lần truy cập thì số event bị thiếu. Sau evict, phương thức chạy lại và event lại xuất hiện; chính điều này cho thấy side effect đang phụ thuộc vào trạng thái cache.

### 3.3. Trường hợp đúng: cache phần tạo dữ liệu, tác dụng phụ ở service gọi

File `src/main/java/example/cache/CachedReportService.java`:

```java
package example.cache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CachedReportService {
    private final AtomicInteger sourceReads = new AtomicInteger();

    @Cacheable(cacheNames = "safeReports", key = "#p0")
    public String getReport(String customerId) {
        sourceReads.incrementAndGet(); // Bộ đếm để quan sát cache miss của demo.
        return "report:" + customerId;
    }

    public int sourceReads() {
        return sourceReads.get();
    }
}
```

File `src/main/java/example/cache/ReportRequestService.java`:

```java
package example.cache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Service;

@Service
public class ReportRequestService {
    private final CachedReportService cachedReports;
    private final AtomicInteger requests = new AtomicInteger();

    public ReportRequestService(CachedReportService cachedReports) {
        this.cachedReports = cachedReports;
    }

    public String handle(String customerId) {
        int n = requests.incrementAndGet(); // Chạy cho MỖI lời gọi handle.
        System.out.println("REQUEST " + customerId + " #" + n);
        return cachedReports.getReport(customerId);
    }

    public int requestCount() {
        return requests.get();
    }
}
```

Ở thiết kế này, `ReportRequestService.handle(...)` là điểm vào xử lý yêu cầu, chạy mỗi lần được gọi. Nó gọi **bean khác** `CachedReportService`, nên việc lấy dữ liệu vẫn đi qua proxy Spring Cache. Bộ đếm request đặt ở ngoài phương thức cache không phụ thuộc hit/miss. Trong ứng dụng thật, audit, authorization, rate limiting và xử lý giao dịch phải được đặt ở **ranh giới thực thi phù hợp**, với bảo đảm riêng của từng nghiệp vụ; code này chỉ chứng minh cách phân tách.

### 3.4. Chạy demo và đối chiếu kết quả

File `src/main/java/example/cache/CacheDemoApplication.java`:

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
    CommandLineRunner demo(UnsafeReportService unsafe,
                           ReportRequestService requests,
                           CachedReportService cached) {
        return args -> {
            System.out.println(unsafe.getReport("c1")); // miss
            System.out.println(unsafe.getReport("c1")); // hit
            System.out.println(unsafe.state());

            unsafe.invalidate("c1");                     // evict
            System.out.println(unsafe.getReport("c1")); // miss trở lại
            System.out.println(unsafe.state());

            System.out.println(requests.handle("c2"));  // miss
            System.out.println(requests.handle("c2"));  // hit
            System.out.println("requestCount=" + requests.requestCount()
                    + ", sourceReads=" + cached.sourceReads());
        };
    }
}
```

Trong thư mục dự án, chạy:

```bash
./gradlew bootRun
# Trên Windows PowerShell:
# .\gradlew.bat bootRun
```

Các dòng **do code demo in ra** theo đúng thứ tự (không tính log khởi động Spring Boot):

```text
BAD BODY c1 #1
report:c1
report:c1
bad bodyRuns=1, notifications=1
BAD BODY c1 #2
report:c1
bad bodyRuns=2, notifications=2
REQUEST c2 #1
report:c2
REQUEST c2 #2
report:c2
requestCount=2, sourceReads=1
```

Đọc kết quả:

- Hai lượt `unsafe.getReport("c1")` chỉ làm thân phương thức chạy **một lần** nên chỉ có một notification mô phỏng.
- Sau `invalidate("c1")`, kết quả trong `unsafeReports` bị xóa; lượt đọc tiếp chạy thân lần hai và tạo notification thứ hai.
- Hai lượt `requests.handle("c2")` đều chạy phần đếm request, nhưng `cached.getReport("c2")` chỉ thực sự chạy phần nạp dữ liệu một lần nhờ cache hit ở lần thứ hai.
- Tên cache `unsafeReports` và `safeReports` khác nhau để hai phép thử không làm ảnh hưởng kết quả của nhau.

Đây là ví dụ Spring Boot gồm năm file Java, **không phải một file độc lập chạy trực tiếp bằng `javac`**. `ConcurrentMapCacheManager` dùng bộ nhớ trong tiến trình, không tự có TTL/giới hạn dung lượng như các backend chuyên dụng.

## 4. Vì sao cách làm sai có thể gây lỗi nghiêm trọng?

### 4.1. Bỏ sót hành vi phải chạy mọi lần

Giả sử `@Cacheable` bọc phương thức vừa lấy giá vừa ghi audit mỗi lần xem giá. Cache hit khiến audit thiếu bản ghi. Điều tương tự có thể xảy ra nếu gửi notification, tăng số lần xem, khấu trừ số lượng hoặc tính phí trong thân phương thức. **Không dùng cache hit/miss làm điều kiện quyết định thực hiện lệnh nghiệp vụ.**

Trường hợp đặc biệt nguy hiểm là method vốn biểu diễn **command**: `chargePayment(...)`, `createOrder(...)`, `sendEmail(...)`, `recordLogin(...)`. Đưa `@Cacheable` lên những method này có thể biến các lần gọi sau thành chỉ trả kết quả cũ mà không thực hiện command. Cơ chế idempotency của command, nếu cần, phải dựa trên khóa nghiệp vụ, trạng thái bền vững và quy tắc giao dịch riêng; cache kết quả không thay thế được các bảo đảm đó.

### 4.2. Dữ liệu trả về che giấu việc không thực thi

Caller vẫn nhận một kết quả trông hợp lệ khi hit. Vì thế một endpoint có thể trả HTTP 200 trong khi logic ghi audit, refresh trạng thái, validate điều kiện đang thay đổi hoặc tăng request metric bên trong thân phương thức đã không chạy. Khi test, đừng chỉ assert response; hãy assert cả trạng thái bên ngoài mà nghiệp vụ yêu cầu.

### 4.3. Kết quả phụ thuộc trạng thái ngoài key

Nếu phương thức đọc thời gian hiện tại, quyền người dùng, tỷ giá, locale, tenant hoặc trạng thái database để quyết định trả gì, thì một cache key chỉ gồm `productId` có thể trả giá trị của ngữ cảnh cũ. Đây còn là vấn đề **độ đúng của dữ liệu** ngoài vấn đề side effect.

Quy tắc: cùng key phải đại diện cho kết quả có thể dùng chung theo chính sách độ mới và quyền truy cập. Bao gồm các thành phần cần thiết trong key, ví dụ tenant, quyền hoặc ngôn ngữ nếu chúng quyết định dữ liệu; evict khi nguồn thay đổi. Tránh đưa bí mật chưa xử lý vào key/log.

### 4.4. Transaction và ngoại lệ không cứu được side effect

Cache hit làm thân phương thức không chạy, vì vậy mọi thao tác ghi/kiểm tra **nằm trong thân** đều không được thực hiện. Với cache miss, nếu ghi ra hệ ngoài rồi phương thức ném exception, tác dụng phụ đã xảy ra có thể không được hoàn tác. Một transaction database không tự rollback được email/message/API ngoài transaction. Khi kết hợp `@Transactional` và caching advice, thứ tự interceptor cùng thời điểm cập nhật/evict có thể ảnh hưởng nhất quán; không dựa vào giả định chỉ nhìn annotation. Với nghiệp vụ cần phát sự kiện đáng tin sau commit, cân nhắc transaction synchronization hoặc transactional outbox phù hợp.

## 5. Những thuộc tính `@Cacheable` có ảnh hưởng đến tần suất chạy

`condition` là điều kiện xét trước khi cache lookup; nếu điều kiện không thỏa, Spring sẽ gọi thân phương thức mà không dùng cache cho lời gọi đó:

```java
@Cacheable(cacheNames = "reports", key = "#p0",
           condition = "#p0 != 'internal'")
public String load(String customerId) {
    // Nếu customerId là "internal": phương thức luôn chạy.
    return loadFromSource(customerId);
}
```

`unless` được xét **sau khi thân đã chạy và có kết quả** khi có thể cache. Nó quyết định không lưu kết quả của lần miss đó, **không làm side effect bên trong thân trở nên an toàn**:

```java
@Cacheable(cacheNames = "reports", key = "#p0",
           unless = "#result == null")
public String find(String customerId) {
    return lookupNullable(customerId);
}
```

Hai đoạn trên là **mã minh họa**, `loadFromSource`/`lookupNullable` cần được định nghĩa bởi ứng dụng. Nếu phương thức ném exception, một kết quả cache thành công không được ghi cho lời gọi đó. Nếu kết quả bị `unless` loại, các lời gọi sau có thể lại miss và chạy side effect.

`@Cacheable(sync = true)` có thể giúp tránh nhiều lần tính toán cùng key khi có nhiều request đồng thời **và nhà cung cấp cache hỗ trợ**. Nó có các giới hạn kết hợp annotation (ví dụ không dùng với `unless`), và không bảo đảm một side effect nghiệp vụ xảy ra đúng một lần trong suốt vòng đời dữ liệu: entry có thể bị evict, hết hạn, failover, đổi backend hoặc truy cập từ các instance khác. Đừng dùng `sync = true` như cơ chế chống gửi email/giao dịch trùng lặp.

Phân biệt `@CachePut`: phương thức gắn `@CachePut` **luôn chạy** rồi cập nhật cache bằng kết quả trả về; nó dành cho trường hợp ghi nguồn và làm mới cache phù hợp, chứ không phải mẹo sửa mọi vấn đề side effect của `@Cacheable`. `@CacheEvict` xóa entry để lần đọc sau miss; việc **xóa entry khiến body chạy lại** càng chứng tỏ số lần side effect không ổn định nếu đặt sai chỗ.

## 6. Quy tắc thiết kế an toàn

1. **Nhận diện phần có thể cache:** tách thành một hàm đọc/biến đổi mà việc bỏ qua khi cache hit không làm thiếu hành động nghiệp vụ. Hàm này có thể truy vấn database/IO để tạo kết quả lúc miss, nhưng không nên thực hiện command bên ngoài.
2. **Đặt hành vi cần mỗi lần ở tầng bao ngoài:** ví dụ controller/filter/service điều phối ghi nhận lượt truy cập, xác thực, rate limit, audit; rồi gọi **một bean khác** cung cấp phương thức `@Cacheable`. Nếu audit phải đáng tin cậy, dùng cơ chế bền vững phù hợp và xác định rõ khi nào ghi.
3. **Thiết kế key và eviction:** cùng kết quả phải có key nhất quán; khác tenant/quyền/ngữ cảnh thì không dùng nhầm entry. Thay đổi dữ liệu gốc cần chiến lược update/evict và TTL phù hợp.
4. **Xác định phạm vi đảm bảo:** local cache theo từng JVM, cache dùng chung và cache nhiều replica có hành vi đồng thời/nhất quán khác nhau. Cache không bảo đảm exactly-once hoặc transaction cho side effect.
5. **Đặt phép đo đúng vị trí:** metric đếm **request** đặt ngoài `@Cacheable`; metric đếm **thực thi body/truy vấn nguồn** có thể đặt bên trong để chẩn đoán miss. Hai metric trả lời hai câu hỏi khác nhau.
6. **Gọi qua Spring bean:** lời gọi `this.cachedMethod(...)` trong cùng bean (proxy mặc định) bỏ qua caching advice; có thể làm body luôn chạy và che giấu thiết kế sai trong test. Hãy kiểm thử bằng đường gọi thực tế.

### Bảng quyết định nhanh

| Hành vi | Đặt trong thân `@Cacheable`? | Lý do |
| --- | --- | --- |
| Đọc database để tạo giá trị cache | Có thể | Miss đọc nguồn, hit dùng lại dữ liệu |
| Tính toán thuần túy, tốn CPU | Có thể | Hit tránh tính lại |
| Audit bắt buộc cho mọi lần truy cập | Không | Hit bỏ qua body |
| Gửi message/email cho mọi yêu cầu | Không | Hit bỏ qua; nhiều miss có thể lặp |
| Ghi order/payment/stock | Không | Command cần bảo đảm nghiệp vụ riêng |
| Metric số request đến hệ thống | Không | Body chỉ phản ánh lần thực thi thực sự |
| Metric số lần load từ nguồn (để học/chẩn đoán) | Có thể | Cố ý đo số miss thực thi, không đo request |
| Kiểm tra quyền truy cập dựa trên ngữ cảnh thay đổi | Không đặt *chỉ* trong body | Hit có thể bỏ qua; phải kiểm tra mỗi yêu cầu và thiết kế key chính xác |

## 7. Cách kiểm thử đúng theo hành vi

Không chỉ đo thời gian nhanh/chậm. Với một key `k`, hãy quan sát **hai đại lượng riêng**: số lần nhận yêu cầu và số lần thân phương thức chạy.

| Bước | Thao tác | Kỳ vọng |
| --- | --- | --- |
| 1 | Gọi lần đầu với `k` | Miss; body chạy một lần; kết quả lưu cache |
| 2 | Gọi lại với cùng `k` | Hit; body không chạy; phần điều phối ngoài body vẫn chạy |
| 3 | Gọi với key khác `k2` | Miss cho `k2`; body chạy |
| 4 | Evict `k` rồi gọi lại | Miss trở lại; body chạy thêm lần nữa |
| 5 | Khi `condition=false` hoặc `unless=true` | Hiểu trường hợp không sử dụng/không lưu cache và số lần body tương ứng |
| 6 | Cho body ném exception sau một tác dụng phụ giả lập | Không có kết quả thành công để cache; xác định side effect nào đã xảy ra |
| 7 | Gọi đồng thời cùng key trên backend mục tiêu | Xác nhận số lần load thực tế, thử có và không có `sync` khi được hỗ trợ |
| 8 | Thử hai tenant/quyền khác nhau | Không nhận nhầm kết quả hay bỏ qua kiểm tra cần thiết |

Khi viết integration test với Spring, hãy gọi bean từ ApplicationContext (qua proxy), dùng cache manager có kiểm soát, clear entry giữa các test độc lập và assert cả kết quả lẫn số lần thực thi body. Với side effect giả lập, có thể dùng fake/repository mock hoặc biến đếm; với nghiệp vụ thực, test thêm transaction/rollback, đồng thời và nhiều instance theo kiến trúc triển khai.

## 8. Những nhầm lẫn thường gặp

- **“Lần nào gọi method thì code bên trong cũng chạy.”** Sai khi `@Cacheable` có cache hit: caller nhận giá trị, thân method có thể không chạy.
- **“Tôi chỉ cache return value, log/audit trong method vẫn chạy.”** Sai nếu log/audit ở thân method đích bị chặn bởi cache.
- **“Dùng `@Cacheable(sync=true)` thì side effect đúng một lần.”** Sai: không đảm bảo exactly-once cho nghiệp vụ.
- **“Cache có TTL nên gửi event trong body là được.”** Sai: số event phụ thuộc hit/miss và thời điểm hết hạn, không phụ thuộc số yêu cầu thật.
- **“Có `@Transactional` thì mọi chuyện đã an toàn.”** Sai: cache, transaction và side effect ngoài database có hợp đồng khác nhau, còn phụ thuộc ranh giới và thứ tự thực thi.
- **“Test gọi `this.cachedMethod()` thấy body chạy liên tục nên cache vô hại.”** Test có thể đang bỏ qua Spring proxy, không phản ánh đường gọi production.
- **“Tôi đặt kiểm quyền trong body nên cache không ảnh hưởng.”** Cache hit có thể bỏ qua kiểm tra đó; phải thiết kế security theo mỗi request và phân vùng dữ liệu cache đúng.

**Nguyên tắc cần nhớ:** Chỉ đặt `@Cacheable` lên phần công việc mà ứng dụng **được phép không thực thi** khi đã có kết quả phù hợp trong cache. Mọi hành vi bắt buộc diễn ra cho mỗi request phải có đường thực thi độc lập với việc hit hay miss.

## Tài liệu tra cứu

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Annotation-based caching (`@Cacheable`, `condition`, `unless`, `sync`): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Boot — Caching support: https://docs.spring.io/spring-boot/reference/io/caching.html
