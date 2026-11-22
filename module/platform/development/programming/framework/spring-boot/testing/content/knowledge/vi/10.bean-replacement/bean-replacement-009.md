# Bean bị mock và ảnh hưởng đến proxy transaction, cache hoặc security trong Spring Boot Test

## 1. Vấn đề: test xanh nhưng hành vi AOP chưa được kiểm chứng

Trong Spring Boot, nhiều hành vi quan trọng không nằm trực tiếp trong thân phương thức service. Spring có thể gắn **advice** quanh lời gọi tới một bean thông qua **AOP proxy** để thực hiện transaction, cache hoặc kiểm tra quyền:

- `@Transactional`: bắt đầu/tham gia transaction, commit hoặc rollback theo cấu hình.
- `@Cacheable`, `@CacheEvict`, `@CachePut`: truy cập, ghi hoặc xóa cache theo chính sách.
- `@PreAuthorize`, `@PostAuthorize`: kiểm tra quyền tại ranh giới phương thức khi method security được bật.

Khi **thay chính bean service bằng Mockito mock**, test có thể chỉ nhìn thấy kết quả được `when(...).thenReturn(...)` lập trình sẵn thay vì logic thật. Điều nguy hiểm là một test như vậy vẫn xanh nhưng **không chứng minh** có transaction, cache hoạt động hay kiểm soát quyền như production.

Đặc biệt, không nên khẳng định một quy tắc tuyệt đối rằng “mock bean thì chắc chắn không còn proxy”. Tùy loại bean, annotation, advisor, thời điểm tạo proxy, cơ chế bean override và phiên bản Spring, mock có thể được đưa qua một proxy hoặc không. **Sự tồn tại của proxy cũng chưa chứng minh advice cụ thể đã thực thi.** Cần chọn đúng ranh giới test và xác minh **hành vi quan sát được**, không đoán từ tên annotation.

Mục tiêu bài học là hiểu **bean nào được thay thế**, **lời gọi có đi qua proxy không**, **điều gì bị mock bỏ qua** và **nên viết assertion thế nào** để tránh kết luận quá mức.

## 2. Ba tầng cần phân biệt: đối tượng, bean và proxy

Một luồng gọi service có AOP thông thường được hình dung như sau:

```text
Controller hoặc test gọi bean Spring
               |
               v
        [AOP proxy nếu có]
          |      |      |
          |      |      +-- Method-security advice
          |      +--------- Cache advice
          +---------------- Transaction advice
               |
               v
       [Đối tượng đích thật]
               |
               v
       Repository / HTTP client
```

Sơ đồ chỉ minh họa **các khả năng interceptor**; không có bảo đảm cả ba đều tồn tại, cũng không áp đặt một thứ tự advice cụ thể. Thứ tự thực tế do cấu hình advisor quyết định và có thể ảnh hưởng kết quả.

Ba khái niệm khác nhau:

1. **Đối tượng đích (target):** ví dụ `OrderService` chứa code Java thật.
2. **Spring bean được inject:** object Spring quản lý; có thể chính target hoặc một proxy bao quanh target.
3. **Mockito mock:** object có hành vi do stub xác định, thường không thực hiện thân phương thức thật trừ khi cấu hình đặc biệt.

Nếu test dùng `new OrderService(mockRepository)`, ta kiểm chứng logic service nhưng **không đi qua Spring AOP proxy**. Nếu dùng `@Autowired OrderService` từ context với cấu hình AOP thích hợp, lời gọi có cơ hội đi qua proxy. Nếu thay `OrderService` bằng mock, test không còn mặc nhiên kiểm chứng thân phương thức thật, ngay cả khi context khởi động thành công.

**Nguyên tắc cốt lõi:** Muốn kiểm tra transaction/cache/security gắn trên **service**, hãy ưu tiên để **service là bean thật được Spring quản lý** và mock **phụ thuộc phía sau nó**. Muốn kiểm tra cách controller xử lý kết quả service, mock service là lựa chọn có thể phù hợp, nhưng đừng dùng bài test controller đó làm bằng chứng cho AOP của service.

## 3. @Mock, @MockitoBean, @MockitoSpyBean và các annotation cũ

| Công cụ | Bean trong Spring context có bị thay? | Khi nào hữu ích? | Giới hạn |
|---|---|---|---|
| `@Mock` của Mockito | **Không tự động** | Unit test thuần Java, truyền mock qua constructor | Không kiểm tra Spring DI/AOP |
| `@MockitoBean` của Spring TestContext | **Có**, thay bean bằng mock hoặc tạo mock bean theo cơ chế mặc định | Test context cần một dependency giả để cô lập service thật | Phần code của bean bị thay không tự chạy |
| `@MockitoSpyBean` | Bao/wrap bean hiện có thành spy | Cần một phần hành vi thật và theo dõi lời gọi | Kết hợp với AOP/cache có thể khó hiểu; phải kiểm soát stubbing và proxy |
| `@MockBean` của Spring Boot đời trước | Thay/tạo mock bean trong Boot test context | Dự án dùng phiên bản Boot cũ | Annotation đã bị đánh dấu deprecated ở các dòng Boot mới; kiểm tra phiên bản để chuyển sang cơ chế phù hợp |
| `@SpyBean` của Spring Boot đời trước | Tạo spy cho bean trong Boot test context | Dự án đời trước cần spy | Cũng cần xét AOP proxy và phiên bản |

`@MockitoBean` và `@MockitoSpyBean` được cung cấp trong Spring Framework **6.2 trở lên** ở package `org.springframework.test.context.bean.override.mockito`. Với Boot 3.4+ (dựa trên Spring Framework 6.2+) hoặc các dòng tương thích mới hơn, nên ưu tiên API này nếu đã có trong dependency. Không áp dụng nguyên xi import đó cho dự án Boot cũ chưa có Spring Framework 6.2.

Ví dụ mẫu:

```java
@MockitoBean
PaymentGateway paymentGateway;
```

Nếu test class được tích hợp Spring TestContext, dòng này thay hoặc tạo bean `PaymentGateway` bằng mock cho context test. Nó **không** thay mọi bean trong ứng dụng. Cơ chế tìm bean theo kiểu/tên có thể cần `@Qualifier` hoặc tên bean rõ ràng nếu có nhiều bean cùng kiểu; test phải xác nhận đang mock **đúng instance mà service được inject**.

Phân biệt thêm:
- `@InjectMocks` của Mockito giúp dựng đối tượng và điền mock trong unit test; nó không tạo một Spring application context với các proxy AOP.
- `@Autowired` của Spring lấy bean từ context. Khi test kiểm tra AOP, lời gọi qua bean được Spring inject là điểm khởi đầu thích hợp.
- `@MockitoSpyBean` đòi bean thật tương ứng có thể được wrap; không nên coi nó là cách tạo bean còn thiếu. Với proxy có stateful advice như cache, một lời gọi dùng để stub/verify spy có thể tương tác với advisor ngoài ý muốn.

## 4. Bảng ảnh hưởng theo từng cơ chế

| Hành vi muốn chứng minh | Nếu mock **service có annotation** | Nếu mock **repository/client phía sau service thật** | Test đáng tin hơn |
|---|---|---|---|
| `@Transactional` mở transaction và rollback đúng | Stub kết quả service không chứng minh interceptor hay rollback | Service thật có thể đi qua transaction proxy, nhưng mock repository không chứng minh dữ liệu DB commit/rollback | Test context có transaction manager; kiểm tra transaction tại ranh giới hoặc DB thật sau commit/rollback |
| `@Cacheable` có tránh gọi lại dependency không? | Stub service không chứng minh cache của code thật; proxy quanh mock (nếu có) có thể ảnh hưởng riêng | Service thật với cache advice và gateway mock cho phép đếm số lần gateway bị gọi | Gọi hai lần cùng key qua bean được inject; xác minh kết quả và số lần gọi gateway |
| `@CacheEvict` có xóa key thực không? | Không nên kết luận từ việc mock được gọi | Có thể test service thật với cache manager thật và dependency mock | Làm nóng cache → thực thi thao tác evict → đọc lại và xác minh dữ liệu mới |
| `@PreAuthorize` chặn truy cập trái phép? | Một `when(...)` xanh không chứng minh interceptor đã chạy | Service thật có method-security advisor; mock dependency vẫn cho phép xác minh không bị gọi khi bị từ chối | Gọi bean thật từ SecurityContext thiếu quyền và assert bị từ chối |
| HTTP security filter có chặn request không? | Mock service không tự nói lên filter còn hay mất | Tùy loại web test và filter chain đã nạp | Test `MockMvc`/HTTP có security filters thực và assert 401/403 |
| Nghiệp vụ trong service có đúng không? | Không chạy logic thực thì chưa kiểm chứng | Unit test hoặc Spring test với service thật và mock dependency | Assert output, error path và side effect nghiệp vụ |

**Không suy ra một test controller có `@MockitoBean OrderService` đã kiểm tra được `@Transactional`, `@Cacheable` và `@PreAuthorize` trên `OrderService`.** Test đó chỉ có thể chứng minh những hành vi của controller, request/response và các thành phần thực sự còn hoạt động trong context của nó.

## 5. Ví dụ chạy được Java 17+: giữ service thật, mock gateway để kiểm tra cache

### 5.1. Yêu cầu nghiệp vụ

Một service lấy đơn giá SKU qua gateway và cache kết quả theo SKU. Với cùng SKU và cache còn hiệu lực, **lời gọi thứ hai** phải trả kết quả giống lời gọi đầu mà **không gọi gateway thêm lần nữa**.

Để kiểm chứng, ta cần:
1. **Service thật** có phương thức `@Cacheable`.
2. **Cache infrastructure thật** do `@EnableCaching` bật trong Spring context.
3. **Gateway mock** để đếm số lần truy vấn bên ngoài.
4. Lời gọi đi qua **service bean do Spring inject**, không phải `new PriceService(...)`.

Ví dụ dùng **Spring Framework 6.2+**, Java 17+, JUnit Jupiter, Spring TestContext, Mockito và Spring caching modules. Trong Spring Boot tương thích, các dependency thường liên quan `spring-boot-starter-test` và `spring-boot-starter-cache`. Không cần database hay server HTTP.

### 5.2. Phụ thuộc cần giả lập

Tệp `src/main/java/com/example/testing/PriceGateway.java`:

```java
package com.example.testing;

public interface PriceGateway {
    int fetchUnitPrice(String sku);
}
```

### 5.3. Service thật được cache

Tệp `src/main/java/com/example/testing/PriceService.java`:

```java
package com.example.testing;

import org.springframework.cache.annotation.Cacheable;

public class PriceService {

    private final PriceGateway gateway;

    public PriceService(PriceGateway gateway) {
        this.gateway = gateway;
    }

    @Cacheable(cacheNames = "prices")
    public int getUnitPrice(String sku) {
        return gateway.fetchUnitPrice(sku);
    }
}
```

Class và phương thức `public`, không `final`, phù hợp cho kiểu proxy class-based phổ biến khi class không khai báo interface nghiệp vụ. Không tự `new PriceService` trong test muốn chứng minh cache advice; object tự tạo sẽ không được bean post-processor gắn proxy.

### 5.4. Test dùng @MockitoBean gateway, không mock PriceService

Tệp `src/test/java/com/example/testing/PriceServiceCachingTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringJUnitConfig(classes = PriceServiceCachingTest.TestConfig.class)
class PriceServiceCachingTest {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    static class TestConfig {

        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("prices");
        }

        @Bean
        PriceService priceService(PriceGateway gateway) {
            return new PriceService(gateway);
        }
    }

    @MockitoBean
    PriceGateway gateway;

    @Autowired
    PriceService priceService;

    @Test
    void secondCallWithSameSkuUsesCache() {
        when(gateway.fetchUnitPrice("SKU-1")).thenReturn(125_000);

        int first = priceService.getUnitPrice("SKU-1");
        int second = priceService.getUnitPrice("SKU-1");

        assertEquals(125_000, first);
        assertEquals(125_000, second);
        assertTrue(AopUtils.isAopProxy(priceService));
        verify(gateway, times(1)).fetchUnitPrice("SKU-1");
    }
}
```

**Giải thích bằng chứng:**

- `@SpringJUnitConfig` kết hợp `SpringExtension` và `@ContextConfiguration` cho JUnit Jupiter, nạp đúng cấu hình được chỉ định.
- `@EnableCaching` đăng ký cơ chế AOP caching; `ConcurrentMapCacheManager` cung cấp cache `prices` có thật trong test context.
- `@MockitoBean PriceGateway gateway` tạo/thay một gateway bean bằng mock, để service nhận mock tại constructor. **`PriceService` vẫn là instance thật** do factory method tạo và được container xử lý.
- `@Autowired PriceService` lấy bean được Spring cung cấp; `AopUtils.isAopProxy` xác nhận có proxy, nhưng **không tự chứng minh cache hit**.
- Hai lần gọi cùng SKU có output đúng; `verify(gateway, times(1))` mới là bằng chứng gateway được gọi **một lần**, nên lần thứ hai không truy vấn lại trong phạm vi test.
- Nếu test cố ý thay chính `PriceService` bằng mock và stub `getUnitPrice`, số `125_000` trả về là kết quả được lập trình, chưa phải bằng chứng cache của thân phương thức thật.

Đây là test **bảo vệ cache advice của service** trong context đã khai báo, chứ chưa kiểm thử Redis, TTL, eviction hoặc cache phân tán. Nếu production dùng Redis hay Caffeine với chính sách expiration khác, phải có integration test riêng cho cache provider đó.

### 5.5. Chạy lớp kiểm thử

Với Gradle wrapper (Linux/macOS):

```bash
./gradlew test --tests "com.example.testing.PriceServiceCachingTest"
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.testing.PriceServiceCachingTest"
```

Với Maven wrapper (Linux/macOS):

```bash
./mvnw -Dtest=PriceServiceCachingTest test
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=PriceServiceCachingTest test
```

Các lệnh giả định dự án đã có dependency và runner JUnit Jupiter tương thích (Gradle thường cần `useJUnitPlatform()`). Test không in stdout nghiệp vụ; báo cáo Gradle/Maven sẽ ghi kết quả. Không tuyên bố bài test **đã chạy trên dự án thật** nếu chưa thực thi chính các lệnh này.

## 6. Cache có trạng thái: tại sao spy hoặc mock nhầm chỗ có thể gây false positive?

Cache là advice **có trạng thái**: cùng một key, một lời gọi ở proxy có thể được trả về trực tiếp từ cache mà **không tới target**. Vì vậy:

- `@MockitoSpyBean` quấn bean thật có thể giúp theo dõi một số hành vi, nhưng khi một spy đã nằm sau cache proxy, `verify(spy)` chỉ thấy invocation thật sự tới spy; **cache hit có thể không chạm spy**.
- Trong một số bố trí proxy/spy, thao tác `when(spy.method())` có thể kích hoạt lời gọi thật hoặc bị advice xử lý trong lúc thiết lập stub. Với spy, ưu tiên cú pháp `doReturn(...).when(spy).method(...)` khi cần tránh chạy method thật ở thời điểm stubbing, nhưng cũng phải hiểu lời gọi qua proxy có thể bị cache/advice khác chặn.
- Nếu muốn kiểm tra cache **thật**, đừng chỉ assert `cacheManager.getCache("prices") != null` hoặc `AopUtils.isAopProxy(service)`. Hãy test **hành vi hai lần gọi/eviction**, kiểm soát trạng thái cache.
- Context có thể được **cache giữa các test**. `ConcurrentMapCacheManager` lưu entry theo vòng đời context, nên các test dùng cùng SKU và cùng context có thể ảnh hưởng nhau. Dùng dữ liệu riêng hoặc xóa cache có chủ đích trong setup; không dựa vào thứ tự chạy.
- Nếu cache chứa dữ liệu riêng cho từng người dùng nhưng key chỉ theo SKU hoặc ID không đủ, có nguy cơ rò dữ liệu giữa người dùng. Kiểm thử thay đổi `SecurityContext` với dữ liệu đã được cache từ người trước, thay vì chỉ kiểm tra request đầu tiên trên cache rỗng.

**Chú ý:** `@Cacheable` có thể bỏ qua toàn bộ việc chạy method body khi cache hit. Nếu method body chứa kiểm tra quyền thủ công, cache advice có thể khiến đường đi thực tế khác lần gọi đầu. Không coi một annotation security hoặc một dòng `if` ở target là bằng chứng bảo vệ mọi cache hit; cần hiểu thứ tự advisor và viết test theo nguy cơ thực tế.

## 7. Transaction: mock repository khác với mock service

Xét service có phương thức:

```java
@Transactional
public void createInvoice(Invoice invoice) {
    invoiceRepository.save(invoice);
}
```

Đây chỉ là **đoạn minh họa** bên trong class service đã có `invoiceRepository`, import `org.springframework.transaction.annotation.Transactional` và kiểu `Invoice`; nó không phải file độc lập.

Trong cách tổ chức Spring AOP proxy thông thường:

```text
Test/Controller
    |
    v
[Transaction proxy]
    |
    v
InvoiceService.createInvoice(...)  <- logic thật
    |
    v
InvoiceRepository                    <- có thể mock trong unit/context test
```

Ba phạm vi chứng minh khác nhau:

1. **Mock chính `InvoiceService`:** `verify(service).createInvoice(...)` chỉ xác nhận mock được gọi. Nếu service method bị stub, không tự chứng minh transaction interceptor đã chạy, repository được lưu hay rollback.
2. **Dùng service thật qua Spring proxy, mock `InvoiceRepository`:** có thể xác minh service tạo đúng entity, gọi `save` đúng lần và **quan sát transaction context** nếu trong test đã có transaction manager thật/cấu hình phù hợp. Tuy nhiên mock repository **không thể chứng minh commit/rollback dữ liệu trong DB**.
3. **Dùng service thật + repository thật + database test:** có thể kiểm chứng tác dụng của transaction đối với dữ liệu sau commit/rollback, constraint và SQL behavior. Đây là integration test; có thể dùng `@SpringBootTest`, `@DataJpaTest` hoặc Testcontainers tùy phạm vi.

Để bật annotation-driven transaction trong context thuần Spring thường cần `@EnableTransactionManagement` và `PlatformTransactionManager`/transaction manager phù hợp. Trong Boot, auto-configuration có thể cung cấp hạ tầng đó khi đủ dependency và cấu hình. **Có `@Transactional` trong mã chưa đồng nghĩa transaction đang chạy trong test.**

### 7.1. Có thể xác minh transaction active khi gọi mock repository

Trong một test **đã có service thật qua transaction proxy, transaction manager thật và một mock repository**, có thể ghi nhận trạng thái transaction ngay khi repository được gọi:

```java
when(invoiceRepository.save(any(Invoice.class)))
        .thenAnswer(invocation -> {
            assertTrue(
                    TransactionSynchronizationManager
                            .isActualTransactionActive());
            return invocation.getArgument(0);
        });
```

Đây là **đoạn minh họa**, yêu cầu imports Mockito/JUnit và `TransactionSynchronizationManager`, cùng các kiểu `Invoice`/`invoiceRepository` đã định nghĩa trong dự án. Không phải test hoàn chỉnh độc lập.

Giá trị `true` là bằng chứng có một transaction active **tại thời điểm mock được gọi**, không chứng minh riêng phương thức `createInvoice` đã tạo nó, cũng không chứng minh database đã commit. Nếu chính test method/class đã có `@Transactional`, transaction do test quản lý có thể làm phép kiểm tra này xanh ngay cả khi production service không mở boundary như mong đợi. Muốn kiểm chứng boundary của service, thiết kế test chạy ngoài transaction test-managed hoặc dùng cơ chế như `TestTransaction` để điều khiển thời điểm kết thúc test transaction một cách minh bạch.

### 7.2. Cách kiểm tra rollback thật

Khi yêu cầu là “ghi hai bảng hoặc rollback cả hai nếu bước sau lỗi”, unit test với mock repository chỉ đủ xác minh **quyết định gọi**, không xác minh atomicity. Một integration test đáng tin nên:
- Sử dụng database/test transaction manager đúng loại; khi lỗi phụ thuộc SQL dialect, dùng database gần production.
- Gọi phương thức **qua bean/proxy do Spring inject**, không tự `new` target.
- Khởi tạo dữ liệu sạch, tạo tình huống ngoại lệ, và **đọc lại trạng thái database** ở ranh giới transaction phù hợp.
- Phân biệt rollback do **test framework** với rollback do **service**. Nhiều Spring test có `@Transactional` trên test sẽ tự rollback sau test; điều đó có thể che khuất việc service commit sai.
- Xác nhận quy tắc rollback: mặc định Spring thường rollback với `RuntimeException`/`Error`, còn checked exception có thể cần quy tắc tùy chỉnh tùy cấu hình/phiên bản; `rollbackFor` và cấu hình hệ thống có thể thay đổi kết quả.

Không kết luận “transaction ổn” chỉ vì `verify(repository).save(...)` đạt hoặc test class có `@Transactional`.

## 8. Security: method-level authorization khác với HTTP filter

Spring Security có ít nhất hai ranh giới bảo vệ mà test cần phân biệt:

- **HTTP/request security:** `SecurityFilterChain` có thể xác thực/ủy quyền request trước khi controller được gọi. Test `MockMvc` phải chạy qua filters phù hợp nếu muốn chứng minh hành vi này.
- **Method security:** `@PreAuthorize`, `@PostAuthorize` được xử lý khi một phương thức Spring bean được gọi **qua cơ chế bảo vệ tương ứng**, điển hình Spring AOP proxy sau khi bật `@EnableMethodSecurity`.

Spring Boot starter security **không tự động bật method security** chỉ vì thư viện hiện diện; ứng dụng/test context cần cấu hình `@EnableMethodSecurity` hoặc cơ chế tương ứng. Một `@WebMvcTest` mock service vẫn có thể kiểm chứng filter ở tầng HTTP **nếu các filters cần thiết đang được nạp**, nhưng không tự chứng minh lời gọi vào **method-protected service thật** được bảo vệ.

Nếu mock chính bean service có `@PreAuthorize`, test có thể không chạy thân phương thức, còn advice gắn hay không phụ thuộc cấu hình proxy thực tế. Vì thế **không được suy ra** security bị tắt hoặc vẫn hoạt động chỉ từ `@MockitoBean` hay `@WithMockUser`; phải kiểm thử hành vi bị cho phép/từ chối.

## 9. Ví dụ Java 17+: test method security trên bean thật, mock gateway

Ví dụ này độc lập với test cache ở mục 5 nhưng tái sử dụng interface `PriceGateway`. Nó cần thêm `spring-security-config`, Spring Security method-security infrastructure và `spring-security-test` (thường cùng dependency Spring Security phù hợp trong một dự án Boot). Các class production và test đều dùng package `com.example.testing`.

### 9.1. Service thật có @PreAuthorize

Tệp `src/main/java/com/example/testing/SecuredPriceService.java`:

```java
package com.example.testing;

import org.springframework.security.access.prepost.PreAuthorize;

public class SecuredPriceService {
    private final PriceGateway gateway;

    public SecuredPriceService(PriceGateway gateway) {
        this.gateway = gateway;
    }

    @PreAuthorize("hasAuthority('PRICE_READ')")
    public int getPrice(String sku) {
        return gateway.fetchUnitPrice(sku);
    }
}
```

Tệp này cần `PriceGateway.java` ở mục 5 và dependency Spring Security. Bean method sẽ được Spring tạo từ cấu hình test. Annotation `@PreAuthorize` chỉ có hiệu lực khi method security đã được bật.

### 9.2. Test gọi Spring bean theo hai security context

Tệp `src/test/java/com/example/testing/SecuredPriceServiceTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@SpringJUnitConfig(classes = SecuredPriceServiceTest.TestConfig.class)
class SecuredPriceServiceTest {

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    static class TestConfig {
        @Bean
        SecuredPriceService securedPriceService(PriceGateway gateway) {
            return new SecuredPriceService(gateway);
        }
    }

    @MockitoBean
    PriceGateway gateway;

    @Autowired
    SecuredPriceService service;

    @Test
    @WithMockUser(authorities = "PRICE_READ")
    void callerWithAuthorityCanReadPrice() {
        when(gateway.fetchUnitPrice("SKU-1")).thenReturn(125_000);

        assertEquals(125_000, service.getPrice("SKU-1"));
        verify(gateway).fetchUnitPrice("SKU-1");
    }

    @Test
    @WithMockUser(authorities = "PRICE_WRITE")
    void callerWithoutAuthorityIsRejected() {
        assertThrows(AccessDeniedException.class,
                () -> service.getPrice("SKU-2"));
        verifyNoInteractions(gateway);
    }
}
```

Giải thích:

- `@EnableMethodSecurity` đăng ký method-security advisors trong test context.
- `SecuredPriceService` vẫn là **bean thật** do `@Bean` tạo, được Spring xử lý để áp dụng `@PreAuthorize`.
- `@MockitoBean` chỉ thay `PriceGateway`. Test được phép chứng minh service chạy code thật và kiểm tra quyền trước khi gọi gateway.
- `@WithMockUser(authorities = "PRICE_READ")` chuẩn bị `SecurityContext` cho test hợp lệ; test khác dùng quyền khác để xác minh bị từ chối.
- Khi không đủ quyền, `AccessDeniedException` (hoặc subtype tương ứng) được assert, và gateway **không được gọi**. Điều này tốt hơn chỉ kiểm tra một mock service ném exception do `thenThrow`.
- Ví dụ kiểm tra **method security** trong context tối thiểu; chưa kiểm tra HTTP status 401/403, filter chain, login flow, JWT hay role mapping thực tế của ứng dụng.

`@WithMockUser` không phải bằng chứng HTTP security filters đã chạy. Nó cung cấp authentication test cho `SecurityContext`; muốn test filter/request phải có bài test HTTP riêng, bảo đảm filters được áp dụng.

Nếu tích hợp nhiều proxy khác nhau, cần quan sát hành vi thực và kiểm tra advice order. Không giả định rằng cache hit, transaction hoặc method-security luôn chạy ở một thứ tự duy nhất trên mọi cấu hình.

### 9.3. Lệnh chạy

Gradle (Linux/macOS):

```bash
./gradlew test --tests "com.example.testing.SecuredPriceServiceTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.testing.SecuredPriceServiceTest"
```

Maven (Linux/macOS):

```bash
./mvnw -Dtest=SecuredPriceServiceTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=SecuredPriceServiceTest test
```

Bài test không in stdout riêng. Các ví dụ là mã có thể biên dịch/chạy trong dự án Java 17+ với dependency/cấu hình được nêu, nhưng không thay cho việc chạy chúng và kiểm tra báo cáo của dự án thật.

## 10. Proxy tồn tại chưa đồng nghĩa transaction, cache hoặc security đều hoạt động

Một số công cụ chẩn đoán thường dùng:

```java
boolean proxied = AopUtils.isAopProxy(service);
boolean jdkProxy = AopUtils.isJdkDynamicProxy(service);
boolean cglibProxy = AopUtils.isCglibProxy(service);
```

Đây là **đoạn minh họa trong test có import `org.springframework.aop.support.AopUtils` và biến `service`**. Kết quả cho biết object đang được inject có phải một AOP proxy theo cơ chế được nhận diện hay không, và một số đặc điểm của proxy. Chúng **không** chứng minh advice nào đã chạy hoặc bản ghi DB đã commit. Để tìm target class có thể dùng `AopUtils.getTargetClass(service)` trong bối cảnh cần chẩn đoán; không tự unproxy rồi gọi target để “test transaction”, vì có thể vô tình **bỏ qua interceptor** mà bạn đang muốn kiểm chứng.

Mockito có `Mockito.mockingDetails(object).isMock()` để hỏi object có phải mock được Mockito nhận diện hay không. Tuy nhiên, nếu bean được inject là **proxy ngoài bao quanh một mock**, câu trả lời đối với proxy không nhất thiết giống câu trả lời với target. Đừng dùng một phép kiểm tra kiểu object để kết luận đầy đủ về composition của AOP.

### 10.1. Self-invocation: lời gọi nội bộ có thể đi vòng proxy

Trong Spring AOP proxy mode, **lời gọi từ object vào chính method khác của cùng object** thường không đi qua proxy. Ví dụ:

```java
public void outer() {
    inner(); // Lời gọi trong cùng target object
}

@Transactional
public void inner() {
    // ...
}
```

Đây là **đoạn minh họa trong một class**, không phải file độc lập. Nếu `outer()` không có transaction sẵn, gọi `inner()` qua `this` theo proxy mode thông thường không tự kích hoạt transaction advice đặt trên `inner()`. Nguyên tắc tương tự đáng lưu ý cho `@Cacheable` và nhiều method-security proxy. Mock không phải nguyên nhân duy nhất khiến advice không được chạy: **đường gọi** cũng quyết định.

Cách thường chọn là tách phương thức cần interceptor ra một bean riêng và gọi qua bean đó, hoặc thiết kế transaction/security boundary tại public service method được gọi từ bên ngoài; nếu dùng AspectJ weaving thay proxy, cơ chế có thể khác. Không lạm dụng self-injection chỉ để vòng lại proxy mà không hiểu vòng đời/circular dependencies.

### 10.2. Interface proxy, class proxy và final methods

- **JDK dynamic proxy** thường dùng khi làm proxy theo interface; code có thể phải inject/gọi qua interface đã được expose.
- **Class-based proxy** sử dụng subclassing (thường là CGLIB); lớp/phương thức `final` không thể bị override để advice theo cơ chế subclass proxy thông thường.
- Method không nằm trong điểm cắt của advisor, sai visibility hoặc không được gọi qua proxy có thể không nhận advice như mong muốn.
- Có `@Transactional` hoặc `@PreAuthorize` trong source là metadata; còn cần hạ tầng tương ứng được bật và lời gọi hợp lệ mới có hành vi.

Với Spring Boot, cách chọn proxy có thể bị ảnh hưởng bởi cấu hình chung và các auto-proxy creator trong context. Không khẳng định mọi dự án mặc định giống nhau về loại proxy.

## 11. Khi vừa có transaction, cache và security trên cùng service

Khi một phương thức áp dụng nhiều cơ chế, **thứ tự advice và cache key** có thể có tác động đáng kể:

1. **Security trước hay sau cache?** Nếu kết quả cache có thể được trả trước khi advice kiểm tra quyền của lời gọi, một kết quả cũ có thể tạo rủi ro lộ dữ liệu. Cần xác định advisor order và test các request có quyền khác nhau trên cache **đã được làm nóng**.
2. **Cache key có phân biệt người dùng/tenant không?** `@Cacheable(key = "#id")` có thể thiếu principal/tenant nếu nội dung trả về phụ thuộc người gọi; cần thiết kế key và quyền truy cập đúng hợp đồng.
3. **Eviction và transaction có đồng bộ không?** Nếu cache bị xóa/ghi trước khi transaction thất bại và rollback, dữ liệu trong cache có thể lệch database. Cần xem cơ chế transaction-aware cache và thứ tự commit/evict theo cấu hình thực.
4. **Method security là trước hay sau lời gọi?** `@PreAuthorize` kiểm tra trước; `@PostAuthorize` kiểm tra sau khi method trả về, khác về tác động phụ có thể đã xảy ra. Không dùng `@PostAuthorize` như thể nó luôn chặn việc ghi DB trước khi gọi.
5. **Mock tại tầng nào?** Mock cả service làm mất cơ sở kiểm chứng logic thật; mock repository/gateway thường giữ service và các advisor cần kiểm tra ở đường đi thật, nhưng không thay thế integration test của DB/Redis/HTTP.

Một ma trận test gợi ý:

| Ca | Trạng thái | Điều muốn xác minh |
|---|---|---|
| Gọi lần đầu với user có quyền, cache rỗng | Cache miss | Trả kết quả đúng, gateway được gọi |
| Gọi lại cùng key và cùng quyền | Cache hit | Trả đúng, gateway không gọi thêm |
| Gọi cùng key sau khi cache đã ấm nhưng user thiếu quyền | Khác SecurityContext | Bị từ chối theo hợp đồng, không lộ dữ liệu |
| Thay đổi dữ liệu rồi evict | Cache có dữ liệu cũ | Lần đọc sau lấy dữ liệu mới |
| Ghi DB thất bại giữa transaction | Exception/rollback | Không có bản ghi commit dở; cache không giữ trạng thái sai |
| Gọi service qua bean từ context | Proxy boundary | Advisor được kích hoạt theo hành vi quan sát được |
| Gọi method nội bộ qua `this` | Self-invocation | Nhận diện trường hợp advice không được áp dụng nếu chỉ dùng proxy |

Không nhất thiết một test phải làm tất cả. Nên tách bài test cache, method security, transaction integration và HTTP security để lỗi dễ chẩn đoán.

## 12. Lỗi thường gặp khi thay bean trong Spring Boot Test

| Sai lầm | Vì sao nguy hiểm | Cách khắc phục |
|---|---|---|
| `@MockitoBean` ngay trên service `@Transactional` rồi tuyên bố rollback đúng | Logic thật và DB chưa được kiểm chứng | Dùng service thật + DB test, xác minh trạng thái sau rollback |
| Mock service `@Cacheable` rồi chỉ assert giá trị stub | Stub có thể trả giá trị mà không chạy logic thật | Mock gateway, giữ service/cache advice thật, kiểm tra hai lần gọi |
| `@WithMockUser` + mock service rồi tuyên bố method security đã chặn | Test không chứng minh method-security advice của service thật | Dùng service thật và `@EnableMethodSecurity`, assert cả ca được phép và bị từ chối |
| Nghĩ `@Mock` tự thay bean Spring | Service có thể nhận bean khác | Dùng `@MockitoBean` đúng type/name trong test context khi cần override |
| Cho rằng proxy tồn tại nghĩa là đủ ba advice | Proxy có thể chỉ phục vụ một cơ chế | Kiểm tra hành vi và advisor config cần thiết |
| Gọi service bằng `new` khi test AOP | Bỏ qua Spring proxy | `@Autowired` bean từ context |
| `@Cacheable` test không dọn cache state | Test phụ thuộc thứ tự | Tách dữ liệu/cache key hoặc clear cache có chủ đích |
| Dùng spy rồi `when(spy.method())` tùy tiện | Có thể chạy method thật hoặc tương tác advice | Cân nhắc `doReturn`; hiểu proxy/spy; tránh spy nếu không cần |
| Dựa trên `verify(repository.save())` để khẳng định commit | Mock không tạo transaction thật | Thêm integration test kiểm tra dữ liệu sau ranh giới transaction |
| Test `@Transactional` tự rollback rồi tưởng service rollback | Test framework có thể tự rollback | Xác minh transaction/service boundary ngoài rollback của test |
| Quên `@EnableMethodSecurity` | `@PreAuthorize` có thể không được kích hoạt | Khai báo/cấu hình method security đúng context |
| Tắt Security filters trong MockMvc nhưng báo 403/401 đã được test | Filter chain thực bị bỏ khỏi đường đi | Bật filters cần thiết và assert HTTP đúng tầng |
| Bỏ qua self-invocation hoặc final method | Advisor có thể không chặn lời gọi | Đặt ranh giới ở method/bean phù hợp và kiểm tra proxy |
| Dùng bean override sai tên khi có nhiều implementation | Mock không đúng dependency hoặc context lỗi | Xác định name/qualifier và cấu hình override chính xác |

## 13. Chiến lược kiểm thử theo rủi ro thực tế

Một bộ test hợp lý thường có các tầng bổ sung nhau:

**Tầng 1 – unit test thuần Java:** Tạo service thật với repository/gateway mock qua constructor; kiểm tra công thức, validation, branch và interaction. Tầng này **không** kiểm tra AOP, nên không cần Spring context.

**Tầng 2 – context test nhỏ:** Dùng `@SpringJUnitConfig`/`@ContextConfiguration` với cache/security/transaction infrastructure đúng phần đang kiểm tra. Mock phụ thuộc bằng `@MockitoBean`, giữ bean chính thật; xác minh hành vi proxy. Phù hợp khi câu hỏi là “Spring đã nối advisor đúng và nó ảnh hưởng thế nào?”

**Tầng 3 – integration test có hạ tầng thật:** Dùng `@SpringBootTest`, `@DataJpaTest`, Testcontainers, Redis test instance hoặc lựa chọn tương ứng để xác minh DB commit/rollback, cache provider, serialization, transaction boundaries và cấu hình Boot. Không giả định H2 luôn tương đương PostgreSQL.

**Tầng 4 – web/API security test:** Dùng `MockMvc` hoặc HTTP client với `SecurityFilterChain` thật và các dependency cần thiết để chứng minh status 401/403/200, filter và method security trên đường đi người dùng. Mock service có thể chấp nhận được nếu mục tiêu chỉ là controller, nhưng phải có test khác cho bảo vệ ở tầng service nếu đó là hợp đồng.

**Review assertion:** Kết quả xanh phải mô tả **điều được kiểm tra** chứ không mô tả điều bạn hy vọng đã xảy ra. Ví dụ “service thật qua cache proxy chỉ gọi gateway một lần cho hai lượt truy vấn cùng SKU” mạnh và chính xác hơn “mock cache đã hoạt động hoàn toàn giống production”.

## 14. Checklist khi một bean bị mock trong test có AOP

- [ ] Đã xác định bean **nào** bị mock/spy, và bean nào vẫn chạy implementation thật.
- [ ] Đã kiểm tra version Spring/Boot và annotation override phù hợp (`@MockitoBean` hoặc API tương ứng).
- [ ] `@Autowired` nhận đúng bean/qualifier; mock không vô tình thay nhầm dependency.
- [ ] Đã xác định bài test kiểm tra **logic service, AOP advisor, DB thật, cache provider hay HTTP security**.
- [ ] Nếu kiểm tra AOP, lời gọi đi qua bean/proxy do Spring quản lý thay vì object tạo bởi `new`.
- [ ] Transaction: có manager thật và test commit/rollback ở ranh giới có ý nghĩa; không nhầm rollback test với service.
- [ ] Cache: đã kiểm tra cache miss/hit/evict bằng kết quả và số lần gọi, quản lý trạng thái cache giữa các ca.
- [ ] Security: đã bật `@EnableMethodSecurity` khi cần, kiểm tra both allowed/denied và đúng SecurityContext; nếu kiểm tra web phải dùng filters phù hợp.
- [ ] Đã cân nhắc advisor order, self-invocation, proxy type, final method và trường hợp cache chứa dữ liệu theo user/tenant.
- [ ] Không lấy `AopUtils.isAopProxy`, `Mockito.mockingDetails` hay một mock `thenReturn` làm bằng chứng duy nhất.
- [ ] Đã chạy đúng test và xem báo cáo Gradle/Maven/CI trước khi tuyên bố đạt trên hệ thống thật.

## 15. Tài liệu tham khảo chính thức

- Spring Framework – [`@MockitoBean` và `@MockitoSpyBean`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): cơ chế thay thế/wrap bean trong Spring TestContext.
- Spring Framework – [Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): transaction interceptor và AOP proxy.
- Spring Framework – [Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy mode, method visibility và self-invocation.
- Spring Security – [Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize` và advisor.

**Kết luận:** Khi thay bean bằng mock trong Spring Boot test, **đường đi qua proxy và phạm vi bị thay thế** quyết định test thực sự kiểm chứng được gì. Nếu cần chứng minh transaction, cache hoặc method security ở service, hãy ưu tiên **service thật được Spring inject, dependency phía sau được mock**, bật đúng infrastructure và assert hành vi ở ranh giới liên quan. Test có mock service vẫn rất hữu ích để cô lập controller, nhưng không phải bằng chứng cho AOP của service. Để xác nhận DB commit/rollback, Redis cache hay HTTP security thực, cần thêm integration test với hạ tầng và cấu hình phù hợp.