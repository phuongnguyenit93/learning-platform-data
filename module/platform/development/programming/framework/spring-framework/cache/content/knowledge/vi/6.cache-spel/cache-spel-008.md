# Kiểm thử biểu thức để tránh khóa thiếu thành phần hoặc sai kiểu

Trong Spring Cache, **SpEL** ở thuộc tính **key** của **@Cacheable** xác định lời gọi nào được dùng lại kết quả đã lưu. Một biểu thức có thể đúng cú pháp nhưng sai nghiệp vụ: bỏ quên tenant, currency hoặc locale; ghép chuỗi gây trùng khóa; làm mất kiểu của định danh; dùng khóa null hoặc khóa từ object mutable. Khi đó cache hit có thể trả dữ liệu của yêu cầu khác mà không chạy thân phương thức.

Mục tiêu của bài học là **kiểm thử hợp đồng của biểu thức key**, không chỉ kiểm tra SpEL có parse được. Người học sẽ xây dựng test kiểm tra từng thành phần, kiểu dữ liệu, key thực tế và hành vi Spring proxy, đồng thời biết khi nào cần chạy test với Redis/Caffeine thay vì chỉ dùng cache trong JVM.

## 1. Một cache key đúng phải đáp ứng điều gì?

Hãy coi **(cache name, key)** là định danh duy nhất của một kết quả được phép tái sử dụng trong cùng ngữ cảnh. Trước khi viết test, xác định những dữ kiện nào thực sự làm thay đổi kết quả.

Ví dụ **quote(sku, tenantId, currency)** có thể phụ thuộc cả ba tham số. Những bất biến cần kiểm tra:

1. **Cùng ngữ cảnh → cùng key:** Lặp lại **("P01", "shop-A", "VND")** được phép cache hit.
2. **Đổi một chiều quyết định kết quả → khác key:** Chỉ thay sku, chỉ thay tenant hoặc chỉ thay currency phải phân biệt entry.
3. **Tham số không liên quan không làm phân mảnh cache:** Nếu **traceId** chỉ để ghi log, thay traceId có thể giữ cùng key khi đã loại nó khỏi biểu thức.
4. **Key ổn định:** Không sử dụng biến ngẫu nhiên, timestamp không cần thiết, địa chỉ object hoặc DTO mutable làm cơ sở identity.
5. **Kiểu không bị gộp sai:** Nếu **Long 42L** và **String "42"** là hai định danh khác nhau, key phải giữ được sự phân biệt theo hợp đồng.
6. **Đọc/ghi/xóa dùng cùng hợp đồng:** **@Cacheable**, **@CachePut** và **@CacheEvict** phải định danh cùng entry khi cùng nói về một kết quả.

**Hit ratio cao không tự chứng minh key đúng.** Một key chỉ theo SKU có thể hit nhiều nhưng trả nhầm kết quả giữa tenant hoặc currency.

## 2. Những biểu thức SpEL cần hiểu khi viết test

Ví dụ minh họa trong Spring service có repository, chưa phải chương trình Java độc lập:

~~~java
@Cacheable(
    cacheNames = "quotes",
    key = "T(java.util.List).of(#p0, #p1, #p2)"
)
public Quote quote(String sku, String tenantId, String currency) {
    return repository.loadQuote(sku, tenantId, currency);
}
~~~

Lời gọi đi qua Spring cache interceptor. **#p0**, **#p1**, **#p2** là ba tham số lần lượt theo vị trí; **T(java.util.List).of(...)** tạo một key dạng List gồm ba thành phần tách biệt, phù hợp để minh họa trong cache lưu khóa Java. **List.of** từ chối phần tử null và sẽ ném **NullPointerException** nếu có null.

| Biểu thức | Ý nghĩa | Test cần có |
| --- | --- | --- |
| **#p0** hoặc **#a0** | Tham số đầu tiên | Có bỏ sót tham số thứ hai/ba không? |
| **#p1**, **#p2** | Tham số thứ hai, thứ ba | Sau khi đổi chữ ký method, vị trí có còn đúng? |
| **#root.args[0]** | Tham số đầu theo metadata | Đúng đối tượng, đúng kiểu? |
| **#root.methodName** | Tên method | Không đủ phân biệt hai class/overload nếu dùng chung cache |
| **#p0.id** | Thuộc tính id của object đầu | Null, getter, uniqueness, các field còn lại |
| **#p0?.id** | Null-safe property access | Nếu kết quả là null, xử lý key ra sao? |
| **'latest'** | String literal trong SpEL | Có đụng key hằng của method khác không? |
| **#p0 + ':' + #p1** | Ghép chuỗi | Có nhập nhằng khi input chứa dấu **:** không? |
| **T(java.util.List).of(#p0, #p1)** | Key tổ hợp | Null, thứ tự, serializer của provider |

Tên tham số **#sku** hay **#tenantId** chỉ resolve đúng khi Spring có metadata tên tham số của Java (thường nhờ **-parameters**). **#p0/#p1** không phụ thuộc tên này. Không dùng **#result** để tính key của **@Cacheable**: kết quả method chưa tồn tại trước cache lookup. **unless = "#result == null"** có thể ngăn lưu kết quả sau khi chạy method; **condition** có thể bỏ qua cache theo input trước khi chạy.

Nếu bỏ thuộc tính **key**, **SimpleKeyGenerator** mặc định dùng **SimpleKey.EMPTY** cho không tham số, thường chính tham số đối với một giá trị không-null không phải mảng, và **SimpleKey(...)** cho nhiều tham số. Spring không tự thêm tên method/class vào key. Hai method dùng chung cache name vẫn phải tránh trùng khóa ngoài ý muốn.

## 3. Test thiếu thành phần: phải thay từng chiều độc lập

Ví dụ sai:

~~~java
@Cacheable(cacheNames = "quotes", key = "#p0")
public String quote(String sku, String tenant, String currency) {
    return pricingClient.quote(sku, tenant, currency);
}
~~~

Hai lời gọi **quote("P01", "shop-A", "VND")** và **quote("P01", "shop-B", "USD")** đều sinh key **"P01"**. Lần sau có thể lấy kết quả của lần trước dù tenant/currency khác nhau. Chỉ thay đồng thời tenant và currency trong một test chưa chứng minh biểu thức có chứa **cả hai**; một biểu thức chỉ chứa currency cũng có thể vượt test đó.

Ma trận tối thiểu:

| Lời gọi so với baseline **(P01, shop-A, VND)** | Kết quả key đúng |
| --- | --- |
| **(P01, shop-A, VND)** lặp lại | Cùng key |
| **(P02, shop-A, VND)** | Khác key |
| **(P01, shop-B, VND)** | Khác key |
| **(P01, shop-A, USD)** | Khác key |

Sửa với **key = "T(java.util.List).of(#p0, #p1, #p2)"** hoặc sử dụng key mặc định của method ba tham số khi mọi tham số đều quyết định kết quả. Cũng áp dụng cho locale, includeTax, priceTier, effectiveDate và permission context nếu chúng thực sự ảnh hưởng output. Phân biệt dữ liệu theo tenant bằng key **không thay thế kiểm tra phân quyền**.

## 4. Test trùng khóa do nối chuỗi

Biểu thức:

~~~java
@Cacheable(cacheNames = "accounts", key = "#p0 + ':' + #p1")
public String lookup(String tenant, String accountId) {
    return gateway.lookup(tenant, accountId);
}
~~~

có thể tạo cùng key cho hai cặp khác nghĩa:

~~~text
tenant="a:b", account="c"   => "a:b:c"
tenant="a",   account="b:c" => "a:b:c"
~~~

SpEL vẫn parse thành công, cache vẫn hoạt động, nhưng identity sai. Test nên chứa dấu phân cách, Unicode, chuỗi rỗng và input có quy tắc chuẩn hóa đặc biệt. Có thể dùng key có cấu trúc như **T(java.util.List).of(#p0,#p1)** trong JVM, hoặc cách mã hóa có length-prefix/escaping rõ ràng cho provider phân tán. Chỉ thêm dấu **":"** không bảo đảm key không nhập nhằng.

## 5. Test sai kiểu do ép về String

~~~java
@Cacheable(cacheNames = "ids", key = "'id:' + #p0")
public String lookup(Object id) {
    return repository.lookup(id);
}
~~~

Với input **42L** (Long) và **"42"** (String), cả hai tạo String key **"id:42"**. Nếu hai kiểu định danh mang nghĩa khác nhau, đây là lỗi va chạm. Trong **ConcurrentMapCache** lưu key Java, biểu thức **#p0** giữ **Long 42L** và **String "42"** là hai key khác nhau theo **equals**; nhưng provider như Redis có thể dùng key converter/serializer riêng.

~~~text
key="'id:' + #p0"  -> Long 42L   -> "id:42"
key="'id:' + #p0"  -> String "42" -> "id:42"  (trùng)

key="#p0" trong local Java cache:
Long 42L != String "42"
~~~

Kiểm tra thêm **Integer/Long**, **"0012"/"12"**, enum/string, timezone, và **BigDecimal("1.0")/BigDecimal("1.00")**. Chỉ chuẩn hóa khi nghiệp vụ xác định các giá trị là tương đương. Cache key đúng trong JVM chưa đủ để khẳng định key vật lý của Redis cũng đúng.

## 6. Những tầng kiểm thử cần phối hợp

| Mức | Xác minh được | Giới hạn |
| --- | --- | --- |
| Unit test hàm tạo key | Tính phân biệt, null/type, ổn định | Không chứng minh Spring proxy chạy annotation |
| Test ExpressionParser riêng | Cú pháp, kết quả khi cung cấp biến mẫu | Evaluation context tự dựng chưa chắc giống cache interceptor |
| Integration test Spring bean | @Cacheable, key thực tế, hit/miss, số lần chạy method | Chưa xác minh Redis/Caffeine cấu hình production |
| Test provider thực tế | Key converter, serializer, prefix, TTL, đa instance | Vẫn cần test hợp đồng nghiệp vụ |

Với annotation quan trọng, nên kiểm thử bằng **bean lấy từ ApplicationContext**, quan sát cả **cache key**, **output** và **số lần thực thi thân phương thức**. Tự tạo object bằng **new** hoặc self-invocation **this.cachedMethod()** trong cùng bean ở proxy mode thông thường sẽ không kích hoạt caching như lời gọi qua Spring proxy.

## 7. Dự án Spring + JUnit 5 chạy được

Dự án dùng **Java 17**, **Spring Framework 6.1.14**, **JUnit Jupiter 5.10.2**, **ConcurrentMapCacheManager**. Những method ghi chú **SAI** cố ý có lỗi để test tái hiện, đối chiếu với method **SỬA**. Không cần database; bộ đếm tăng chỉ khi thân method thực sự chạy.

Cấu trúc:

~~~text
spel-cache-key-tests/
├── settings.gradle
├── build.gradle
├── src/main/java/demo/keys/CacheKeyConfig.java
└── src/test/java/demo/keys/CacheKeyExpressionTest.java
~~~

**settings.gradle**:

~~~groovy
rootProject.name = 'spel-cache-key-tests'
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    testImplementation 'org.springframework:spring-test:6.1.14'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

test {
    useJUnitPlatform()
}
~~~

**src/main/java/demo/keys/CacheKeyConfig.java**:

~~~java
package demo.keys;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheKeyConfig {

    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager(
                "unsafeQuotes", "safeQuotes", "ambiguousKeys",
                "tupleKeys", "unsafeTyped", "typedKeys");
    }

    @Bean
    public QuoteService quoteService() {
        return new QuoteService();
    }

    public static class QuoteService {
        private final AtomicInteger bad = new AtomicInteger();
        private final AtomicInteger good = new AtomicInteger();
        private final AtomicInteger ambiguous = new AtomicInteger();
        private final AtomicInteger tuple = new AtomicInteger();
        private final AtomicInteger badType = new AtomicInteger();
        private final AtomicInteger typed = new AtomicInteger();

        // SAI: Bỏ tenant và currency.
        @Cacheable(cacheNames = "unsafeQuotes", key = "#p0")
        public String unsafeQuote(String sku, String tenant, String currency) {
            return "bad#" + bad.incrementAndGet()
                    + "/" + sku + "/" + tenant + "/" + currency;
        }

        // SỬA: Tách đủ cả ba phần.
        @Cacheable(
            cacheNames = "safeQuotes",
            key = "T(java.util.List).of(#p0, #p1, #p2)"
        )
        public String safeQuote(String sku, String tenant, String currency) {
            return "good#" + good.incrementAndGet()
                    + "/" + sku + "/" + tenant + "/" + currency;
        }

        // SAI: Delimiter không escape.
        @Cacheable(cacheNames = "ambiguousKeys", key = "#p0 + ':' + #p1")
        public String ambiguous(String tenant, String account) {
            return "amb#" + ambiguous.incrementAndGet()
                    + "/" + tenant + "/" + account;
        }

        // SỬA: Hai thành phần giữ độc lập.
        @Cacheable(cacheNames = "tupleKeys", key = "T(java.util.List).of(#p0, #p1)")
        public String tuple(String tenant, String account) {
            return "tuple#" + tuple.incrementAndGet()
                    + "/" + tenant + "/" + account;
        }

        // SAI: Long 42L và String "42" thành cùng chuỗi.
        @Cacheable(cacheNames = "unsafeTyped", key = "'id:' + #p0")
        public String unsafeTyped(Object id) {
            return "badType#" + badType.incrementAndGet()
                    + "/" + id.getClass().getSimpleName();
        }

        // SỬA cho local ConcurrentMapCache: giữ kiểu key gốc.
        @Cacheable(cacheNames = "typedKeys", key = "#p0")
        public String typed(Object id) {
            return "typed#" + typed.incrementAndGet()
                    + "/" + id.getClass().getSimpleName();
        }

        public int unsafeCalls() { return bad.get(); }
        public int safeCalls() { return good.get(); }
        public int ambiguousCalls() { return ambiguous.get(); }
        public int tupleCalls() { return tuple.get(); }
        public int unsafeTypedCalls() { return badType.get(); }
        public int typedCalls() { return typed.get(); }

        public void reset() {
            bad.set(0);
            good.set(0);
            ambiguous.set(0);
            tuple.set(0);
            badType.set(0);
            typed.set(0);
        }
    }
}
~~~

**src/test/java/demo/keys/CacheKeyExpressionTest.java**:

~~~java
package demo.keys;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cache.CacheManager;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(CacheKeyConfig.class)
class CacheKeyExpressionTest {

    @Autowired
    CacheKeyConfig.QuoteService service;

    @Autowired
    CacheManager manager;

    @BeforeEach
    void beforeEach() {
        for (String name : List.of(
                "unsafeQuotes", "safeQuotes", "ambiguousKeys",
                "tupleKeys", "unsafeTyped", "typedKeys")) {
            assertNotNull(manager.getCache(name));
            manager.getCache(name).clear();
        }
        service.reset();
    }

    @Test
    void missingTenantAndCurrencyCollide() {
        String a = service.unsafeQuote("P01", "shop-A", "VND");
        String b = service.unsafeQuote("P01", "shop-B", "USD");

        // Test tái hiện lỗi cố ý: hai ngữ cảnh dùng cùng entry.
        assertEquals(a, b);
        assertEquals(1, service.unsafeCalls());
    }

    @Test
    void checksEachDimensionIndependently() {
        String baseline = service.safeQuote("P01", "shop-A", "VND");
        String skuChanged = service.safeQuote("P02", "shop-A", "VND");
        String tenantChanged = service.safeQuote("P01", "shop-B", "VND");
        String currencyChanged = service.safeQuote("P01", "shop-A", "USD");
        String repeated = service.safeQuote("P01", "shop-A", "VND");

        assertNotEquals(baseline, skuChanged);
        assertNotEquals(baseline, tenantChanged);
        assertNotEquals(baseline, currencyChanged);
        assertEquals(baseline, repeated);
        assertEquals(4, service.safeCalls());

        var cache = manager.getCache("safeQuotes");
        assertNotNull(cache.get(List.of("P01", "shop-A", "VND")));
        assertNotNull(cache.get(List.of("P01", "shop-B", "VND")));
        assertNotNull(cache.get(List.of("P01", "shop-A", "USD")));
    }

    @Test
    void delimiterCollisionAndStructuredKey() {
        String a = service.ambiguous("a:b", "c");
        String b = service.ambiguous("a", "b:c");
        assertEquals(a, b);
        assertEquals(1, service.ambiguousCalls());

        String x = service.tuple("a:b", "c");
        String y = service.tuple("a", "b:c");
        assertNotEquals(x, y);
        assertEquals(2, service.tupleCalls());
    }

    @Test
    void stringConversionErasesIdentifierType() {
        String a = service.unsafeTyped(42L);
        String b = service.unsafeTyped("42");
        assertEquals(a, b);
        assertEquals(1, service.unsafeTypedCalls());

        String x = service.typed(42L);
        String y = service.typed("42");
        assertNotEquals(x, y);
        assertEquals(2, service.typedCalls());

        var cache = manager.getCache("typedKeys");
        assertNotNull(cache.get(42L));
        assertNotNull(cache.get("42"));
    }
}
~~~

Chạy trong thư mục dự án bằng Gradle tương thích với JDK 17 (hoặc Gradle wrapper sẵn có của dự án):

~~~bash
gradle test
~~~

**Kết quả dự kiến:** JUnit chạy **4 test thành công**, không có assertion failure. Test đầu tiên và các trường hợp "bad" chủ động chứng minh biểu thức sai gây va chạm; chúng PASS khi lỗi được tái hiện đúng. Output chi tiết tùy phiên bản Gradle/môi trường, không có stdout cố định. Cấu trúc trên là project để người học tạo rồi chạy; các đoạn Java minh họa trước đó không phải chương trình độc lập.

Tại sao đây là kiểm thử gần hành vi thật? **@SpringJUnitConfig** tạo ApplicationContext; **@EnableCaching** bật interceptor; service được lấy từ Spring nên lời gọi đi qua proxy. **@BeforeEach** xóa entry và reset bộ đếm để các test độc lập nhau. **manager.getCache(...)** cho phép nhìn thấy kiểu key thật trong cache local. Bài này chưa thử Redis serializer/khóa vật lý của cluster production.

## 8. Null, object key, DTO và các lỗi đánh giá khác

| Biểu thức/đầu vào | Rủi ro cần thử |
| --- | --- |
| **#p0.id** với p0 null | Truy cập property gây lỗi |
| **#p0?.id** | Có thể tạo null key, cần quy định từ chối/bỏ cache |
| **T(java.util.List).of(#p0, #p1)** với null | **List.of** ném **NullPointerException** |
| **#p0.toString()** | Null hoặc DTO mutable biểu diễn thiếu ổn định |
| **#p0.total + #p1** | Cộng số, nối chuỗi hoặc chuyển kiểu theo toán hạng |
| **#p0.field** khi DTO có nhiều field quyết định output | Bỏ sót field có thể gộp kết quả |
| Object dùng **equals/hashCode** không phù hợp | Khóa tương đương bị tách, hoặc khóa khác bị gộp |
| Array/collection mutable | Key đổi nghĩa sau khi đã được lưu |
| **BigDecimal("1.0")** và **BigDecimal("1.00")** | Khác nhau theo equals; chỉ chuẩn hóa nếu nghiệp vụ cho phép |

Nếu null là đầu vào hợp lệ, hãy định nghĩa một kiểu key/policy hỗ trợ null một cách tường minh hoặc dùng **condition** để không cache những lời gọi đó. Đừng mặc định chuyển null thành chuỗi **"null"**, vì nó có thể trùng với giá trị literal. Nếu kết quả phụ thuộc tenant/user, ngoài key còn cần thực hiện kiểm tra quyền đọc ở đúng vị trí.

## 9. Kiểm thử đối xứng @Cacheable, @CachePut và @CacheEvict

Đọc đúng key nhưng cập nhật/xóa sai key vẫn tạo dữ liệu stale. Ví dụ trong service có repository:

~~~java
@Cacheable(
    cacheNames = "quotes",
    key = "T(java.util.List).of(#p0, #p1, #p2)"
)
public Quote quote(String sku, String tenant, String currency) {
    return repository.quote(sku, tenant, currency);
}

@CacheEvict(
    cacheNames = "quotes",
    key = "T(java.util.List).of(#p0, #p1, #p2)"
)
public void changePrice(
        String sku, String tenant, String currency, long newPrice) {
    repository.changePrice(sku, tenant, currency, newPrice);
}
~~~

Method ghi có **bốn tham số**, trong khi key đọc chỉ gồm ba. Nếu bỏ **key** tại **@CacheEvict**, mặc định nó tạo khóa có cả **newPrice** nên không xóa entry đã đọc. Test nên đi theo luồng: đọc để tạo cache → cập nhật DB → gọi method ghi qua Spring → đọc lại → xác minh kết quả mới và các entry khác không bị ảnh hưởng. Với **@CachePut**, kiểm tra method trả giá trị cuối cùng thực sự cần lưu và dùng cùng quy tắc key đọc.

Đừng chỉ đổi TTL để chữa key sai: cùng một entry vừa tạo vẫn có thể trả sai. Nếu có transaction, việc eviction/update xảy ra trước hay sau commit cũng cần test để tránh race nạp lại dữ liệu chưa commit.

## 10. Ma trận kiểm thử cần duy trì

| Nhóm | Ca kiểm thử | Điều kiện đạt |
| --- | --- | --- |
| Hit đúng | Cùng bộ tham số nghiệp vụ hai lần | Method chỉ chạy một lần |
| Đổi từng chiều | SKU/tenant/currency/locale/variant | Key khác khi output có thể khác |
| Tham số log | Thay traceId/correlationId | Không phát sinh entry mới khi không ảnh hưởng kết quả |
| Separator | Dấu :, /, chuỗi rỗng, Unicode | Không nhập nhằng giữa hai bộ tham số |
| Kiểu | Long/String, Integer/Long, BigDecimal scale | Phân biệt theo quy tắc nghiệp vụ |
| Null | Null tại object/property và phần tử tuple | Bỏ cache hoặc xử lý theo policy rõ ràng |
| DTO | Hai value object tương đương, object mutable | Identity đúng và ổn định |
| Chéo method | Hai method cùng cache name/key | Chỉ dùng chung entry nếu cùng ý nghĩa |
| Eviction/put | Đọc → cập nhật → đọc | Entry đúng được thay/xóa |
| Provider | Chạy thêm với Redis/Caffeine production-like | Serializer/prefix/key vật lý phù hợp |
| Proxy | Gọi qua bean, thử self-invocation | Biết khi nào annotation thực sự chạy |

Có thể dùng **parameterized test** và **property-based test** để bao phủ thêm các tuple; vẫn phải cố ý xây dựng trường hợp đối chứng đổi từng chiều. Không suy ra từ vài bộ input rằng biểu thức không bao giờ trùng: test đi cùng lập luận về cách biểu diễn key.

## 11. Cách xử lý khi test key thất bại

1. Ghi **cache name, method, tham số, kiểu runtime, SpEL expression** và output đúng cần nhận.
2. Kiểm tra method thật sự đi qua Spring proxy; không nhầm việc gọi trực tiếp với cache hit/miss.
3. Quan sát key thực tế trong cache; xác định lỗi do thiếu dimension, delimiter, kiểu, null, equality, namespace hay serializer.
4. Sửa expression/KeyGenerator hoặc tách cache name khi hai kiểu dữ liệu không nên chia sẻ cache.
5. Đồng bộ **@CacheEvict/@CachePut**; nếu đổi format key trong Redis/shared cache đang vận hành, kiểm tra key cũ còn tồn tại và kế hoạch rollout.
6. Chạy lại các test từng chiều, hit đúng, null/type, cross-method, concurrency và provider thực tế.

## 12. Câu hỏi tự kiểm tra

1. Vì sao test thay đồng thời tenant và currency chưa chứng minh key chứa cả hai?
2. Khi nào **#p0** đủ dùng, khi nào bắt buộc xét thêm **#p1/#p2**?
3. Vì sao **("a:b", "c")** và **("a", "b:c")** nguy hiểm nếu nối chuỗi bằng dấu hai chấm?
4. Vì sao **42L** và **"42"** có thể tách ở cache local nhưng trùng sau **'id:' + #p0**?
5. Khi input nullable, tại sao **T(java.util.List).of(...)** cần chính sách khác?
6. Vì sao test SpEL parser riêng không thay thế integration test Spring?
7. Nếu method ghi có thêm **newPrice**, vì sao **@CacheEvict** không thể dùng default key như method đọc?
8. Khi chuyển từ ConcurrentMapCache sang Redis, cần kiểm tra gì về key converter và cache prefix?

Nguyên tắc xuyên suốt: **chỉ các lời gọi thật sự được phép chia sẻ kết quả mới nên có cùng cache name + key**. Thiết kế biểu thức từ hợp đồng dữ liệu, test từng thành phần riêng, xác minh kiểu/key thực tế, và giữ cùng quy tắc trên đường đọc, ghi và xóa.

### Tài liệu tham khảo

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — @Cacheable, SpEL và key generation: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Spring AOP proxy: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — SimpleKeyGenerator API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/SimpleKeyGenerator.html
- Spring Data Redis — Redis Cache: https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html
