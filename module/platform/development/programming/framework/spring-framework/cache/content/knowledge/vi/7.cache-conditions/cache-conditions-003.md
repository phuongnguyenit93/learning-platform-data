# Phân biệt điều kiện bỏ qua cache với điều kiện nghiệp vụ

## 1. Hai câu hỏi khác nhau

Trong Spring Framework, thuộc tính `condition` của `@Cacheable` trả lời câu hỏi:

> **Lời gọi này có nên tham gia cơ chế đọc/ghi cache hay không?**

Điều kiện nghiệp vụ (business rule) trả lời câu hỏi khác:

> **Lời gọi này có hợp lệ, được phép thực hiện và cần xử lý theo quy tắc nào?**

Hai loại điều kiện có thể cùng xuất hiện trong một ứng dụng, nhưng không thay thế nhau. Ví dụ: một sản phẩm đang khuyến mãi có giá đổi liên tục nên **không dùng cache**; đó là quyết định hiệu năng và tính mới. Một người dùng không có quyền xem giá dành riêng cho đối tác phải **bị từ chối truy cập**; đó là quy tắc nghiệp vụ hoặc phân quyền.

```text
Request
  |
  v
Kiểm tra nghiệp vụ / quyền truy cập cần áp dụng cho từng request
  |-- Không hợp lệ: từ chối hoặc trả lỗi nghiệp vụ
  '-- Hợp lệ
       |
       v
    Lời gọi qua Spring cache proxy
       |-- @Cacheable.condition = false
       |      -> bỏ qua đọc và ghi cache -> chạy phương thức
       '-- @Cacheable.condition = true
              |-- cache HIT -> trả dữ liệu cache, bỏ qua thân phương thức
              '-- cache MISS -> chạy phương thức -> xét unless -> có thể lưu
```

**Mấu chốt:** `condition = false` **không** có nghĩa là “từ chối gọi phương thức”. Nó có nghĩa là **không sử dụng cache cho lần gọi này**. Phương thức đích vẫn được thực thi (trong luồng đồng bộ thông thường).

Nếu điều kiện nghiệp vụ nằm bên trong thân phương thức gắn `@Cacheable` thì **cache hit có thể bỏ qua luôn điều kiện đó**. Vì vậy, những kiểm tra phải thực hiện ở **mọi request** (như xác thực/ủy quyền động) phải ở ranh giới được chạy trước khi trả kết quả từ cache.

## 2. `@Cacheable(condition = ...)` hoạt động lúc nào?

Một ví dụ:

```java
@Cacheable(
    cacheNames = "prices",
    key = "#p0",
    condition = "#p0 != 'FLASH'"
)
public Integer loadPrice(String sku) {
    return repository.loadPrice(sku);
}
```

*Đoạn code này minh họa annotation; `repository` cần được triển khai. Ví dụ đầy đủ có thể chạy nằm ở mục 6.*

Biểu thức `condition` là SpEL và được đánh giá **trước** thao tác tra cache của `@Cacheable`. `#p0` là đối số đầu tiên, ở đây là `sku`.

- `loadPrice("FLASH")`: `condition` trả `false`. Spring **bỏ qua cả cache lookup và cache put** của operation này, sau đó gọi `loadPrice` thật. Lần gọi sau với `"FLASH"` cũng chạy phương thức.
- `loadPrice("STANDARD")`: `condition` trả `true`. Spring kiểm tra cache `prices` với key `"STANDARD"`. Nếu hit, thân method **không chạy**; nếu miss, method chạy và kết quả có thể được lưu.
- `condition` chỉ quyết định sử dụng caching cho operation này. Nó **không kiểm tra quyền**, **không đánh giá tính hợp lệ nghiệp vụ** và **không ngăn lời gọi đến cơ sở dữ liệu** khi biểu thức trả `false`.

Đây thường là một chính sách cache có chủ đích: không cache các giá thay đổi nhanh, request cần dữ liệu tươi, truy vấn thử nghiệm hoặc lời gọi có đầu vào không thích hợp để cache.

Lưu ý: `condition` được đánh giá dựa trên dữ liệu **đã có trước khi phương thức trả về**, như các tham số `#p0`, `#p1` hoặc metadata được Spring hỗ trợ. Không dùng `#result` trong `@Cacheable(condition = ...)` vì lúc đó chưa có kết quả phương thức.

## 3. Điều kiện nghiệp vụ nằm ở đâu và làm gì?

Điều kiện nghiệp vụ có thể là:

- **Tiền điều kiện:** số lượng đặt hàng phải lớn hơn 0, mã hàng phải tồn tại, yêu cầu phải đúng trạng thái.
- **Quy tắc tính toán:** đơn hàng từ 10 sản phẩm được áp dụng mức giá khác; người dùng thuộc nhóm nào thì chọn chính sách nào.
- **Kiểm soát truy cập:** người gọi có được xem dữ liệu của tenant, tài khoản hoặc khách hàng này không.
- **Bất biến và hậu điều kiện:** không cho bán quá tồn kho; dữ liệu sau cập nhật phải thỏa điều kiện nhất quán.

Có trường hợp kết quả sau khi áp dụng quy tắc nghiệp vụ **có thể cache an toàn**. Ví dụ, giá niêm yết của SKU chuẩn không thay đổi trong 10 phút và không phụ thuộc người gọi. Khi đó, tính một lần và dùng lại có thể hợp lý.

Nhưng một quy tắc **cần được đánh giá lại ở mỗi request** thì không thể chỉ đặt bên trong thân method `@Cacheable`:

```java
// Ví dụ nguy hiểm: kiểm tra quyền có thể bị bỏ qua khi cache hit
@Cacheable(cacheNames = "documents", key = "#p0")
public Document getDocument(String documentId, User caller) {
    permissionService.assertCanRead(caller, documentId);
    return repository.find(documentId);
}
```

*Đoạn trên minh họa lỗi thiết kế; `Document`, `User`, `permissionService` và `repository` chưa được định nghĩa.*

Giả sử người A hợp lệ gọi `getDocument("DOC-1", A)` khiến cache lưu theo key `"DOC-1"`. Sau đó người B không có quyền gọi `getDocument("DOC-1", B)`: nếu hit, phương thức **không chạy**, nên `permissionService.assertCanRead` cũng **không chạy**. Đó là một lỗi kiểm soát truy cập tiềm ẩn.

Cách thiết kế rõ ràng hơn: kiểm tra quyền ở một service hoặc lớp bảo vệ được thực thi trước lời gọi đến bean cacheable. Nếu kết quả mang tính cá nhân hoặc tenant, cache key và phạm vi lưu trữ cũng phải phân biệt đầy đủ mọi ngữ cảnh ảnh hưởng đến dữ liệu. Việc đưa user ID vào key có thể giảm trộn dữ liệu, nhưng **không thay thế việc kiểm tra quyền tại thời điểm request**.

## 4. So sánh chính xác `condition`, `unless` và `if` nghiệp vụ

| Cơ chế | Trả lời câu hỏi | Thời điểm | Khi điều kiện không thỏa |
| --- | --- | --- | --- |
| `@Cacheable(condition = "...")` | Có tham gia tra/ghi cache lần này không? | Trước khi cache lookup | Bỏ qua cache, **vẫn gọi phương thức** |
| `@Cacheable(unless = "...")` | Có nên **không lưu kết quả mới** này không? | Sau khi method chạy ở lần miss | `unless = true` thì **không ghi cache**; kết quả vẫn trả về |
| `if (...)` trong thân method | Xử lý nghiệp vụ hoặc từ chối đầu vào như thế nào? | Khi thân method thực sự chạy | Theo code: có thể throw, return, đổi nhánh xử lý |
| Kiểm tra chính sách trong facade/filter trước bean cacheable | Request này có được phép đi tiếp không? | Trước lời gọi cacheable | Có thể từ chối ngay, dù cache chứa dữ liệu |
| `@CacheEvict` sau thao tác thay đổi dữ liệu | Cần loại bỏ kết quả lưu trước đó không? | Thường sau khi method hoàn thành thành công | Xóa entry để lần đọc kế tiếp nạp dữ liệu mới |

Ví dụ kết hợp:

```java
@Cacheable(
    cacheNames = "prices",
    key = "#p0",
    condition = "#p0 != 'FLASH'",
    unless = "#result == null"
)
public Integer loadPrice(String sku) {
    if (sku.isBlank()) {
        throw new IllegalArgumentException("SKU required");
    }
    return repository.findPrice(sku);
}
```

*Ví dụ riêng minh họa cú pháp; `repository` chưa định nghĩa.*

Diễn giải:

1. `sku == "FLASH"`: không dùng cache; method chạy và sẽ thực thi `if`.
2. `sku == "STANDARD"`, cache miss: method chạy, có thể throw vì rule, hoặc trả giá; sau đó mới xét `unless`.
3. `sku == "STANDARD"`, cache hit: method không chạy, cả `if` **bên trong method** bị bỏ qua. Vì vậy, nếu `if` là kiểm tra quyền phải làm mỗi request, vị trí đó là không phù hợp.
4. Nếu method trả `null` trong lượt miss: `unless` là `true`, Spring không lưu null; điều này không phải một lỗi nghiệp vụ được tự động trả về.
5. Nếu method throw exception: không có giá trị trả về bình thường để lưu theo `@Cacheable` mặc định.

**Không nhầm ngữ nghĩa biểu thức:** `condition = false` là “cache bypass”; `unless = true` là “veto cache put”; `throw new ...` là “từ chối nghiệp vụ”. Ba hành vi khác nhau, dễ quan sát bằng output của chương trình.

## 5. Chọn vị trí thực thi phù hợp cho từng loại quy tắc

Một thiết kế service thường có hai lớp:

```text
HTTP / caller
    |
    v
PriceFacade.getPrice(sku, caller)
    |-- validate request
    |-- authorize caller
    '-- PriceLookupService.loadPrice(sku)
            |-- Spring @Cacheable interceptor
            |     condition / key / hit / miss / unless
            '-- method body nếu cache miss hoặc bypass
                  -> database / phép tính tốn kém
```

**Lớp ngoài** xử lý tiền điều kiện và quyền phải kiểm tra mỗi lượt. **Lớp cacheable** xử lý truy vấn/tính toán mà kết quả có thể tái sử dụng khi cùng key. Đây là một cách tổ chức dễ hiểu, không phải quy tắc bắt buộc phải có đúng hai class.

Chú ý hai ranh giới:

- Nếu tính giá **thực sự phụ thuộc** vào nhóm khách hàng hoặc tenant, cần đưa những biến ảnh hưởng đầu ra vào cache key (hoặc dùng cache name/scope riêng) để tránh sử dụng nhầm giá. Nếu dữ liệu rất nhạy cảm, cân nhắc không cache ở tầng dùng chung.
- Các hành động có **side effect bắt buộc mỗi lần** (ghi giao dịch, cập nhật tồn kho, gửi sự kiện) không phù hợp để bị bỏ qua bởi `@Cacheable`. Cache nên chứa thao tác đọc/tính toán có thể lặp lại và có chiến lược làm mới đúng nghiệp vụ.

Đừng tin rằng đặt `condition = "#caller.isAdmin()"` là cách thực hiện phân quyền. Nó chỉ quyết định cache cho admin; lời gọi của non-admin vẫn vào phương thức. Một biểu thức cache condition không phải hàng rào bảo mật.

## 6. Ví dụ Java 17+ chạy được: cache bypass và business rule độc lập

Chương trình Spring Boot sau có hai bean:

- `PriceFacade` kiểm tra đầu vào và quyền **mỗi lần** người dùng gọi.
- `PriceLookupService` dùng `@Cacheable` để quyết định những SKU nào được cache. `FLASH` luôn bypass cache, còn `UNKNOWN` trả `null` và bị `unless` từ chối lưu.

Một bộ đếm trong phương thức tra cứu cho thấy **khi nào thân phương thức thực sự chạy**. Toàn bộ ví dụ chạy với Java 17+, Maven và Spring Boot 3.3.5, dùng cache local trong bộ nhớ.

Cấu trúc:

```text
business-vs-cache/
├── pom.xml
└── src/main/java/example/cachepolicy/
    ├── Application.java
    ├── PriceFacade.java
    └── PriceLookupService.java
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
    <artifactId>business-vs-cache</artifactId>
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

**`src/main/java/example/cachepolicy/PriceLookupService.java`**

```java
package example.cachepolicy;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class PriceLookupService {
    private final AtomicInteger loads = new AtomicInteger();

    @Cacheable(
        cacheNames = "prices",
        key = "#p0",
        condition = "#p0 != 'FLASH'",
        unless = "#result == null"
    )
    public Integer loadPrice(String sku) {
        int callNumber = loads.incrementAndGet();
        System.out.println("LOAD #" + callNumber + " " + sku);

        return switch (sku) {
            case "STANDARD" -> 100;
            case "FLASH" -> 80;
            default -> null;
        };
    }
}
```

**`src/main/java/example/cachepolicy/PriceFacade.java`**

```java
package example.cachepolicy;

import org.springframework.stereotype.Service;

@Service
public class PriceFacade {
    private final PriceLookupService lookup;

    public PriceFacade(PriceLookupService lookup) {
        this.lookup = lookup;
    }

    public Integer getPrice(String sku, boolean allowedToView) {
        // Quy tắc nghiệp vụ: phải kiểm tra ở mọi request.
        if (!allowedToView) {
            throw new SecurityException("Access denied");
        }
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU required");
        }

        // Lời gọi này đi qua proxy của bean khác nên @Cacheable có hiệu lực.
        return lookup.loadPrice(sku);
    }
}
```

**`src/main/java/example/cachepolicy/Application.java`**

```java
package example.cachepolicy;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("prices");
    }

    @Bean
    CommandLineRunner demo(PriceFacade prices) {
        return args -> {
            System.out.println("S1 -> " + prices.getPrice("STANDARD", true));
            System.out.println("S2 -> " + prices.getPrice("STANDARD", true));

            try {
                prices.getPrice("STANDARD", false);
            } catch (SecurityException ex) {
                System.out.println("DENY -> " + ex.getMessage());
            }

            System.out.println("F1 -> " + prices.getPrice("FLASH", true));
            System.out.println("F2 -> " + prices.getPrice("FLASH", true));
            System.out.println("U1 -> " + prices.getPrice("UNKNOWN", true));
            System.out.println("U2 -> " + prices.getPrice("UNKNOWN", true));
        };
    }
}
```

Chạy trong thư mục chứa `pom.xml`:

```bash
mvn spring-boot:run
```

Các dòng của ví dụ theo **thứ tự chính xác** bên dưới; console còn có log khởi động của Spring Boot:

```text
LOAD #1 STANDARD
S1 -> 100
S2 -> 100
DENY -> Access denied
LOAD #2 FLASH
F1 -> 80
LOAD #3 FLASH
F2 -> 80
LOAD #4 UNKNOWN
U1 -> null
LOAD #5 UNKNOWN
U2 -> null
```

Vì sao có kết quả đó?

| Lượt | Business rule ở `PriceFacade` | Quyết định cache | Thân `loadPrice` có chạy? |
| --- | --- | --- | --- |
| S1, STANDARD | Cho phép | `condition=true`, miss | Có: in `LOAD #1`, cache `100` |
| S2, STANDARD | Cho phép | `condition=true`, hit | Không; trả `100` từ cache |
| DENY, STANDARD | **Từ chối** trước khi gọi lookup | Không tra cache | Không; ném `SecurityException` |
| F1 và F2, FLASH | Cho phép | `condition=false` mỗi lần | Có cả hai lần; in `LOAD #2` và `LOAD #3` |
| U1 và U2, UNKNOWN | Cho phép | Miss; `unless=true` do result null | Có cả hai lần; in `LOAD #4` và `LOAD #5` |

Đây là bằng chứng trực quan cho ba hành vi khác nhau:

- **Business reject:** `DENY` phát sinh dù cache `STANDARD` đã có kết quả. Lớp kiểm tra quyền chạy trước lời gọi đến bean cacheable.
- **Cache bypass:** `FLASH` không bị từ chối. Mỗi lần đều trả `80`, nhưng phương thức phải chạy lại vì `condition=false`.
- **Skip cache put:** `UNKNOWN` được phép thực thi, nhưng kết quả `null` không được lưu do `unless=true`. Vì thế lượt U2 vẫn chạy method.

Chương trình minh họa bằng dữ liệu cố định và `ConcurrentMapCacheManager`, không phải ứng dụng xác thực thật. Boolean `allowedToView` chỉ mô phỏng quyết định phân quyền; trong hệ thống thực, quyền phải được xác minh từ ngữ cảnh tin cậy (như Spring Security), không mù quáng tin cờ boolean do client tự gửi. Cache này nằm trong một JVM, không có TTL tự động hoặc đồng bộ liên node.

## 7. Tác động của cache hit lên logic `if` bên trong method

Một lập trình viên có thể đặt các bước sau trong phương thức cacheable:

```java
@Cacheable(cacheNames = "report", key = "#p0")
public Report getReport(String reportId, User caller) {
    ensurePermission(caller, reportId);
    validateRequest(reportId);
    Report data = loadFromDatabase(reportId);
    return data;
}
```

*Đoạn trên chỉ minh họa: các kiểu và hàm phụ trợ chưa được triển khai.*

Ở **lượt miss**, toàn bộ thân method chạy nên `ensurePermission` và `validateRequest` được thực hiện. Ở **lượt hit**, interceptor trả entry đã lưu, không thực thi hai hàm trên. Đây là một lý do quan trọng để tách kiểm tra quyền khỏi phương thức cacheable khi quyền có thể đổi theo người hoặc thời điểm.

Nhưng không phải cứ có `if` trong method là lỗi. Ví dụ:

```java
@Cacheable(cacheNames = "shipping", key = "#p0 + ':' + #p1")
public int shippingFee(String zone, int weightKg) {
    if (weightKg >= 10) {
        return 50;
    }
    return 20;
}
```

Điều kiện `weightKg >= 10` là **quy tắc tính kết quả**, và nếu kết quả thực sự chỉ phụ thuộc `zone`, `weightKg` thì có thể cache kết quả đó. Lần hit không cần tính lại `if` vì Spring tái sử dụng **kết quả đã tính cho cùng dữ liệu đầu vào**.

Quy tắc nghiệp vụ cần xem xét theo ý nghĩa, không chỉ theo cú pháp `if`: điều kiện **phải kiểm tra lại từng lượt** khác với phép tính **ổn định theo key** có thể tái sử dụng.

## 8. Thiết kế key và invalidation để tránh sai kết quả

Ngay cả khi đặt kiểm tra quyền bên ngoài, kết quả được cache chỉ đúng nếu key phân biệt đủ các biến ảnh hưởng đầu ra.

Ví dụ, giá cá nhân hóa:

```java
@Cacheable(cacheNames = "customerPrices", key = "#p0 + ':' + #p1")
public int loadCustomerPrice(String productId, String customerTier) {
    return calculatePrice(productId, customerTier);
}
```

Ở đây `productId` và `customerTier` đều có thể ảnh hưởng kết quả. Nếu chỉ chọn `key="#p0"`, nhóm `VIP` có thể nhận giá nhóm `STANDARD` hoặc ngược lại. Với multi-tenant, ID tenant thường phải tham gia phạm vi cache/key nếu dữ liệu khác nhau theo tenant; vẫn cần kiểm tra quyền ở một điểm chắc chắn chạy.

Khi dữ liệu nguồn thay đổi, cache hit có thể trả dữ liệu cũ. Phải dùng cơ chế làm mới phù hợp: `@CacheEvict` sau cập nhật thành công, `@CachePut` khi muốn ghi kết quả mới, TTL, versioned key hoặc invalidation liên node. Cần cân nhắc thời điểm transaction commit và race giữa đọc/ghi khi yêu cầu nhất quán cao.

Đừng đặt tiêu chí “nếu dữ liệu thay đổi thì không cache” trong `condition` dựa trên trạng thái chưa được đọc, bởi vì biểu thức condition chạy trước method. Nếu quyết định có lưu phụ thuộc chính **kết quả vừa tải**, dùng `unless`; nếu muốn biết cache có còn tươi, cần chiến lược version/expiry/invalidation ở tầng thích hợp.

## 9. Những sai lầm phổ biến

1. **Dùng `condition=false` để từ chối người dùng.** Spring chỉ bỏ qua cache và vẫn gọi method. Nếu method không tự chặn thì nghiệp vụ vẫn được thực hiện.
2. **Đặt kiểm tra quyền động chỉ trong method cacheable.** Cache hit bỏ qua method, có thể bỏ qua kiểm tra quyền.
3. **Giả định `unless=true` nghĩa là trả lỗi hoặc chạy lại method.** Nó chỉ veto lưu kết quả của lần vừa chạy; kết quả vẫn được trả cho caller.
4. **Trộn kết quả người dùng/tenant khác nhau trong một key.** Key phải phản ánh đủ ngữ cảnh ảnh hưởng kết quả; nhiều dữ liệu nhạy cảm nên tránh cache chung.
5. **Quên tự kiểm tra self-invocation.** Trong proxy mode mặc định, `this.loadPrice(...)` gọi nội bộ trong cùng bean không đi qua cache interceptor nên các quy tắc `condition`/`unless` cũng không được áp dụng.
6. **Cho rằng mọi hit đều mới nhất.** Cache không tự quan sát database; cần chính sách hết hạn hoặc xóa/cập nhật cache.
7. **Đặt side effect trong method cacheable rồi kỳ vọng luôn chạy.** Hit có thể bỏ qua gửi event, ghi log nghiệp vụ hoặc cập nhật trạng thái.
8. **Đánh giá business rule bằng giá trị trả về ở `@Cacheable(condition="#result...")`.** Điều kiện trước lookup chưa có `#result`; phải dùng dữ liệu đầu vào hoặc `unless` nếu câu hỏi là có lưu kết quả vừa tạo không.
9. **Nhầm cache provider với chính sách nghiệp vụ.** Provider quản lý lưu/truy xuất/TTL/eviction theo cấu hình; không tự hiểu điều kiện phân quyền và quy tắc hợp lệ của ứng dụng.

## 10. Tự kiểm tra kiến thức

**Câu 1.** `@Cacheable(condition = "#p0 != 'FLASH'")` gặp `sku="FLASH"`. Liệu phương thức có bị Spring ngăn chạy?

**Đáp án:** Không. Spring bỏ qua cache cho operation này; phương thức thực vẫn được gọi và xử lý theo nghiệp vụ.

**Câu 2.** Một phương thức `@Cacheable` có `if (!allowed) throw ...` trong thân; cache đã có key tương ứng. Có bảo đảm kiểm tra quyền vẫn chạy?

**Đáp án:** Không. Cache hit có thể trả entry ngay tại interceptor và bỏ qua toàn bộ thân method. Kiểm tra quyền cần đặt ở tầng có hiệu lực mỗi request.

**Câu 3.** `condition=true`, cache miss, method trả `null`, `unless="#result == null"`. Điều gì xảy ra?

**Đáp án:** Method đã chạy; `unless` là `true` nên Spring không ghi kết quả mới vào cache. Lượt gọi hiện tại vẫn nhận `null`.

**Câu 4.** Một method tính phí vận chuyển dựa trên `zone` và `weightKg`. Có thể giữ phép tính theo ngưỡng trọng lượng bên trong method cacheable không?

**Đáp án:** Có thể, nếu tính phí ổn định theo các yếu tố đó, key chứa đủ yếu tố và dữ liệu liên quan được làm mới khi cần. Lượt hit trả phí đã tính đúng cho cùng key.

**Câu 5.** Có thể thay toàn bộ logic phân quyền bằng `@Cacheable(condition="#caller.isAuthorized()")` không?

**Đáp án:** Không. Khi điều kiện false, Spring bỏ qua caching nhưng vẫn thực thi phương thức. Kiểm soát truy cập phải do lớp kiểm tra quyền thực hiện và ngăn hành vi trái phép.

## Tài liệu tham khảo

- Spring Framework Reference — *Declarative Annotation-based Caching*, phần *Conditional Caching*: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Reference — *Proxying Mechanisms*, mục self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Boot Reference — *Caching*: https://docs.spring.io/spring-boot/reference/io/caching.html
