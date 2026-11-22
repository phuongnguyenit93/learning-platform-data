# Singleton bean, mock dùng chung và trạng thái có thể thay đổi

## 1. Vì sao một test PASS riêng lẻ nhưng FAIL khi chạy cả suite?

Trong module **Spring Boot - testing**, nhóm **Cách ly và chạy song song**, một hiện tượng hay gặp là hai bài test đều PASS khi chạy riêng, nhưng khi chạy cùng nhau hoặc bật JUnit parallel thì đôi lúc FAIL. Nguyên nhân có thể không nằm trong assertion, mà nằm ở **đối tượng được dùng chung**:

- Spring bean mặc định ở scope **singleton**: cùng một `ApplicationContext` trả về cùng một bean instance cho mọi nơi inject bean đó.
- Spring TestContext **cache `ApplicationContext`** giữa các test classes có cấu hình tương đương, khiến nhiều tests có thể sử dụng cùng singleton instance.
- `@MockitoBean` thay một bean trong context bằng **Mockito mock**, nhưng mock là đối tượng nằm trong context; nếu nhiều tests dùng chung context, chúng có thể cùng stubbing, verifying hoặc reset **cùng mock**.
- Một `static Map`, cache, fake clock, singleton repository hoặc embedded service có thể tích lũy trạng thái giữa tests.
- JUnit có thể tạo **test class instance mới mỗi method** mà các Spring beans inject vào lại **vẫn là cùng singleton**.

Ví dụ lỗi:

~~~java
@Component
class UnsafeCounter {
    private int count;

    void increment() {
        count++; // Không atomic, tồn tại qua nhiều test methods.
    }

    int value() {
        return count;
    }
}
~~~

Đoạn trên là **phản ví dụ**, không thuộc project runnable phía dưới. Test A gọi `increment()` một lần và assert `value()==1`; test B cũng làm thế. Khi Spring context được tái sử dụng, test B có thể nhận kết quả 2. Nếu hai tests chạy đồng thời, `count++` còn có race condition và lost updates. Thêm `Thread.sleep` chỉ che hoặc khuếch đại lỗi, không sửa cơ chế đồng bộ.

Mục tiêu là **cách ly đúng theo cấp độ**:

1. **Test fixture riêng cho mỗi test** nếu đang test business logic thuần.
2. **Bean stateless** nếu service được chia sẻ.
3. **Mutable state có namespace riêng** theo test ID/tenant/cart và cơ chế thread-safe nếu singleton cần giữ state.
4. **Không chạy song song test phụ thuộc shared MockitoBean/DirtiesContext**, hoặc thiết kế lại để không cần shared mock.
5. Dùng `@ResourceLock`, `@Isolated`, dọn fixture, `@DirtiesContext` **đúng phạm vi**, chứ không áp dụng bừa để che dependency giữa tests.

Bài này có dự án **Java 17, Spring Boot 3.5.16, JUnit Jupiter, Mockito, AssertJ**, với 13 ca test trong năm lớp: pure unit mock riêng, Spring bean mock chạy cách ly, Spring singleton có state phân vùng chạy song song, kiểm thử atomic concurrency bằng latch, và ví dụ khóa tài nguyên static.

## 2. Những lớp phạm vi khác nhau dễ bị nhầm

| Phạm vi | Ai tạo / quản lý? | Có tự cách ly mỗi @Test? |
| --- | --- | --- |
| Local variable trong method | JVM trong mỗi call | Thường có |
| Test instance field, JUnit `PER_METHOD` | JUnit tạo instance test mới theo method | **Có đối với field**, không đối với object được inject |
| Test instance field, JUnit `PER_CLASS` | Một test instance cho cả lớp | **Không** |
| `static` field | JVM/classloader | Không; chia sẻ giữa instances/classes |
| Spring `@Singleton` bean | Một `ApplicationContext` | Không; dùng chung trong context |
| `@Prototype` bean | Spring tạo theo lần request từ container | Không tự biến injection vào singleton thành prototype per call |
| `@MockitoBean` | Spring test bean override trong context | Reset giữa method mặc định; **không phải mock riêng mỗi method** |
| Mockito `@Mock` trong test Jupiter | MockitoExtension/test instance | Thường riêng theo test invocation |
| Mockito `Mockito.mock(...)` trong method | Test method | Riêng nếu không chia sẻ reference |
| `ApplicationContext` cached | Spring TestContext `ContextCache` trong JVM | Có thể dùng chung nhiều test classes |
| H2 database in-memory với tên cố định | Datasource/JVM/connection | Không, nếu cùng DB URL |
| External broker / DB / Redis / filesystem | Infrastructure | Không, trừ khi tạo namespace/resource riêng |

Câu nói “JUnit tạo test instance mới cho mỗi test” là **đúng về default lifecycle**, nhưng không chứng minh Spring singleton, mock trong cached context, static Map hay database đã được reset. Khi test gặp race/flaky, hãy vẽ **đồ thị ownership của mọi mutable object**.

### Ví dụ một đồ thị tham chiếu

~~~text
JUnit Test A instance ───┐
                        ├─> cached Spring ApplicationContext
JUnit Test B instance ───┘           |
                                     +─> CheckoutService singleton
                                     |       |
                                     |       +─> PricingClient singleton/mock
                                     |
                                     +─> CartRegistry singleton
                                              |
                                              +─> mutable Map cartId -> total
~~~

Hai test instances khác nhau **không** làm hai `CartRegistry` khác nhau. Khi một test `clear()` toàn map trong `@BeforeEach`, nó đang sửa dữ liệu mà test khác có thể đang cần.

## 3. Spring singleton không nhất thiết gây race

Singleton chỉ có nghĩa một bean instance trong context. **Một singleton bất biến/stateless hoàn toàn có thể an toàn khi chạy song song.**

Ví dụ:

~~~java
@Service
public class TaxCalculator {
    public long addFixedTax(long cents) {
        return Math.addExact(cents, 100L);
    }
}
~~~

Đây là snippet minh họa, cần `@Service` import. Nó không giữ mutable per-request state. Cùng instance phục vụ nhiều threads sẽ không tạo cross-test data leakage do field nội bộ.

Ngược lại, một service giữ state theo request trong field:

~~~java
@Service
public class BadCheckoutService {
    private String currentCartId;

    public void setCurrentCartId(String cartId) {
        currentCartId = cartId;
    }

    public String currentCartId() {
        return currentCartId;
    }
}
~~~

là **phản ví dụ**. Hai requests/tests cùng dùng bean có thể ghi đè `currentCartId` của nhau. Thay `String` bằng `volatile String` chỉ làm visible giá trị mới, không tạo **request isolation**. Đúng hơn là truyền cart ID vào method và dùng request-local data hoặc storage có key phù hợp.

Nguyên tắc: **dịch vụ singleton nên stateless, hoặc state bên trong phải có concurrency semantics và scope rõ ràng.**

## 4. Ba kiểu lỗi khác nhau: race, leak và reset conflict

**State leak (tuần tự):** test A tạo state ở singleton, không cleanup; test B chạy sau và nhìn thấy state đó. Lỗi có thể tồn tại ngay cả khi tắt parallel.

**Data race (song song):** test A và B cùng thay đổi một `HashMap`/field thường mà không có synchronization; kết quả không xác định. Race có thể gây lost updates và stale reads, kể cả nếu ban đầu store trống.

**Shared mock conflict:** test A stubbing `when(gateway.price("pen")).thenReturn(100)`, test B đổi thành 200 hoặc Spring reset mock khi A chưa verify xong. Mỗi test có thể đúng khi chạy riêng nhưng verification bắt số lần gọi từ test khác, hoặc stub bị xóa giữa lúc test đang dùng.

~~~text
Test A                     Test B
  stub mock -> 100
                             stub same mock -> 200
  invoke checkout("pen")
                             verify(mock, times(1))...
  verify(mock, times(1))
                             @AfterEach resets shared mock
  -> stubbing/verify có thể ảnh hưởng nhau
~~~

Spring `@MockitoBean` mặc định reset mock sau mỗi test method, nhưng **reset theo từng test lifecycle không serializes toàn bộ tests**. Spring Framework documentation cảnh báo **không chạy parallel** các tests dùng `@MockitoBean` hoặc `@MockitoSpyBean` theo cách thông thường.

Ba lỗi cần **ba cách sửa khác nhau**; tăng timeout hoặc gọi `Mockito.reset` khắp nơi không giải quyết root cause.

## 5. ContextCache của Spring TestContext

Spring TestContext cache `ApplicationContext` để tránh khởi động lại Spring Boot nhiều lần. Cache chủ yếu dùng key từ cấu hình context: classes/locations/active profiles/test properties/context customizers và các thành phần liên quan. Bean overrides như `@MockitoBean` là context customizers nên có thể ảnh hưởng cache key.

Điều cần nhớ:

- Hai test classes có context configuration tương đương **có thể reuse cùng context** trong một JVM.
- Context cache là **static trong process**, không tự chia sẻ giữa nhiều Gradle forks/JVM processes.
- `@BeforeEach` chạy mỗi method nhưng không tự reset singleton beans.
- `@AfterEach` xóa dữ liệu của một test có thể gây lỗi nếu nó xóa **state đang dùng bởi test khác**.
- `@DirtiesContext` đánh dấu context dirty để framework loại và đóng context; có chi phí khởi động lại và gây rủi ro cho các tests đồng thời đang dùng context đó.
- `@MockitoBean` field name/qualifier có thể ảnh hưởng cache key. Dùng tên thống nhất khi thật sự muốn reuse cùng override configuration.
- Cấu hình test khác nhau có thể tạo **hai contexts**, nhưng cả hai vẫn có thể trỏ đến **cùng database, Redis, broker hoặc static field** ngoài context.

Context cache **không phải** lỗi; đó là tối ưu hóa rất hữu ích. Hãy viết test chịu được việc bean instance được reuse.

## 6. Mockito @Mock và Spring @MockitoBean: không giống nhau

| API | Nơi tồn tại | Tác dụng |
| --- | --- | --- |
| `@Mock` + `MockitoExtension` | Test instance/Mockito test lifecycle | Mock thuần, không tự thay Spring bean |
| `Mockito.mock(PricingClient.class)` | Theo nơi bạn tạo reference | Dễ tạo per-method fixture, không cần Spring |
| `@InjectMocks` | Test fixture của Mockito | Constructor/field injection vào object được tạo bởi Mockito; **không** thay bean trong context |
| `@MockitoBean` | Bean override trong Spring test context | Thay bean trong `ApplicationContext` để các Spring beans khác inject mock |
| `@MockitoSpyBean` | Wrap bean trong Spring context | Gọi real code ở phương thức không stub; thận trọng side effect và AOP |
| Spring Boot `@MockBean` | Legacy API, deprecated từ Boot 3.4 | Với Boot 3.5 ưu tiên `@MockitoBean` của Spring Framework |

`@MockitoBean` import:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
~~~

Spring Framework 6.2 `@MockitoBean` có `reset` default **AFTER**: tự reset stubbing/interactions sau mỗi test method. `@MockitoBean(enforceOverride = true)` yêu cầu **bean thật phải tồn tại** để thay; không âm thầm tạo một mock mới khi không có target. Mặc định không enforce thì bean không tồn tại có thể được tạo để thỏa dependency; điều này đôi khi che lỗi test setup.

**Không dùng `@Mock` trên một field rồi tưởng Spring `@Autowired CheckoutService` sẽ tự nhận mock.** Đó là hai DI containers/lifecycles khác nhau. Trong pure unit test, trực tiếp `new CheckoutService(mock, new CartRegistry())`; trong Spring integration test cần `@MockitoBean` hoặc test configuration phù hợp.

## 7. Mặc định reset AFTER có ý nghĩa và giới hạn gì?

Giả sử test:

~~~java
@MockitoBean
PricingClient pricingClient;
~~~

Sau test method, Spring TestContext reset mock theo `MockReset.AFTER`. Điều này làm **clear Mockito stubbing/interaction history** theo chính sách reset, nhưng:

1. Không tạo một bean instance mới cho từng method.
2. Không clear `CartRegistry` hay state của các singleton khác.
3. Không rollback database/Redis/queue state.
4. Không bảo đảm background async task đã hoàn tất.
5. Không an toàn cho **concurrent tests cùng dùng mock**, vì test A có thể reset khi B đang invoke/verify.
6. Không đảm bảo callback của một task đã được hủy trước khi reset.
7. Không giải quyết double invocation do endpoint hoặc scheduler đang chạy.

Nếu có nhu cầu `reset=MockReset.NONE` (ví dụ flow nhiều giai đoạn), bạn **phải tự quản lý** lịch sử mock/lifecycle và càng không nên trộn với parallel tests. `Mockito.clearInvocations(mock)` giữ stubbing còn `Mockito.reset(mock)` xóa cả stubbing/interactions; cả hai đều có thể phá test đang chạy nếu mock dùng chung.

**Lựa chọn ưu tiên:** nếu test business logic đơn thuần, dùng per-method Mockito mock với `MockitoExtension`. Nếu cần Spring wiring với `@MockitoBean`, **serial/exclude parallel** lớp test đó theo khuyến nghị chính thức.

## 8. Quy tắc thực tế cho @Isolated, @Execution và @ResourceLock

JUnit Jupiter có nhiều mức điều phối:

- **`@Execution(CONCURRENT)`**: cho phép tests chạy song song theo cấu hình engine.
- **`@Execution(SAME_THREAD)`**: giúp các tests trong class tuân execution mode same-thread; **không tự ngăn một class khác chạy đồng thời**.
- **`@Isolated`** trên test class: yêu cầu Jupiter chạy class đó không đồng thời với các Jupiter tests khác **trong cùng execution plan/engine**. Hữu ích cho class dùng `@MockitoBean`.
- **`@ResourceLock("shared-key", mode = READ_WRITE)`**: các tests **cùng khai báo lock key tương thích** sẽ được JUnit điều phối; JUnit lock gồm lifecycle `@BeforeEach`/`@AfterEach`.
- **`@DirtiesContext`**: làm context bị loại/recreate, *không phải khóa*; không nên dùng tùy tiện với parallel.
- **`@TestInstance(PER_CLASS)`**: chia sẻ một test instance, không phải synchronization.

Giới hạn quan trọng: `@Isolated` và `@ResourceLock` của JUnit **không khóa nhiều JVMs/CI shards/máy khác nhau**, và không tự await async background threads được spawn sau khi test method kết thúc. Với external Redis/DB/broker cần namespace riêng hoặc resource-level isolation ngoài JUnit.

Nếu có các test methods dùng chung static map và bạn muốn serial hóa chúng, **tất cả các test truy cập resource đó phải khai báo cùng `@ResourceLock`**. Một test quên khai báo có thể vẫn chạy đồng thời, kể cả khi các test khác khóa đúng.

## 9. Thiết kế demo: cùng singleton, tách state theo cart ID

Ví dụ dùng một `CheckoutService` singleton:

~~~text
Test / HTTP request (cartId=unique)
       |
       v
CheckoutService singleton (stateless)
       |
       +---- PricingClient singleton (hoặc @MockitoBean)
       |
       +---- CartRegistry singleton
                 |
                 +-- ConcurrentHashMap<cartId, totalCents>
~~~

`CheckoutService` không giữ `currentCartId` ở field; mọi method nhận `cartId` như argument. `CartRegistry` vẫn **có mutable state**, nhưng là `ConcurrentHashMap` và dùng atomic `compute` theo key. Mỗi test tạo ID riêng và chỉ cleanup ID của mình.

**Hai vấn đề tách biệt**:

- **Thread safety:** hai threads cùng thêm vào **cùng cart ID** không làm lost update.
- **Test isolation:** hai tests dùng **hai cart IDs khác nhau** không đọc/ghi/xóa state của nhau.

Thread-safe Map **không tự bảo đảm test isolation** nếu mọi test đều dùng ID `"test-cart"` và cùng gọi `clear()` toàn map.

## 10. Cấu trúc project và Gradle

Dự án mẫu:

~~~text
settings.gradle
build.gradle
src/main/java/com/example/isolation/
    IsolationDemoApplication.java
    PricingClient.java
    DefaultPricingClient.java
    CartRegistry.java
    CheckoutService.java
src/test/java/com/example/isolation/
    CheckoutPureUnitTest.java
    CheckoutSpringMockTest.java
    CheckoutSpringParallelTest.java
    CartRegistryConcurrencyTest.java
    StaticScratchLockTest.java
src/test/resources/
    junit-platform.properties
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'spring-singleton-isolation-demo'
~~~

**`build.gradle` (Java 17, Spring Boot 3.5.16):**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    // Giới hạn Gradle test JVM forks; KHÔNG vô hiệu hóa
    // concurrency bên trong JUnit Jupiter engine.
    maxParallelForks = 1
}
~~~

`spring-boot-starter-test` cung cấp JUnit Jupiter, Mockito, Mockito Jupiter extension, AssertJ và Spring TestContext. Không cần database, web server, Docker hoặc external network trong ứng dụng mẫu.

### Kích hoạt Jupiter parallel có giới hạn

**`src/test/resources/junit-platform.properties`:**

~~~properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=4
~~~

Các cấu hình này cho phép **bốn workers tương đối** trong cùng test JVM. `CheckoutSpringMockTest` sẽ dùng `@Isolated` để không cạnh tranh mock/context với các test khác trong cùng Jupiter engine; pure/concurrent tests chỉ dùng state riêng.

Đây là cấu hình **để học và chứng minh cách ly**, không phải khuyến nghị bật parallel toàn bộ suite production ngay lập tức. Với suite có `@MockitoBean`, `@DirtiesContext`, shared DB/broker, nên đánh giá và phân nhóm rõ. Mỗi test dùng mock bean cần được exclude khỏi parallel hoặc chạy ở execution plan riêng; `@Isolated` minh họa cách chặn đồng thời trong một engine.

## 11. Spring Boot application

**`src/main/java/com/example/isolation/IsolationDemoApplication.java`:**

~~~java
package com.example.isolation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IsolationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(IsolationDemoApplication.class, args);
    }
}
~~~

Các production components phía dưới đều nằm ở package `com.example.isolation` nên được `@SpringBootApplication` component scan.

Không thêm scheduler/background worker vào demo: bài muốn tập trung vào singleton/mocks và test parallel, không cần tạo một tác nhân bất đồng bộ thứ ba làm mơ hồ kết quả.

## 12. PricingClient và implementation mặc định

**`src/main/java/com/example/isolation/PricingClient.java`:**

~~~java
package com.example.isolation;

public interface PricingClient {
    long unitPriceCents(String sku);
}
~~~

**`src/main/java/com/example/isolation/DefaultPricingClient.java`:**

~~~java
package com.example.isolation;

import org.springframework.stereotype.Component;

@Component
public class DefaultPricingClient implements PricingClient {

    @Override
    public long unitPriceCents(String sku) {
        return switch (sku) {
            case "pen" -> 200L;
            case "book" -> 500L;
            case "eraser" -> 50L;
            default -> throw new IllegalArgumentException(
                    "Unknown sku: " + sku
            );
        };
    }
}
~~~

Bean này **stateless**, nên nhiều threads có thể gọi cùng instance mà không tạo dữ liệu dùng chung. Input `sku` bị null sẽ ném NullPointerException do `switch` trên null (Java 17); service sẽ validate đầu vào.

Trong `CheckoutSpringMockTest`, `@MockitoBean(enforceOverride=true)` thay **PricingClient bean** (chính là `DefaultPricingClient`) bằng Mockito mock. Trong `CheckoutSpringParallelTest`, Spring dùng production `DefaultPricingClient`, không có mock override.

Đây là một lý do dùng bean override thật trong integration test: pure Mockito `@Mock` **không** thay instance mà Spring đang inject vào `CheckoutService`.

## 13. CartRegistry: mutable nhưng có scope rõ và atomic update

**`src/main/java/com/example/isolation/CartRegistry.java`:**

~~~java
package com.example.isolation;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.stereotype.Component;

@Component
public class CartRegistry {

    private final ConcurrentMap<String, Long> totals =
            new ConcurrentHashMap<>();

    public long add(String cartId, long cents) {
        if (cartId == null || cartId.isBlank() || cents <= 0) {
            throw new IllegalArgumentException(
                    "Invalid cart or price"
            );
        }

        return totals.compute(
                cartId,
                (id, previous) -> Math.addExact(
                        previous == null ? 0L : previous,
                        cents
                )
        );
    }

    public long total(String cartId) {
        if (cartId == null || cartId.isBlank()) {
            throw new IllegalArgumentException(
                    "Invalid cart"
            );
        }
        return totals.getOrDefault(cartId, 0L);
    }

    public void remove(String cartId) {
        totals.remove(cartId);
    }
}
~~~

`ConcurrentHashMap.compute` tính toán và cập nhật **một key** atomically theo contract của ConcurrentHashMap. Nếu tám threads đồng thời gọi `add("shared", 1)` 50 lần mỗi thread, kết quả phải là **400**, không bị lost increments.

**Nhưng** `remove(cartId)` do một test gọi khi worker khác còn đang cập nhật cùng key vẫn có thể xóa state hợp lệ. Thread safety không đồng nghĩa đúng business sequencing. Trong suite, test chỉ dọn key **của mình sau khi task hoàn tất**.

`Math.addExact` phát hiện overflow thay vì im lặng wrap một `long`; với tiền thật, cần currency, ledger và DB atomicity. Store in-memory này **không bền qua restart** và không bảo vệ nhiều pods; đây là test model.

## 14. CheckoutService: singleton không lưu cart ID vào field

**`src/main/java/com/example/isolation/CheckoutService.java`:**

~~~java
package com.example.isolation;

import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final PricingClient prices;
    private final CartRegistry carts;

    public CheckoutService(
            PricingClient prices,
            CartRegistry carts
    ) {
        this.prices = Objects.requireNonNull(prices, "prices");
        this.carts = Objects.requireNonNull(carts, "carts");
    }

    public long addItem(String cartId, String sku) {
        if (cartId == null || cartId.isBlank()
                || sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                    "Invalid item request"
            );
        }

        long cents = prices.unitPriceCents(sku);
        if (cents <= 0) {
            throw new IllegalArgumentException(
                    "Non-positive item price"
            );
        }
        return carts.add(cartId, cents);
    }

    public long total(String cartId) {
        return carts.total(cartId);
    }
}
~~~

`CheckoutService` **không có mutable field** theo request, chỉ giữ reference đến collaborators. Nó là singleton an toàn về *riêng state field của service*, nhưng collaborator `CartRegistry` là mutable. Test vẫn cần isolation theo `cartId`.

Đây là một **add operation có side effect**: gọi `addItem("A","pen")` hai lần sẽ cộng 400, không tự idempotent. Nếu operation đi qua HTTP/queue có thể được retry, cần thêm business idempotency key và persistent unique constraint/ledger, ngoài phạm vi test isolation của bài này.

## 15. Pure unit tests: mỗi method có mock và store riêng

**`src/test/java/com/example/isolation/CheckoutPureUnitTest.java`:**

~~~java
package com.example.isolation;

import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CheckoutPureUnitTest {

    @Mock
    PricingClient pricingClient;

    private CheckoutService checkout;
    private CartRegistry carts;
    private String cartId;

    @BeforeEach
    void setUp() {
        carts = new CartRegistry();
        checkout = new CheckoutService(pricingClient, carts);
        cartId = "unit-" + UUID.randomUUID();
    }

    @Test
    void unitMockAndStoreAreFreshForEachMethod() {
        when(pricingClient.unitPriceCents("pen"))
                .thenReturn(100L);

        assertThat(checkout.addItem(cartId, "pen"))
                .isEqualTo(100L);
        assertThat(carts.total(cartId))
                .isEqualTo(100L);
        verify(pricingClient).unitPriceCents("pen");
    }

    @Test
    void separateSkuPricesAccumulateWithinOneFixture() {
        when(pricingClient.unitPriceCents("book"))
                .thenReturn(300L);
        when(pricingClient.unitPriceCents("pen"))
                .thenReturn(50L);

        checkout.addItem(cartId, "book");
        checkout.addItem(cartId, "pen");

        assertThat(carts.total(cartId))
                .isEqualTo(350L);
        verify(pricingClient).unitPriceCents("book");
        verify(pricingClient).unitPriceCents("pen");
    }

    @Test
    void invalidPriceDoesNotMutateLocalStore() {
        when(pricingClient.unitPriceCents("pen"))
                .thenReturn(0L);

        assertThatThrownBy(
                () -> checkout.addItem(cartId, "pen")
        ).isInstanceOf(IllegalArgumentException.class)
         .hasMessageContaining("Non-positive item price");

        assertThat(carts.total(cartId)).isZero();
    }
}
~~~

**Ba tests** dùng `@Mock` từ MockitoExtension, tạo `new CartRegistry()` và `new CheckoutService(...)` ở `@BeforeEach`. JUnit default lifecycle là `PER_METHOD`, nên mỗi test có instance/fixtures riêng. Các tests có thể chạy song song mà không chạm một shared Spring context.

**Không dùng `@SpringBootTest` cho unit test business đơn thuần.** Mỗi test chỉ cần behavior của `CheckoutService` và `CartRegistry`; startup context tốn chi phí và đưa thêm cơ hội state leak.

Nếu muốn dùng `@InjectMocks`, có thể để Mockito tạo `CheckoutService`, nhưng phải bảo đảm cách tiêm `CartRegistry` và mock rõ ràng; constructor injection trực tiếp trong ví dụ giúp dependency graph dễ kiểm hơn.

## 16. Spring mock bean test: dùng @Isolated để tránh overlap

**`src/test/java/com/example/isolation/CheckoutSpringMockTest.java`:**

~~~java
package com.example.isolation;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.junit.jupiter.api.parallel.Isolated;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@Isolated
@Execution(ExecutionMode.SAME_THREAD)
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class CheckoutSpringMockTest {

    @Autowired
    CheckoutService checkout;

    @Autowired
    CartRegistry carts;

    @Autowired
    ApplicationContext context;

    @MockitoBean(enforceOverride = true)
    PricingClient pricingClient;

    private String cartId;

    @BeforeEach
    void createOwnCartId() {
        cartId = "mock-" + UUID.randomUUID();
    }

    @AfterEach
    void cleanOwnCartOnly() {
        carts.remove(cartId);
    }

    @Test
    void springMockReplacesOnlyPricingDependency() {
        when(pricingClient.unitPriceCents("pen"))
                .thenReturn(350L);

        assertThat(context.getBean(PricingClient.class))
                .isSameAs(pricingClient);
        assertThat(checkout.addItem(cartId, "pen"))
                .isEqualTo(350L);
        verify(pricingClient).unitPriceCents("pen");
    }

    @Test
    void differentStubIsSetIndependentlyForEachTest() {
        when(pricingClient.unitPriceCents("book"))
                .thenReturn(700L);

        assertThat(checkout.addItem(cartId, "book"))
                .isEqualTo(700L);
        assertThat(carts.total(cartId))
                .isEqualTo(700L);
        verify(pricingClient).unitPriceCents("book");
    }

    @Test
    void invalidMockPriceDoesNotMutateSharedRegistry() {
        when(pricingClient.unitPriceCents("pen"))
                .thenReturn(0L);

        assertThatThrownBy(
                () -> checkout.addItem(cartId, "pen")
        ).isInstanceOf(IllegalArgumentException.class);

        assertThat(carts.total(cartId)).isZero();
        verify(pricingClient).unitPriceCents("pen");
    }
}
~~~

**Ba tests** kiểm đúng Spring wiring với một bean override. Mỗi test có own cart ID và dọn cart riêng; Spring context/mock **vẫn có thể được reuse** nên đây không phải ba `PricingClient` mocks khác nhau.

Vì bật Jupiter parallel ở project level, class này gắn **`@Isolated`** để không chạy cùng các Jupiter tests khác trong cùng execution plan. `@Execution(SAME_THREAD)` mô tả thêm việc không chạy song song giữa các methods của class. Đây là biện pháp có chủ đích cho một test dùng mock bean chung, không phải cách làm bắt buộc cho mọi Spring test.

**Giới hạn:** `@Isolated` không ngăn một tiến trình Gradle fork khác, Maven fork khác hoặc CI shard khác truy cập external resource giống nhau. `@MockitoBean` reset AFTER vẫn cần mọi công việc bất đồng bộ của test hoàn tất trước khi method teardown xảy ra.

### Vì sao không dùng Mockito.reset ở @BeforeEach?

Spring test mock mặc định được reset sau test method. Reset thủ công trước test có thể che lifecycle issue và — quan trọng hơn — **phá concurrent test** nếu mock đang được chia sẻ. Với class được cách ly, mỗi method chỉ khai báo stubbing nó cần, verification chỉ cho call chính nó, và không dùng order-dependent behavior.

## 17. Spring integration tests song song: singleton mutable nhưng partition theo ID

**`src/test/java/com/example/isolation/CheckoutSpringParallelTest.java`:**

~~~java
package com.example.isolation;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@Execution(ExecutionMode.CONCURRENT)
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class CheckoutSpringParallelTest {

    @Autowired
    CheckoutService checkout;

    @Autowired
    CartRegistry carts;

    private String cartId;

    @BeforeEach
    void createOwnCart() {
        cartId = "parallel-" + UUID.randomUUID();
    }

    @AfterEach
    void cleanOnlyOwnCart() {
        carts.remove(cartId);
    }

    @Test
    void penIsAddedToUniqueCart() {
        assertThat(checkout.addItem(cartId, "pen"))
                .isEqualTo(200L);
        assertThat(checkout.total(cartId))
                .isEqualTo(200L);
    }

    @Test
    void bookIsAddedToUniqueCart() {
        assertThat(checkout.addItem(cartId, "book"))
                .isEqualTo(500L);
        assertThat(checkout.total(cartId))
                .isEqualTo(500L);
    }

    @Test
    void twoUniqueCartsNeverShareTotals() {
        String second = "parallel-extra-" + UUID.randomUUID();

        try {
            assertThat(checkout.addItem(cartId, "pen"))
                    .isEqualTo(200L);
            assertThat(checkout.addItem(second, "book"))
                    .isEqualTo(500L);

            assertThat(carts.total(cartId)).isEqualTo(200L);
            assertThat(carts.total(second)).isEqualTo(500L);
        } finally {
            carts.remove(second);
        }
    }
}
~~~

**Ba tests** có thể chạy song song trong cùng Spring context. Chúng dùng production `DefaultPricingClient` (stateless) và cùng singleton `CartRegistry`, nhưng từng method có unique cart ID/cleanup riêng. Không test nào gọi `carts.clearAll()`.

Điều kiện để an toàn:

- `CartRegistry.add` dùng atomic `compute`, không HashMap thường.
- ID không được hard-code giống nhau giữa methods.
- `@AfterEach` chỉ xóa ID do test tạo.
- Không có background task còn dùng ID sau cleanup.
- Test fields thuộc per-method test instance, không phải `@TestInstance(PER_CLASS)`.
- Test không sửa global properties, default locale/time zone hoặc DB bảng chung mà không có isolation.

**Một shared singleton có thể an toàn dưới parallel testing**, nếu ownership/concurrency semantics của state được chứng minh. Đừng mặc định mọi singleton cần `@DirtiesContext`.

## 18. Concurrent unit test: chứng minh update cùng key không lost increment

**`src/test/java/com/example/isolation/CartRegistryConcurrencyTest.java`:**

~~~java
package com.example.isolation;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import static org.assertj.core.api.Assertions.assertThat;

@Execution(ExecutionMode.CONCURRENT)
class CartRegistryConcurrencyTest {

    @Test
    void concurrentAddsToSameCartUseAtomicCompute()
            throws Exception {
        CartRegistry carts = new CartRegistry();
        ExecutorService pool =
                Executors.newFixedThreadPool(8);
        CountDownLatch ready = new CountDownLatch(8);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Void>> tasks = new ArrayList<>();

        try {
            for (int t = 0; t < 8; t++) {
                tasks.add(pool.submit(() -> {
                    ready.countDown();
                    if (!start.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "Start gate timeout"
                        );
                    }
                    for (int i = 0; i < 50; i++) {
                        carts.add("shared-cart", 1L);
                    }
                    return null;
                }));
            }

            assertThat(
                    ready.await(5, TimeUnit.SECONDS)
            ).isTrue();

            start.countDown();
            for (Future<Void> task : tasks) {
                task.get(5, TimeUnit.SECONDS);
            }

            assertThat(carts.total("shared-cart"))
                    .isEqualTo(400L);
        } finally {
            start.countDown();
            pool.shutdownNow();
            assertThat(
                    pool.awaitTermination(5, TimeUnit.SECONDS)
            ).isTrue();
        }
    }

    @Test
    void independentCartsCanUpdateConcurrently()
            throws Exception {
        CartRegistry carts = new CartRegistry();
        ExecutorService pool =
                Executors.newFixedThreadPool(4);
        List<String> ids = new ArrayList<>();
        List<Future<?>> tasks = new ArrayList<>();

        try {
            for (int i = 0; i < 4; i++) {
                String id = "cart-" + UUID.randomUUID();
                ids.add(id);
                tasks.add(pool.submit(() -> {
                    for (int k = 0; k < 100; k++) {
                        carts.add(id, 2L);
                    }
                }));
            }

            for (Future<?> task : tasks) {
                task.get(5, TimeUnit.SECONDS);
            }
            for (String id : ids) {
                assertThat(carts.total(id))
                        .isEqualTo(200L);
            }
        } finally {
            pool.shutdownNow();
            assertThat(
                    pool.awaitTermination(5, TimeUnit.SECONDS)
            ).isTrue();
        }
    }
}
~~~

Hai tests này **không khởi động Spring**, không có mock/shared context. `CartRegistry` tạo **local trong mỗi method**. Test thứ nhất dùng `CountDownLatch` để ép tám workers cùng tới điểm bắt đầu, thay vì dùng `Thread.sleep` để “hy vọng” chúng cạnh tranh. `Future.get(timeout)` bảo đảm worker hoàn tất trước assert.

Nếu đổi `ConcurrentHashMap.compute` thành:

~~~java
// PHẢN VÍ DỤ: read-modify-write không atomic.
long old = totals.getOrDefault(cartId, 0L);
totals.put(cartId, old + cents);
~~~

thì test concurrency có thể phát hiện lost increments. Lưu ý test concurrency **không phải một chứng minh hình thức** về mọi possible thread interleaving; nó tạo một bài regression có giá trị. Với biến đổi quan trọng hơn, cần stress/linearizability testing và kiểm trên hệ production-like.

## 19. JUnit @ResourceLock cho một static mutable resource

Đôi khi legacy test vẫn phải đọc/ghi shared static cache mà chưa thể refactor ngay. JUnit `@ResourceLock` cho phép serialize những test có chung **lock key**.

**`src/test/java/com/example/isolation/StaticScratchLockTest.java`:**

~~~java
package com.example.isolation;

import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;

import static org.assertj.core.api.Assertions.assertThat;

@Execution(ExecutionMode.CONCURRENT)
class StaticScratchLockTest {

    private static final Map<String, Integer> SCRATCH =
            new HashMap<>();

    @Test
    @ResourceLock(
            value = "legacy-static-scratch",
            mode = ResourceAccessMode.READ_WRITE
    )
    void firstWriterUsesJunitResourceLock() {
        SCRATCH.clear();
        SCRATCH.put("count", 1);
        assertThat(SCRATCH.get("count")).isEqualTo(1);
    }

    @Test
    @ResourceLock(
            value = "legacy-static-scratch",
            mode = ResourceAccessMode.READ_WRITE
    )
    void secondWriterUsesTheSameJunitResourceLock() {
        SCRATCH.clear();
        SCRATCH.put("count", 2);
        assertThat(SCRATCH.get("count")).isEqualTo(2);
    }
}
~~~

Hai tests khai báo cùng lock key và WRITE mode. Trong cùng JUnit Jupiter execution plan, scheduler không chạy chúng đồng thời ở vùng lifecycle đã khóa.

**Đây là mitigation cho legacy state, không phải kiến trúc mặc định.** Nếu một test ở class khác dùng `SCRATCH` nhưng quên `@ResourceLock("legacy-static-scratch")`, lock không bảo vệ nó. Nếu hai Gradle test JVMs độc lập cùng sửa một file/Redis, JUnit lock cũng không phối hợp qua processes. Refactor về per-test fixtures/namespace vẫn tốt hơn.

## 20. @TestInstance(PER_CLASS) và @TestMethodOrder không phải isolation

JUnit Jupiter mặc định `@TestInstance(PER_METHOD)`: mỗi test method có một test instance mới. Nếu dùng:

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@Execution(ExecutionMode.CONCURRENT)
class UnsafeSharedFixtureTest {
    private int total;

    @Test
    void one() {
        total++;
    }

    @Test
    void two() {
        total++;
    }
}
~~~

Đây là **phản ví dụ**, không nằm trong project runnable. Hai methods có thể cập nhật cùng `total` và tạo race. Với `PER_CLASS`, JUnit thường có quy tắc execution mode mặc định bảo thủ hơn nếu không có `@Execution(CONCURRENT)`, nhưng đừng dựa vào đó như synchronization cho state bên ngoài.

Tương tự, `@TestMethodOrder` chỉ định thứ tự trong một số trường hợp; **không bảo đảm test độc lập**. Test B phụ thuộc “A phải chạy trước rồi set singleton state” là thiết kế khó duy trì. Thay vào đó mỗi test setup đầy đủ dữ liệu mình cần.

Một test method có thể dùng `@BeforeEach` tạo local fixture riêng **dù test class PER_CLASS**, nhưng test fields bị chia sẻ vẫn cần synchronization; không nên đánh đổi độ dễ hiểu nếu không có lợi ích cụ thể.

## 21. @DirtiesContext: chỉ dùng khi context thật sự cần thay mới

`@DirtiesContext` buộc Spring loại context khỏi cache và đóng nó theo mode được khai báo. Ví dụ:

~~~java
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD
)
@SpringBootTest
class ExpensiveIsolatedIntegrationTest {
    // Mỗi test method làm dirty context và context được tải lại.
}
~~~

Đây là snippet minh họa, không thuộc project runnable. Nó có thể hữu ích khi test thực sự thay đổi **bean definitions/configuration/context-managed lifecycle** không thể cleanup; nhưng bất lợi:

- Khởi động context lại chậm, tăng CPU/RAM của CI.
- Test khác có thể đang dùng context cached và bất ngờ bị đóng.
- Không rollback/reset external database/broker/Redis bên ngoài context.
- Không xóa static fields ngoài Spring.
- **Spring Framework khuyến nghị không chạy parallel tests dùng `@DirtiesContext`**.

Nếu vấn đề chỉ là một key trong `CartRegistry`, `carts.remove(myCartId)` rõ và rẻ hơn nhiều. Nếu vấn đề là shared mock, `@DirtiesContext` không thay thế cách ly lịch chạy/cấu hình; Spring test mock vốn có reset lifecycle.

## 22. Mock reset và async background tasks

Đây là failure case khó:

~~~text
Test method:
   stub shared @MockitoBean
   submit async worker
   return ngay

Spring teardown:
   reset @MockitoBean

Async worker:
   gọi mock sau khi reset
   -> thấy default Mockito response
   -> ghi state sai / exception
~~~

Nếu test có `@Async`, Kafka consumer, scheduled task, web request hoặc `CompletableFuture`, hãy **await business completion** trước khi verify/reset/cleanup. Dùng:

- `CompletableFuture.get(timeout)` cho task gắn Future.
- Awaitility `untilAsserted` cho committed DB status.
- `CountDownLatch.await(timeout)` nếu cần explicit signal đúng thời điểm.
- Shutdown/cancel executor do test **tự tạo** trong `finally`.
- Không shutdown Spring-managed shared executor trong mỗi test method.

Nếu không kiểm soát lifecycle của background thread, tốt hơn dùng **fake collaborator riêng** hoặc serialized integration test, tránh shared MockitoBean. Mock reset tự động **không chờ task bất đồng bộ**.

Mockito `verify(mock, timeout(...))` chỉ chứng minh invocation đã xảy ra, không chứng minh database commit hoặc side effect của worker đã hoàn tất. Khi contract là business state, await state đó.

## 23. AOP proxy và @MockitoBean: thay bean có thể thay cả hành vi

Một điểm dễ bỏ sót trong Spring: một service thật có thể được bọc bởi AOP proxy để cung cấp `@Transactional`, `@Cacheable`, method security hay `@Retryable`. Khi `@MockitoBean` **thay bean**, instance override là mock, không phải **real bean được AOP proxy như cũ**; test interaction với mock **không** chứng minh annotation-driven effects của original service.

Ví dụ test:

~~~java
@MockitoBean
PaymentService paymentService;

// Mockito verify(paymentService).charge(...)
// KHÔNG chứng minh @Transactional trên real PaymentService đã chạy.
~~~

Đây là snippet, `PaymentService` là tên ví dụ. Nếu mục tiêu là kiểm transaction/retry/cache behavior, **không mock chính component sở hữu annotation đó**. Hãy dùng service thật và mock một **external gateway** bên dưới, hoặc dùng integration test với database/client stub thật.

`@MockitoSpyBean` là lựa chọn khác nhưng spy method có thể gọi real code, cần `doReturn(...).when(spy)...` khi stubbing có side effect, và phải hiểu Spring AOP proxy target. Không tự coi spy là cách “khắc phục mọi thứ” — nó cũng là override nằm trong test context và không nên chạy parallel vô kiểm soát.

## 24. Khi singleton có state, tránh global clear

Một pattern rất dễ gây race:

~~~java
@BeforeEach
void reset() {
    cache.clear(); // Xóa toàn cache dùng bởi test khác!
}
~~~

Trong một suite parallel, test A có thể đang dùng cache key `A` thì test B gọi `clear()` và làm mất dữ liệu. Nếu namespace test độc lập, ưu tiên:

~~~java
@BeforeEach
void setup() {
    cartId = "test-" + UUID.randomUUID();
}

@AfterEach
void cleanup() {
    carts.remove(cartId);
}
~~~

Hai snippets là ví dụ ý tưởng, được thực thi trong các integration tests hoàn chỉnh phía trên. Nếu test tạo nhiều keys, lưu danh sách keys do test sở hữu và xóa **chỉ các keys đó**. Không xóa resource của test khác. Với DB có thể dùng unique schema/container per test class hoặc tenant/transaction ID; với Kafka dùng topic/group/consumer ID riêng.

**Không đủ khi external operation chưa xong:** nếu background worker còn chạy, nó có thể ghi lại row sau cleanup. Phải await/cancel tasks trước, rồi dọn.

## 25. Khi có database, @Transactional trong test không rollback mọi thread

Spring `@Transactional` trên JUnit test method tạo **test-managed transaction** gắn với test thread. Một request qua embedded HTTP server, `@Async` worker, scheduler hoặc Kafka consumer có thể chạy **thread/transaction khác** và commit DB riêng.

Ví dụ test có `@Transactional`:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class IncorrectAssumptionTest {
    // Test thread rollback không đương nhiên rollback
    // DB writes của HTTP server thread.
}
~~~

Đây là snippet minh họa, không thuộc project runnable. Nếu method gọi HTTP endpoint và server ghi DB, test rollback có thể không xóa dữ liệu đã commit ở server thread. Khi tests chạy song song, dữ liệu có thể leak vào các method/classes khác.

Giải pháp:

1. Tạo unique business IDs cho mỗi method.
2. Query/await committed state đúng transaction/isolation.
3. Explicit cleanup sau khi background processing hoàn tất.
4. Nếu dùng Testcontainers, cô lập schema/container đúng cấp cần thiết.
5. Không phụ thuộc test thread rollback để dọn external resources.

`@Sql` và `@DirtiesContext` cũng không tự làm sạch Kafka topics, object storage hoặc HTTP provider. Phải có ownership/lifecycle plan cho từng tài nguyên.

## 26. Context cache key và field name của @MockitoBean

Spring Framework 6.2 cho phép `@MockitoBean` suy ra bean theo **field type** và dùng `@Qualifier`/field name để phân biệt khi cần. Tên field có thể là **fallback qualifier** và ảnh hưởng context cache key.

Ví dụ hai test classes cùng muốn mock một `PricingClient` nhưng một field đặt `pricingClient`, còn class kia đặt `service`:

~~~java
@MockitoBean
PricingClient pricingClient;
~~~

~~~java
@MockitoBean
PricingClient service;
~~~

Đây là hai snippets, không thuộc demo hoàn chỉnh. Tùy context/qualifier, Spring có thể tạo **hai context cache entries** không cần thiết. Nếu thật sự test cùng override configuration, đặt field names nhất quán hoặc khai báo explicit qualifier/name phù hợp.

Điều ngược lại cũng cần nhớ: **reusing context không có nghĩa mock instance riêng** cho từng class. Cùng context có thể làm test A/B chia sẻ mock, dù mỗi class có field riêng.

Nếu bean có nhiều candidates cùng type, `@MockitoBean` có thể fail vì ambiguous target. Đừng đặt @Primary ngẫu nhiên để giấu lỗi; dùng `@Qualifier` hoặc `@MockitoBean(name="...")`, và `enforceOverride=true` để phát hiện target không tồn tại.

## 27. @ResourceLock, @Isolated không giải quyết CI shards

Trong một Gradle `test` task, `maxParallelForks=1` giới hạn concurrent **Gradle forked test JVMs**. Tuy nhiên JUnit Jupiter vẫn có thể chạy multiple tests đồng thời **trong một JVM** theo `junit-platform.properties`. Tăng `maxParallelForks` lên 4 sẽ tạo thêm các JVMs và mỗi JVM có context cache riêng; test dùng cùng external PostgreSQL schema hoặc Kafka topic vẫn có thể tranh chấp.

Tương tự CI có thể chia jobs thành nhiều shards/machines. `@ResourceLock` và `@Isolated` của JUnit chỉ điều phối **bên trong cùng engine execution plan**. Chúng không phải distributed locks và không thay thế:

- Unique DB/schema/tenant IDs.
- Kafka topic/group names riêng mỗi test run.
- Filesystem temp dirs do `@TempDir` quản lý.
- Random network ports với lifecycle owner rõ.
- Redis key prefix riêng cho CI job/test invocation.
- Namespace per test run thay vì global truncate.
- Cleanup bảo đảm không chạm resource đang được test khác dùng.

**Chọn đúng cấp độ cách ly:** method-local cho unit tests, keyed shared singleton cho Spring integration, per-class container/schema khi bắt buộc, per-job external namespace cho CI shards.

## 28. Một ma trận để chọn chiến lược

| Test scenario | Được chạy parallel? | Chiến lược |
| --- | --- | --- |
| Pure unit test với mock và store mới per method | Có | `@Mock` + `MockitoExtension`, local fixtures |
| Spring service singleton **stateless** | Thường có | Không sửa global mutable state |
| Spring singleton có `ConcurrentHashMap` theo unique ID | Có nếu contract rõ | Per-test key, atomic updates, scoped cleanup |
| `@MockitoBean` trong cached context | **Không khuyến nghị** | `@Isolated`/serialized test group |
| `@MockitoSpyBean` trên service stateful | **Không khuyến nghị** | Serial + hiểu real method/AOP behavior |
| `@DirtiesContext` giữa test methods | Không khuyến nghị | Chạy riêng, dùng thật cần thiết |
| Shared `static HashMap` legacy | Chỉ khi phối hợp lock đúng | `@ResourceLock` hoặc refactor |
| Shared DB table, tests truncate toàn bảng | Không | Unique data/schema hoặc serial grouping |
| H2 cùng fixed DB URL | Có điều kiện | Unique IDs, DB transaction/cleanup đúng |
| Embedded Kafka topic/group chung | Có rủi ro | Unique topics/groups; lifecycle isolation |
| Spring `@Async` worker truy cập mock sau test | Không khi chưa join | Await completion trước mock reset |
| Tests sửa `System.setProperty`/default locale | Không an toàn khi không khóa | `@ResourceLock`/isolate hoặc tránh global mutation |

**Không phải càng nhiều `@DirtiesContext` hoặc `@Isolated` thì test càng tốt.** Mục tiêu là có thể chạy song song những test **thật sự độc lập**, đồng thời khóa hoặc tách riêng số ít test sử dụng global resource không thể tránh.

## 29. Chẩn đoán sự cố flakiness

| Triệu chứng | Nguyên nhân thường gặp | Bằng chứng nên thu |
| --- | --- | --- |
| PASS một mình, FAIL khi chạy suite | Singleton/static/database state leak | IDs, context reuse, teardown logs |
| Mockito `Wanted but not invoked` sau concurrent test | Another test reset/stub cùng mock | Mock identity, test schedule, after lifecycle |
| Mockito `TooManyActualInvocations` | Another test dùng chung mock, task background chưa xong | Interaction history, owner ID |
| Stubbing của test A biến mất | Spring `MockReset.AFTER` test B reset | Mock/context sharing, concurrency |
| Total lúc 2 lúc 1 | `count++` / HashMap non-atomic | Concurrent stress/latch |
| Cart của test A bị mất khi test B setup | Global `clear()` trong @BeforeEach | Cleanup scope |
| Bean state còn sau @BeforeEach | @BeforeEach không reset Spring singleton | Context cache and bean identity |
| `@DirtiesContext` gây "context no longer active" | Context bị đóng khi test khác dùng | Parallel Spring docs, cache eviction |
| Test @Transactional vẫn để lại DB rows | Server/async thread khác transaction | DB commit thread/connection |
| @MockitoBean mock vẫn tồn tại ở class khác | Context cache reused | Context cache key & bean override config |
| Mockito test không chạm bean của @Autowired service | Dùng @Mock thay vì @MockitoBean | DI wiring, mock identity |
| Spy stubbing chạy real code bất ngờ | `when(spy.method())` thực thi method | `doReturn` when spy phù hợp |
| Parallel tests đều dùng file ./tmp/output.json | Shared filesystem path | @TempDir, per-test directory |
| Test dùng same Kafka group/topic | Offsets và records shared | Unique groups/topics |
| Reset bean rồi async callback re-mutate | Worker chưa hoàn tất | Await worker, cleanup order |
| Tests đang chạy nhanh hơn nhưng không ổn định | Parallel enabled trên suite chưa cô lập | Classify/serialize risky tests |
| Tắt toàn bộ parallel “chữa xong” | Race bị che nhưng state leak còn | Chạy tuần tự nhiều thứ tự ngẫu nhiên |
| @TestInstance(PER_CLASS) thêm shared field | Một test instance mutable | Per-method lifecycle/local state |
| Different field names create extra contexts | @MockitoBean fallback qualifier ảnh hưởng cache key | Standardize field naming |
| Context cache thrashing, CI chậm | Quá nhiều unique overrides/dirty contexts | Cache stats, group configs |

Nếu cần debug context cache, Spring TestContext hỗ trợ logging ở `org.springframework.test.context.cache` với log level DEBUG. Không assert chính xác context count giữa mọi Gradle versions; đo để phát hiện cache miss/eviction bất thường.

## 30. Checklist review trước khi bật parallel

- [ ] Đã nhận diện các singleton beans có mutable fields/cache?
- [ ] Đã phân biệt singleton **stateless** với mutable state cần thread safety?
- [ ] Có `static` fields/shared test instance `PER_CLASS` nào có mutation?
- [ ] Mọi test dùng shared storage có unique ID/namespace?
- [ ] Cleanup chỉ xóa resource mà test sở hữu?
- [ ] Không có `clearAll()/TRUNCATE` ảnh hưởng test khác?
- [ ] Các background workers đã hoàn tất trước teardown/reset?
- [ ] `@MockitoBean` test có được serialize hoặc isolate khỏi parallel?
- [ ] Không dùng `Mockito.reset` thủ công lên mock đang chia sẻ với test khác?
- [ ] Mock default reset AFTER được hiểu là reset stubs/interactions, **không tạo bean mới**?
- [ ] Với pure service, dùng `@Mock` + fixture riêng thay vì @SpringBootTest?
- [ ] Với Spring wiring, mock đúng bean qua `@MockitoBean`/qualifier?
- [ ] Có kiểm `enforceOverride=true` khi muốn test target thật tồn tại?
- [ ] @MockitoBean field names/qualifiers nhất quán khi cần reuse context?
- [ ] Có test trên service thật nếu cần xác nhận `@Transactional`/`@Retryable`/`@Cacheable`?
- [ ] `@DirtiesContext` chỉ dùng khi cần, tránh parallel?
- [ ] `@ResourceLock` key được khai báo bởi **mọi test cùng dùng resource**?
- [ ] `@Isolated` không bị hiểu nhầm thành distributed lock?
- [ ] Gradle forks/CI shards không dùng chung resource mà không namespace?
- [ ] Database rollback scope có bao trùm background threads không?
- [ ] Spring test context cache và H2 URL/Redis/Kafka namespace đã được hiểu?
- [ ] Test concurrency có latch và bound timeouts, không Thread.sleep phỏng đoán?
- [ ] Mockito verification chỉ kiểm invocation, business invariants được assert riêng?
- [ ] Chạy suite nhiều lần/thứ tự khác nhau trước khi bật parallel rộng?
- [ ] Kết quả dự kiến được phân biệt với build/JUnit đã chạy thật?

## 31. Lệnh chạy và expected outcomes

Nếu có JDK 17+, Gradle Wrapper và dependencies:

~~~bash
./gradlew test --tests "com.example.isolation.CheckoutPureUnitTest"
./gradlew test --tests "com.example.isolation.CheckoutSpringMockTest"
./gradlew test --tests "com.example.isolation.CheckoutSpringParallelTest"
./gradlew test --tests "com.example.isolation.CartRegistryConcurrencyTest"
./gradlew test --tests "com.example.isolation.StaticScratchLockTest"
./gradlew test
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.isolation.CheckoutPureUnitTest"
.\gradlew.bat test --tests "com.example.isolation.CheckoutSpringMockTest"
.\gradlew.bat test --tests "com.example.isolation.CheckoutSpringParallelTest"
.\gradlew.bat test --tests "com.example.isolation.CartRegistryConcurrencyTest"
.\gradlew.bat test --tests "com.example.isolation.StaticScratchLockTest"
.\gradlew.bat test
~~~

**13 JUnit methods**: 3 pure unit; 3 Spring @MockitoBean isolated; 3 Spring parallel state-by-ID; 2 CartRegistry concurrency; 2 static scratch `@ResourceLock`.

| Nhóm | Expected |
| --- | --- |
| Pure unit Mockito | Stubs riêng mỗi test, totals 100/350, invalid price giữ 0 |
| Spring mock bean | @MockitoBean thay đúng PricingClient; totals 350/700, invalid giữ 0 |
| Spring parallel real beans | Pen 200, book 500, hai cart IDs không giao thoa |
| 8 worker tasks cùng một cart | 8 × 50 additions × 1 cent = **400 cents** |
| 4 worker tasks ở bốn carts | Mỗi cart 100 additions × 2 cents = **200 cents** |
| Static legacy lock | Hai methods dùng cùng ResourceLock key, expected 1/2 trong method của mình |

Đây là **kết quả suy ra từ source**, không phải output Gradle/JUnit đã quan sát. Mã mẫu **chưa được compile/run trong lúc biên soạn**, vì vậy cần thực thi trong project có đủ files/Gradle Wrapper để xác nhận thực tế. Không có `System.out.println` trong application code nên không có stdout cố định.

**Kết luận:** Đừng quy kết mọi flaky test cho “chạy song song quá nhanh”. Hãy kiểm tra **ownership của mutable state**: test instance mới không đồng nghĩa Spring singleton mới; mock trong cached context có thể được nhiều tests dùng chung, và reset AFTER không làm concurrent mocking an toàn. Dùng per-method mocks cho unit tests, singleton stateless hoặc state-by-key atomic + scoped cleanup cho parallel Spring tests, và serialize các test có `@MockitoBean`/`@DirtiesContext` hoặc global resources không thể tách. Cần kiểm cả data race, state leak và lifecycle của background tasks trước khi tin tưởng một suite chạy parallel.

### Tài liệu chính thức

- [Spring Framework 6.2 — TestContext Parallel Test Execution](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html)
- [Spring Framework 6.2 — @MockitoBean / @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html)
- [Spring Framework 6.2 — Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html)
- [Spring Framework 6.2 — Context Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html)
- [Spring Framework 6.2 — Dependency Injection for Test Fixtures](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/fixture-di.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — @MockBean Deprecated API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/mock/mockito/MockBean.html)
- [JUnit Jupiter 5.12 — Parallel Execution, @ResourceLock, @Isolated](https://docs.junit.org/5.12.0/user-guide/#writing-tests-parallel-execution)
- [JUnit Jupiter 5.12 — Test Instance Lifecycle](https://docs.junit.org/5.12.0/user-guide/#writing-tests-test-instance-lifecycle)
- [Mockito — MockitoExtension Javadoc](https://javadoc.io/doc/org.mockito/mockito-junit-jupiter/latest/org/mockito/junit/jupiter/MockitoExtension.html)
- [Java SE 17 — ConcurrentHashMap.compute](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)