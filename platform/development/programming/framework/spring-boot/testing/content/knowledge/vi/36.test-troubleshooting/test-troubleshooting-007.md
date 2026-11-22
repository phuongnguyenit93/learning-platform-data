# Mockito stubbing sai, mock không được dùng hoặc verify sai thời điểm

## 1. Vấn đề: test thất bại dù nghiệp vụ dường như đúng

Trong kiểm thử Java/Spring Boot, Mockito giúp thay những phụ thuộc bên ngoài bằng **test doubles**: repository, HTTP client, message sender, adapter thanh toán. Nhưng việc thiết lập mock sai có thể khiến test thất bại không phải vì code nghiệp vụ hỏng, mà vì **test setup, đối tượng đang được kiểm tra, tham số hoặc thời điểm verify không khớp**.

Các lỗi thường gặp:

- `UnnecessaryStubbingException`: đã `when(...).thenReturn(...)` nhưng nhánh thực thi không bao giờ dùng stub đó.
- `PotentialStubbingProblem`: code gọi một method với argument khác argument đã stub khi đang dùng strict stubbing.
- `Wanted but not invoked`: Mockito không ghi nhận tương tác được `verify(...)` yêu cầu.
- `TooManyActualInvocations` hoặc `NeverWantedButInvoked`: số lời gọi khác `times(1)` hoặc `never()` đã assert.
- `InvalidUseOfMatchersException`: trộn matcher và giá trị raw sai cách, hoặc dùng matcher ngoài lời gọi stubbing/verification.
- `NotAMockException`: truyền một object thật hoặc proxy khác vào `verify/reset/when` sai cú pháp.
- `WrongTypeOfReturnValue`: stub trả sai kiểu, hoặc spy bị gọi phương thức thật ngoài ý muốn.
- Stub đã khai báo trên **mock A**, nhưng `service` thật đang giữ **bean B**/một instance mới; verify A luôn thấy 0 invocations.
- `verify` chạy **trước khi** `CompletableFuture`, `@Async`, listener hoặc HTTP request hoàn tất.
- Một `@Spy` bị stub bằng `when(spy.method())` khiến method thật được gọi **ngay lúc stubbing**, gây I/O, thay đổi state hoặc exception.
- Mockito mặc định trả `null`, `false`, `0` hoặc empty default cho những method chưa stub; test có thể rẽ sang nhánh khác dự định.

Bài thuộc nhóm **Chẩn đoán lỗi kiểm thử**, đề mục chính **“Mockito stubbing sai, mock không được dùng hoặc verify sai thời điểm”**. Ví dụ sử dụng **Java 17+**, **Spring Boot 3.3.5**, **JUnit Jupiter** và Mockito 5 do Spring Boot dependency management cung cấp. Một phần test là unit test thuần Mockito; phần khác dùng `@SpringBootTest` và `@MockBean` đúng theo Spring Boot 3.3.

### Sau bài học, bạn có thể

1. Phân biệt **stubbing**, **invocation** và **verification**.
2. Đọc đúng nguyên nhân của `UnnecessaryStubbingException`, `PotentialStubbingProblem`, `WantedButNotInvoked` và `TooManyActualInvocations`.
3. Khai báo `@Mock`, `@ExtendWith(MockitoExtension.class)` và inject dependency thực sự dùng bởi subject under test.
4. Dùng `when(...).thenReturn(...)`, `thenThrow(...)` và `doThrow(...).when(...)` đúng loại method.
5. Dùng `any()`, `anyString()`, `eq()`, `isNull()` và `ArgumentCaptor` mà không làm lỏng contract.
6. Kiểm tra số lần gọi bằng `times`, `never`, `atLeastOnce` và thứ tự bằng `InOrder`.
7. Hiểu `STRICT_STUBS`, lựa chọn stub tối thiểu và lý do không bật `lenient` toàn suite.
8. Biết khi nào dùng `doReturn(...).when(spy)` để tránh gọi method thật lúc setup.
9. Phân biệt `@Mock`/`@InjectMocks` với `@MockBean` trong Spring `ApplicationContext`.
10. Verify async sau khi đợi **completion signal** có timeout; biết giới hạn của `Mockito.timeout(...)`/`after(...)`.
11. Kiểm tra mock thực sự thuộc đối tượng đang được test và chẩn đoán proxy, Spring context cache, reset.
12. Tạo một checklist xử lý lỗi dựa trên bằng chứng trước khi thay đổi expected assertions.

**Lưu ý phiên bản:** Spring Boot 3.3 sử dụng `org.springframework.boot.test.mock.mockito.MockBean`. `@MockitoBean` nằm trong Spring Framework 6.2 và được dùng trong các nhánh Spring Boot mới hơn, **không phải annotation thay thế tương ứng trong project Boot 3.3.5 này**.

## 2. Ba hành động khác nhau: stub, call, verify

```text
TEST SETUP                         CODE UNDER TEST                     ASSERTION
  @Mock InventoryClient
       |
  when(inventory.find("SKU-1"))
       .thenReturn(Optional.of(...))
       |                                 service.reserve("SKU-1", 2)
       |                                       |
       +--------- mock ghi nhận <-------------+-- inventory.find("SKU-1")
                                                 |
                                            service tính toán
                                                 |
                                               repo.save(...)
                                                                           |
                                                            verify(inventory).find("SKU-1")
                                                            verify(repo).save(...)
```

**Stubbing** nói mock *sẽ trả gì hoặc ném gì nếu được gọi đúng*. Nó **không tự gọi method nghiệp vụ**, không xác nhận code đã dùng stub, và không tự chứng minh side effect xảy ra.

**Invocation** là hành động subject under test thực sự gọi mock trong lúc chạy. Mockito ghi lại method, arguments và thứ tự tương tác.

**Verification** kiểm tra lịch sử invocations tại **thời điểm verify**. `verify(mock).method(...)` về mặc định tương đương `verify(mock, times(1)).method(...)`. Nó không đợi background job hoặc callback tương lai trừ khi dùng verification mode đặc biệt; và cả verification timeout cũng không phải một business-completion guarantee.

### Một ví dụ sai phổ biến

```java
when(inventory.find("SKU-1"))
        .thenReturn(Optional.of(new Stock("SKU-1", 10)));

// Không gọi service.reserve(...).

verify(inventory).find("SKU-1"); // Wanted but not invoked.
```

Đây là **snippet minh họa lỗi**, không thuộc các tests được kỳ vọng xanh trong project. Lời gọi bên trong `when` được Mockito dùng để **khai báo stub**, không tính như business invocation cần verify.

## 3. Ma trận triệu chứng và câu hỏi cần đặt

| Thông báo | Câu hỏi chẩn đoán đầu tiên | Sửa theo hướng |
| --- | --- | --- |
| `UnnecessaryStubbingException` | Nhánh test có thực sự gọi stub? | Xóa hoặc chuyển stub vào test cần nó |
| `PotentialStubbingProblem` | Argument thực tế khác stub? | So sánh invocation, chỉnh stub hoặc code |
| `Wanted but not invoked` | Code đã đến lời gọi? Đúng mock instance? | Trace branch/injection, không thêm `times(0)` |
| `Arguments are different!` | `equals`, whitespace, object identity, nullable? | Assert/capture argument đúng contract |
| `TooManyActualInvocations` | Retry/loop/listener có gọi nhiều lần? | Xác định expected attempts, không tùy tiện đổi `times` |
| `NeverWantedButInvoked` | Nhánh không được gọi lại có chạy? | Kiểm tra branch và thời điểm |
| `InvalidUseOfMatchersException` | Trộn matcher với raw args? | Dùng `eq` cho giá trị cố định |
| `WrongTypeOfReturnValue` | Stub method type sai hoặc spy gọi thật? | Kiểm tra generic/overload và `doReturn` |
| `NotAMockException` | Biến verify có phải Mockito mock? | Dùng đúng mock/proxy, không verify object thật |
| `NullPointerException` khi use result | Method chưa stub? Branch khác? | Stub đúng method/args hoặc thiết kế null handling |
| Unit test xanh, Spring test verify 0 | `service` dùng bean thật/bean khác | Dùng `@MockBean` đúng context/type/qualifier |
| Verify async đôi lúc fail | Assertion chạy trước background work | Chờ future/latch/observable state |
| Spy làm network call khi setup | Dùng `when(spy.realCall())` | `doReturn(...).when(spy)` |
| `verifyNoMoreInteractions` dễ đỏ | Test ràng buộc mọi lời gọi phụ | Chỉ verify contract thật sự quan trọng |

Cùng một exception có thể có nhiều nguyên nhân; đọc **stacktrace và danh sách actual interactions** do Mockito in ra trước khi thay expected counts.

## 4. Khi nào nên chọn unit test và Spring integration test?

| Mục tiêu | Công cụ | Điều test chứng minh |
| --- | --- | --- |
| Service gọi đúng repository/client | `MockitoExtension`, `@Mock` | Invocation & business branch |
| Service không gọi repository khi validation fail | `verifyNoInteractions` | Không có side effect ở mock boundary |
| Đối chiếu argument đã truyền | `ArgumentCaptor` | Đúng object/fields đã được save/publish |
| Thứ tự dependency calls | `InOrder` | Invocations có order phù hợp |
| Spy một implementation legacy | `spy` + `doReturn` | Partial mocking/real-method side effects |
| Async callback gọi mock sau khi hoàn tất | `CompletableFuture`/latch | Completion boundary + interaction |
| Bean trong Spring context được thay bởi mock | `@SpringBootTest` + `@MockBean` | Spring bean wiring/proxy context |
| HTTP controller gọi service | `@WebMvcTest` + `@MockBean`/`MockMvc` | Request mapping và service delegation |
| DB query/transaction thực | Testcontainers/`@DataJpaTest`/JDBC integration | DB behavior, không chỉ mock interaction |

**Không khởi động cả Spring Boot** chỉ để test một hàm Java dùng hai dependency interfaces. Nhưng không dùng `@Mock` thuần Mockito rồi kết luận bean trong một `@SpringBootTest` đã được thay thế; hai cơ chế khác nhau.

## 5. Project mẫu: cấu trúc files

Ví dụ xây một `ReservationService` gọi `InventoryClient`, sau đó ghi `ReservationRepository` nếu đủ hàng. Nó được thiết kế để dễ nhìn thấy branch short-circuit, verify counts, argument captor và lỗi repository. Phần async thêm `DeferredPublisher` và `EventSink` với executor được inject.

```text
mockito-diagnostics-lab/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/mockdiagnostics/
│   ├── MockitoDiagnosticsApplication.java
│   ├── Stock.java
│   ├── Reservation.java
│   ├── InventoryClient.java
│   ├── ReservationRepository.java
│   ├── ReservationService.java
│   ├── StatefulFormatter.java
│   ├── EventSink.java
│   └── DeferredPublisher.java
└── src/test/java/com/example/mockdiagnostics/
    ├── ReservationServiceTest.java
    ├── SpyDiagnosticsTest.java
    ├── AsyncVerificationTest.java
    └── ReservationServiceSpringTest.java
```

Các files Java đặt trong cùng package để tránh import dài. Project dùng **Java 17** và Spring Boot 3.3.5, không yêu cầu H2/Docker/Kafka/HTTP server. `@SpringBootApplication` có hai adapter mặc định đơn giản để context chạy được trong ví dụ; Spring test sẽ thay thế chúng bằng `@MockBean`.

## 6. settings.gradle và build.gradle

`settings.gradle`:

```groovy
rootProject.name = 'mockito-diagnostics-lab'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
        exceptionFormat =
            org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
    }
}
```

`spring-boot-starter-test` chứa Mockito, Mockito JUnit Jupiter integration, JUnit Jupiter, AssertJ và Spring Test. Spring Boot BOM quản lý versions nhất quán; không ghim một Mockito major version khác chỉ vì StackOverflow snippet dùng bản cũ.

**Nếu chưa có Gradle Wrapper**, `./gradlew` sẽ không tồn tại; dùng Gradle cài sẵn tương thích hoặc tạo/commit Wrapper. Đây là bước build environment, không phải Mockito failure.

## 7. Ứng dụng Spring Boot tối giản

`src/main/java/com/example/mockdiagnostics/MockitoDiagnosticsApplication.java`:

```java
package com.example.mockdiagnostics;

import java.util.Optional;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MockitoDiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                MockitoDiagnosticsApplication.class, args);
    }

    // Hai adapter demo để ứng dụng có thể khởi động
    // mà không cần hệ thống inventory/database thật.
    // Spring @MockBean sẽ thay thế hai beans này trong test.

    @Bean
    InventoryClient defaultInventoryClient() {
        return sku -> Optional.empty();
    }

    @Bean
    ReservationRepository defaultReservationRepository() {
        return reservation -> { };
    }
}
```

Đây là **adapter giả dành riêng lab**, không phải thiết kế inventory/repository production. Production sẽ dùng HTTP/JDBC adapters thật và test integration tại boundary của chúng. Việc khai báo đúng **một bean** của mỗi interface giúp `@MockBean InventoryClient`/`@MockBean ReservationRepository` trong Spring test thay được đúng beans theo type.

## 8. Domain records và dependency contracts

`src/main/java/com/example/mockdiagnostics/Stock.java`:

```java
package com.example.mockdiagnostics;

public record Stock(String sku, int available) {
    public Stock {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku required");
        }
        if (available < 0) {
            throw new IllegalArgumentException("negative stock");
        }
    }
}
```

`src/main/java/com/example/mockdiagnostics/Reservation.java`:

```java
package com.example.mockdiagnostics;

public record Reservation(String sku, int units) {
    public Reservation {
        if (sku == null || sku.isBlank() || units <= 0) {
            throw new IllegalArgumentException("invalid reservation");
        }
    }
}
```

`src/main/java/com/example/mockdiagnostics/InventoryClient.java`:

```java
package com.example.mockdiagnostics;

import java.util.Optional;

public interface InventoryClient {
    Optional<Stock> find(String sku);
}
```

`src/main/java/com/example/mockdiagnostics/ReservationRepository.java`:

```java
package com.example.mockdiagnostics;

public interface ReservationRepository {
    void save(Reservation reservation);
}
```

Vì `Reservation` là **record**, nó có `equals/hashCode` theo components; do đó `verify(repository).save(new Reservation("SKU-1", 2))` so sánh theo giá trị, không theo object identity. Nếu thay record bằng class Java không override `equals`, verification với object mới có thể báo argument mismatch dù các fields trùng nhau; khi ấy cân nhắc `ArgumentCaptor` hoặc `argThat` cho contract rõ.

## 9. ReservationService: subject under test

`src/main/java/com/example/mockdiagnostics/ReservationService.java`:

```java
package com.example.mockdiagnostics;

import java.util.Objects;
import org.springframework.stereotype.Service;

@Service
public class ReservationService {

    private final InventoryClient inventory;
    private final ReservationRepository repository;

    public ReservationService(
            InventoryClient inventory,
            ReservationRepository repository) {
        this.inventory = Objects.requireNonNull(inventory);
        this.repository = Objects.requireNonNull(repository);
    }

    public Reservation reserve(String sku, int units) {
        if (sku == null || sku.isBlank() || units <= 0) {
            throw new IllegalArgumentException("invalid request");
        }

        Stock stock = inventory.find(sku)
                .orElseThrow(() ->
                        new InsufficientStockException(
                                "stock not found: " + sku));

        if (stock.available() < units) {
            throw new InsufficientStockException(
                    "not enough stock: " + sku);
        }

        Reservation result = new Reservation(sku, units);
        repository.save(result);
        return result;
    }

    public static final class InsufficientStockException
            extends RuntimeException {

        public InsufficientStockException(String message) {
            super(message);
        }
    }
}
```

### Mọi nhánh đều có ý nghĩa cho Mockito

- **Invalid input**: throw trước cả `inventory.find`. Nếu stub inventory trong test này, stub sẽ **không được dùng** → strict stubbing có thể báo `UnnecessaryStubbingException`.
- **Not found**: gọi inventory một lần, **không gọi repository**.
- **Insufficient stock**: gọi inventory, rồi throw, không save.
- **Success**: gọi inventory, sau đó repository.save, trả record.
- **Repository throws**: đã gọi inventory rồi repository, exception truyền ra caller; verify vẫn có thể xác minh invocation trước khi lỗi.

Không có retry/async/Spring transaction trong class này. Do đó trong unit test, `verify(...)` **sau khi `reserve` trả về hoặc ném exception** là đúng thời điểm. Sau đó mới so sánh với ví dụ async ở phần khác.

## 10. Unit tests với MockitoExtension và strict stubbing

`src/test/java/com/example/mockdiagnostics/ReservationServiceTest.java`:

```java
package com.example.mockdiagnostics;

import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ReservationServiceTest {

    @Mock
    InventoryClient inventory;

    @Mock
    ReservationRepository repository;

    ReservationService service;

    @BeforeEach
    void setUp() {
        // Subject nhận đúng hai mocks MockitoExtension tạo.
        service = new ReservationService(inventory, repository);
    }

    @Test
    void reservesWhenStockIsEnough() {
        when(inventory.find("SKU-1"))
                .thenReturn(Optional.of(new Stock("SKU-1", 8)));

        Reservation result = service.reserve("SKU-1", 2);

        assertEquals(new Reservation("SKU-1", 2), result);
        verify(inventory).find("SKU-1");
        verify(repository).save(new Reservation("SKU-1", 2));
        verifyNoMoreInteractions(inventory, repository);
    }

    @Test
    void lowStockDoesNotWrite() {
        when(inventory.find("SKU-2"))
                .thenReturn(Optional.of(new Stock("SKU-2", 1)));

        assertThrows(
                ReservationService.InsufficientStockException.class,
                () -> service.reserve("SKU-2", 3));

        verify(inventory).find("SKU-2");
        verify(repository, never()).save(any(Reservation.class));
    }

    @Test
    void missingSkuDoesNotWrite() {
        when(inventory.find("SKU-3"))
                .thenReturn(Optional.empty());

        assertThrows(
                ReservationService.InsufficientStockException.class,
                () -> service.reserve("SKU-3", 1));

        verify(inventory).find("SKU-3");
        verifyNoInteractions(repository);
    }

    @Test
    void invalidInputSkipsDependencies() {
        // Không khai báo stub: nhánh validate phải dừng sớm.
        assertThrows(
                IllegalArgumentException.class,
                () -> service.reserve(" ", 1));

        assertThrows(
                IllegalArgumentException.class,
                () -> service.reserve("SKU-4", 0));

        verifyNoInteractions(inventory, repository);
    }

    @Test
    void captorInspectsSavedReservation() {
        when(inventory.find("SKU-5"))
                .thenReturn(Optional.of(new Stock("SKU-5", 6)));

        service.reserve("SKU-5", 4);

        ArgumentCaptor<Reservation> captor =
                ArgumentCaptor.forClass(Reservation.class);

        verify(repository).save(captor.capture());

        Reservation saved = captor.getValue();
        assertEquals("SKU-5", saved.sku());
        assertEquals(4, saved.units());
    }

    @Test
    void repeatedCallsRequireExplicitCount() {
        when(inventory.find("SKU-6"))
                .thenReturn(Optional.of(new Stock("SKU-6", 10)));

        service.reserve("SKU-6", 1);
        service.reserve("SKU-6", 2);

        verify(inventory, times(2)).find("SKU-6");
        verify(repository).save(new Reservation("SKU-6", 1));
        verify(repository).save(new Reservation("SKU-6", 2));
    }

    @Test
    void inOrderChecksRequiredSequence() {
        when(inventory.find("SKU-7"))
                .thenReturn(Optional.of(new Stock("SKU-7", 3)));

        service.reserve("SKU-7", 1);

        InOrder order = inOrder(inventory, repository);
        order.verify(inventory).find("SKU-7");
        order.verify(repository)
                .save(new Reservation("SKU-7", 1));
        order.verifyNoMoreInteractions();
    }

    @Test
    void repositoryFailureIsPropagated() {
        when(inventory.find("SKU-8"))
                .thenReturn(Optional.of(new Stock("SKU-8", 5)));

        doThrow(new IllegalStateException("storage unavailable"))
                .when(repository)
                .save(any(Reservation.class));

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> service.reserve("SKU-8", 2));

        assertEquals("storage unavailable", error.getMessage());
        verify(inventory).find("SKU-8");
        verify(repository).save(new Reservation("SKU-8", 2));
    }
}
```

**Có 8 phương thức `@Test`** trong class unit này. Mỗi test chỉ stub những method mà nhánh nghiệp vụ thực tế sẽ gọi. Các @Mock được MockitoExtension tạo/khởi tạo trước method, và `@BeforeEach` đặt chúng đúng vào service.

### Giải thích kỹ về verify counts

Test `repeatedCallsRequireExplicitCount` gọi `reserve` **hai lần**, do đó `inventory.find("SKU-6")` được gọi hai lần. Nếu viết `verify(inventory).find("SKU-6")`, Mockito mặc định kiểm tra **đúng một lần** và báo số invocation quá nhiều. Sửa đúng là `times(2)` vì **code thực tế có hai calls có chủ đích**, không phải tăng count để ép test xanh khi service bị retry bất thường.

Trong cùng test, repository được gọi với **hai arguments khác nhau**, mỗi argument một lần; hai câu `verify(repository).save(new Reservation(...))` là đúng. `verify(repository, times(2)).save(new Reservation("SKU-6",1))` lại **sai**, vì chỉ có một invocation mang chính argument đó.

### @BeforeEach nên tạo service, không stub mọi thứ

`@BeforeEach` tạo `new ReservationService(inventory, repository)` nhưng **không** làm:

```java
when(inventory.find("SKU-1"))
    .thenReturn(Optional.of(new Stock("SKU-1", 10)));
```

cho mọi test. Nếu có một test validation thất bại trước lookup, stub trên sẽ bị unused. Strict mode sẽ báo ở cuối test dù business assertion đã pass. Hãy khai báo stubbing trong test thực sự cần nó; `lenient` chỉ dành cho trường hợp ngoại lệ đã hiểu rõ.

## 11. Stubbing sai argument và PotentialStubbingProblem

Giả sử test muốn chạy `SKU-10` nhưng stub nhầm `SKU-11`:

```java
when(inventory.find("SKU-11"))
    .thenReturn(Optional.of(new Stock("SKU-11", 5)));

service.reserve("SKU-10", 2);
```

Đây là **snippet cố ý sai, không thuộc runnable tests**. Với `MockitoExtension` mặc định `Strictness.STRICT_STUBS`, một invocation khác argument của stub có thể bị báo `PotentialStubbingProblem`. Nếu không bật strictness, mock có thể trả giá trị mặc định cho lời gọi khác và code rẽ sang nhánh sai, tạo `NullPointerException` hoặc exception nghiệp vụ gây nhiễu.

### Cách sửa đúng

- Mở actual invocation trong failure message.
- Kiểm tra service có normalize/trim/change identifier không.
- Nếu hợp đồng cần gọi chính xác `SKU-10`, stub đúng `"SKU-10"` và `verify(inventory).find("SKU-10")`.
- Nếu service có thể gọi một tập arguments hợp lệ, dùng matcher đủ chặt hoặc `thenAnswer` có kiểm soát.
- Không dùng `anyString()` chỉ để làm test hết đỏ khi parameter là nội dung mà test phải bảo vệ.

Một ví dụ với matcher có kiểm soát:

```java
when(inventory.find(org.mockito.ArgumentMatchers.eq("SKU-10")))
    .thenReturn(Optional.of(new Stock("SKU-10", 5)));
```

Đây là snippet cần mock `inventory`, import đúng matcher và một method test gọi đúng argument để tránh unused stubbing.

### PotentialStubbingProblem không có nghĩa production bug chắc chắn

Mockito gọi đây là một **dấu hiệu mismatch tiềm năng**; nếu code có nhiều branches gọi cùng method với arguments khác nhau một cách hợp lệ, hãy xác định thử xem test đang over-specify stub không. Khi thật sự có nhiều stubbings cùng method theo tình huống, `doReturn(...).when(mock)...` hoặc `willReturn(...).given(mock)...` có thể giúp tránh ambiguity ở bước khai báo. Không bật `Strictness.LENIENT` toàn suite như giải pháp đầu tiên.

## 12. UnnecessaryStubbingException: unused stub có thể là dấu hiệu đúng

Ví dụ minh họa lỗi:

```java
when(inventory.find("SKU-1"))
    .thenReturn(Optional.of(new Stock("SKU-1", 8)));

// Nhánh đầu vào invalid trả lỗi trước khi gọi inventory:
assertThrows(IllegalArgumentException.class,
    () -> service.reserve("", 2));
```

Business assertion có thể pass nhưng MockitoExtension sẽ phát hiện stub không dùng và báo `UnnecessaryStubbingException` khi đóng test. Test sạch phải **xóa dòng when(...)**; không cần mock behavior cho một dependency không được gọi.

Một ví dụ khác: test success có ba stubs nhưng chỉ cần một:

```java
when(inventory.find("SKU-1")).thenReturn(Optional.of(...));
when(inventory.find("SKU-2")).thenReturn(Optional.of(...));
when(inventory.find("SKU-3")).thenReturn(Optional.of(...));

service.reserve("SKU-1", 1);
```

Đây là pseudocode với `...`, **không runnable**. Hai stubs `SKU-2` và `SKU-3` thừa. Không xóa assertion chính xác của Mockito; hãy loại những data arrangements không phục vụ scenario.

### Khi nào lenient hợp lý?

```java
lenient().when(inventory.find("SKU-COMMON"))
        .thenReturn(Optional.of(new Stock("SKU-COMMON", 1)));
```

Snippet này cần import static `Mockito.lenient`. Leniency bỏ qua một số strict-stubbing checks **cho stub cụ thể**; nếu test không dùng stub này, nó có thể tồn tại mà không báo unused. Nhưng đó là lựa chọn **cuối cùng** khi shared fixture phức tạp không thể tách hợp lý, không phải thói quen cho mỗi test.

Ưu tiên thứ tự:

1. Xóa stub không cần.
2. Chuyển stub từ `@BeforeEach` sang test thực sự dùng nó.
3. Chia fixture/builder theo từng scenario.
4. Thay stub quá cụ thể bằng matcher đúng contract nếu thích hợp.
5. Chỉ khi có lý do thực, đặt `lenient()` trên một stubbing, ghi chú lý do.
6. Tránh `@MockitoSettings(strictness=LENIENT)` trên cả test class nếu chỉ một stub khó cấu hình.

## 13. Default answers và NullPointerException bất ngờ

Một Mockito mock thông thường không tự gọi implementation thật. Với method chưa stub:

- Reference type có thể trả `null`.
- Primitive có default `0`/`false`.
- Một số kiểu quen thuộc như collection hoặc `Optional` có empty defaults trong Mockito hiện đại.
- Void method mặc định **không làm gì**.
- Smart/Deep stubs là lựa chọn riêng; không cần cho phần lớn unit tests.

Nếu code gọi `inventory.find("SKU-2")` trong khi test stub `inventory.find("SKU-1")`, không nên suy chắc nó trả `null`: với method trả `Optional`, Mockito có thể trả `Optional.empty()`. Test sẽ thấy `InsufficientStockException` trong ví dụ, hoặc strict stubbing mismatch trước đó. **Đừng suy root cause chỉ từ exception cuối cùng**, hãy kiểm tra arguments và stubbing list.

### Không dùng RETURNS_DEEP_STUBS để che thiết kế

`mock(Foo.class, RETURNS_DEEP_STUBS)` có thể cho phép `when(foo.getBar().getBaz().value())...` nhưng sẽ làm tests coupling vào chain nội bộ, khó refactor và dễ che null boundary. Ưu tiên inject các collaborators rõ ràng hoặc tạo DTO thật khi dữ liệu là object đơn giản.

## 14. ArgumentMatchers: dùng đồng nhất và đủ chặt

Một method có hai arguments ví dụ `publisher.send(channel, event)`:

**Sai**:

```java
when(publisher.send(anyString(), "payload"))
    .thenReturn(true);
```

**Đúng**:

```java
when(publisher.send(anyString(), eq("payload")))
    .thenReturn(true);
```

Hai snippets này **không nằm trong project runnable** vì `publisher.send` chỉ là API minh họa. Khi sử dụng matcher trên một parameter trong một invocation, các parameters còn lại trong cùng invocation phải dùng matcher tương ứng (`eq`, `any`, v.v.).

### Matcher không phải “giá trị magic”

`anyString()` được dùng trong vị trí argument của lời gọi lên mock trong stubbing/verify; nó không có nghĩa “một string random để truyền vào service”. Không viết:

```java
service.reserve(anyString(), 2); // Sai mục đích.
```

Matcher là cơ chế Mockito, không phải generator test data. Dùng một giá trị cụ thể như `"SKU-1"` để gọi code under test.

### Null matching

Trong Mockito 5, `anyString()` match các string **không null**, không tự match null. Muốn assert null có thể dùng `isNull()`, hoặc dùng `nullable(String.class)` cho cả null và non-null khi policy thật cần. Ví dụ:

```java
verify(inventory).find(isNull());
```

Snippet trên chỉ có ý nghĩa nếu code under test thật sự gọi `inventory.find(null)`; `ReservationService` ở project **cố ý validate trước** nên không có invocation đó. Dùng matcher không khớp để “verify null” trong case invalid input sẽ fail đúng.

### Overload/generic types

Nếu interface có overload `find(String)` và `find(UUID)`, matcher `any()` có thể khiến compiler khó phân giải method hoặc dẫn tới stubbing overload sai. Dùng `anyString()` hoặc `any(UUID.class)` với type cụ thể. Với method trả `Optional<List<T>>`, bảo đảm `thenReturn(...)` đúng kiểu trả về.

## 15. void methods: doThrow/doNothing thay vì when(...).thenReturn

`ReservationRepository.save` trả `void`. Đoạn này **không biên dịch**:

```java
when(repository.save(new Reservation("SKU-1", 2)))
    .thenThrow(new IllegalStateException());
```

Java không cho dùng một `void` expression như argument cho `when`. Đúng là:

```java
doThrow(new IllegalStateException("storage unavailable"))
    .when(repository)
    .save(new Reservation("SKU-1", 2));
```

Muốn mặc định không làm gì với void method trên mock, thường **không cần** `doNothing` vì void mock vốn no-op. `doNothing().when(spy).dangerousVoid()` lại hữu ích nếu spy không được gọi method thật. `doAnswer(...)` dùng khi thật sự cần giả callback hoặc side effect có kiểm soát, nhưng đừng biến một mock thành mini application nếu DTO/real object đơn giản đã đủ.

### Kiểm tra exception branch sau doThrow

Có một lần gọi `save` trước khi repository throw. Sau `assertThrows`, `verify(repository).save(...)` vẫn hợp lệ vì Mockito ghi nhận invocation. Đừng suy “method throw nên Mockito không tính số lần gọi”.

## 16. @Spy: lỗi khi stubbing gọi method thật ngay trong setup

`src/main/java/com/example/mockdiagnostics/StatefulFormatter.java`:

```java
package com.example.mockdiagnostics;

import java.util.Locale;

public class StatefulFormatter {

    private int calls;

    public String normalize(String raw) {
        calls++;

        if (raw == null) {
            throw new IllegalArgumentException("raw is null");
        }

        return raw.trim().toUpperCase(Locale.ROOT);
    }

    public int calls() {
        return calls;
    }
}
```

`spy(new StatefulFormatter())` là **partial mock**: những methods chưa stub thường gọi real implementation. Nếu `when(spy.normalize(" hi ")).thenReturn("FIXED")`, Java cần evaluate `spy.normalize(...)` trước khi truyền kết quả vào `when(...)`; method thật chạy **một lần trong lúc stubbing**. Nếu nó ghi DB hoặc gửi HTTP, setup test đã gây side effect.

### Dùng doReturn để tránh thực thi method lúc setup

`src/test/java/com/example/mockdiagnostics/SpyDiagnosticsTest.java`:

```java
package com.example.mockdiagnostics;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class SpyDiagnosticsTest {

    @Test
    void doReturnSkipsRealMethodDuringSetup() {
        StatefulFormatter formatter =
                spy(new StatefulFormatter());

        doReturn("FIXED")
                .when(formatter)
                .normalize(" hi ");

        assertEquals(0, formatter.calls());

        assertEquals("FIXED",
                formatter.normalize(" hi "));

        // normalize đã được stub, không gọi real logic.
        assertEquals(0, formatter.calls());
        verify(formatter).normalize(" hi ");
    }

    @Test
    void whenOnSpyCallsRealMethodDuringStubbing() {
        StatefulFormatter formatter =
                spy(new StatefulFormatter());

        when(formatter.normalize(" hi "))
                .thenReturn("FIXED");

        // Tại thời điểm thiết lập when, method thật đã chạy.
        assertEquals(1, formatter.calls());

        // Method đã stub được gọi lại và trả giá trị giả.
        assertEquals("FIXED",
                formatter.normalize(" hi "));
        assertEquals(1, formatter.calls());
    }
}
```

**Có 2 phương thức `@Test`** trong class này. Tests dùng `spy` trực tiếp, không cần `MockitoExtension` vì không có @Mock fields hay session strictness requirement.

### Spy không đồng nhất với object gốc

Mockito spies thường tạo **bản sao trạng thái** của object được đưa vào `spy(realObject)`, không phải luôn delegate mọi call về chính object đó. Nếu giữ cả `realObject` và `spyObject`, đừng so sánh side effects trên object gốc mà nghĩ mình đã quan sát state của spy. Bài chỉ gọi `formatter.calls()` trên **spy**, tránh nhầm này.

### @SpyBean và Spring AOP proxy

Trong Spring Boot 3.3, `@SpyBean` cho phép wrap Spring bean thật; nó có thể kích hoạt side effects nếu stub bằng `when(spy.method())`. Với beans có Spring AOP proxies, `@Transactional`, `@Cacheable` hoặc security advice, cần hiểu đang spy proxy hay target; khi cần, dùng Spring `AopTestUtils` theo tài liệu. Không dùng `spy(new SomeService())` rồi suy interceptor của Spring đã được kiểm thử.

## 17. verify() mặc định đòi đúng một invocation

Các câu sau có nghĩa khác nhau:

```java
verify(inventory).find("SKU-1");             // Đúng 1 lần.
verify(inventory, times(1)).find("SKU-1");   // Tương đương.
verify(inventory, times(2)).find("SKU-1");   // Đúng 2 lần.
verify(inventory, never()).find("SKU-1");    // Đúng 0 lần.
verify(inventory, atLeastOnce()).find("SKU-1");// >= 1 lần.
```

Đây là **snippets** dùng mock `inventory` từ project và imports `times`, `never`, `atLeastOnce`. Không phải những câu có thể cùng pass trên một lịch sử invocations; mỗi verification mode thể hiện một contract riêng.

### Số lần gọi có thể bị hiểu nhầm

- Một retry decorator có thể gọi repository/client nhiều lần.
- Một loop gọi adapter cho mỗi item; verify số calls tương ứng số items.
- Một callback có thể được đăng ký hai lần.
- Một `@BeforeEach` hoặc setup code đã gọi mock ngoài ý định.
- Mockito mock từ test trước còn history nếu không reset, nhất là khi tạo static mock hoặc dùng shared Spring context sai reset policy.
- Một method được gọi cả khi stubbing spy bằng `when(...)`.
- `verifyNoMoreInteractions` phát hiện thêm calls chưa được verify, nhưng dễ coupling test với các detail methods không thuộc hợp đồng.

**Không sửa `times(1)` thành `atLeastOnce()` chỉ vì test đang thấy 2 calls.** Xác định lần gọi thứ hai là đúng hay bug; nếu code đáng lẽ một lần, giữ assertion và sửa logic.

## 18. ArgumentCaptor: kiểm tra đúng object đã gửi

Trong `captorInspectsSavedReservation`:

```java
ArgumentCaptor<Reservation> captor =
        ArgumentCaptor.forClass(Reservation.class);

verify(repository).save(captor.capture());

Reservation saved = captor.getValue();
assertEquals("SKU-5", saved.sku());
assertEquals(4, saved.units());
```

`ArgumentCaptor` đọc argument **sau khi invocation đã xảy ra**. Nó không thay thế việc gọi service. Nếu không có `repository.save`, câu `verify(...).save(captor.capture())` sẽ báo không có invocation.

### Khi nào dùng captor và khi nào dùng equals?

- DTO/record có `equals` rõ → `verify(repo).save(new Reservation(...))` gọn.
- Cần kiểm tra nhiều fields hoặc một transformation → captor dễ đọc.
- Object không có `equals` ổn định → captor hoặc `argThat` có thể phù hợp.
- Có nhiều invocations → `captor.getAllValues()` và kiểm tra danh sách theo contract.
- Không nên dùng captor làm “matcher bất kỳ” lúc stubbing nếu chỉ cần một response; dùng `eq/any` rõ hơn.

### Captor không chứng minh DB đã commit

`verify(repo).save(...)` chỉ chứng minh service **gọi dependency**. Nếu repository mock là no-op thì không có dữ liệu nào được ghi xuống database. Muốn bảo vệ JDBC/JPA transaction, cần integration test với database thật và assertion dữ liệu sau transaction/commit boundary.

## 19. InOrder và verifyNoMoreInteractions

`InOrder` kiểm tra **thứ tự invocations** giữa mocks:

```java
InOrder order = inOrder(inventory, repository);
order.verify(inventory).find("SKU-7");
order.verify(repository).save(
        new Reservation("SKU-7", 1));
order.verifyNoMoreInteractions();
```

Điều này hữu ích nếu nghiệp vụ yêu cầu **check stock trước khi persist**. Nhưng nếu logic có nhiều benign calls như metrics/tracing getters, đừng ràng buộc toàn bộ history khi không cần.

### Tránh verifyNoMoreInteractions trên mọi test

`verifyNoMoreInteractions(inventory, repository)` bảo vệ “không có invocation nào khác” sau những interactions đã verify. Đây là contract mạnh; nếu service thêm một lookup phụ hoàn toàn hợp lệ, test sẽ fail. Dùng nó khi **absence of extra calls thật sự quan trọng** (payment charge, idempotent write, retry budget), không biến thành nghi thức bắt buộc cho mọi getter.

`verifyNoInteractions(repository)` khác: nó assert repository **chưa được gọi lần nào**, bất kể method. `verify(repository, never()).save(...)` chỉ assert **method cụ thể** với argument matcher đó không được gọi; repository có thể đã nhận method khác mà verification vẫn pass. Chọn mức chặt chẽ theo mục tiêu test.

## 20. Lỗi mock instance: service đang cầm đối tượng nào?

Một kiểu lỗi rất dễ gặp:

```java
InventoryClient mockA = mock(InventoryClient.class);
InventoryClient mockB = mock(InventoryClient.class);

ReservationService service =
        new ReservationService(mockB, repository);

service.reserve("SKU-1", 1);

verify(mockA).find("SKU-1"); // Sai instance.
```

Đây là **snippet cố ý sai**, và để chạy đến verify cần mockB được stub trả stock hợp lệ. Cốt lõi là `verify(mockA)` không thể thấy calls trên `mockB`. Nếu cố debug bằng `verify(mockA, times(0))`, test chỉ che việc service không dùng mock bạn tưởng.

### Dấu hiệu nhận diện

- Có nhiều `new ReservationService(...)` trong fixture.
- Dùng `@Mock` field nhưng `@InjectMocks` hoặc constructor manual tạo service khác.
- Spring test dùng `@Mock` nhưng bean service được `@Autowired` từ context và vẫn giữ collaborator bean thật.
- Một bean có nhiều implementations với `@Qualifier`, mock nhầm bean name.
- Test verify một spy tự tạo bằng `spy(...)` nhưng Spring vẫn gọi target bean khác.
- Một async callback capture object cũ, test lại verify mock mới.
- `Mockito.reset(mock)` được gọi giữa business call và verify nên invocation history bị xóa.

### Cách chẩn đoán identity

`Mockito.mockingDetails(object).isMock()` và `isSpy()` cho biết một object có được Mockito xem là mock/spy hay không. Có thể dùng `mockingDetails(mock).getInvocations()` để xem recorded interactions trong test diagnostics, nhưng đừng dựa vào text format nội bộ để viết business assertion. Với Spring proxy, identity/proxy/target có thể khác, nên cần xác minh bean wiring thay vì ép mọi proxy là Mockito mock trực tiếp.

## 21. @Mock, @InjectMocks và @MockBean khác nhau

| Annotation | Vai trò | Context |
| --- | --- | --- |
| `@Mock` | Tạo mock cho field/parameter | MockitoExtension/unit test |
| `@InjectMocks` | Yêu cầu Mockito inject mocks qua constructor/setter/fields theo khả năng | Object under test, không đăng ký Spring bean |
| `@Spy` | Partial mock object thật | Mockito-managed |
| `@MockBean` (Boot 3.3) | Tạo/thay bean trong Spring ApplicationContext | Spring Boot Test |
| `@SpyBean` (Boot 3.3) | Wrap Spring bean với spy | Spring Boot Test |

**`@InjectMocks` không phải dependency injection container.** Nếu inject nhầm vì constructors overloaded, field names/types trùng hoặc không tìm thấy dependency, Mockito không đảm bảo báo lỗi rõ như Spring context. Với service chỉ có hai dependencies, `new ReservationService(inventory, repository)` tường minh giúp thấy mock nào được dùng và dễ debug hơn.

**`@MockBean` không chỉ tương đương `@Mock`.** Nó đăng ký/replaces đúng một Spring bean theo type hoặc name, cho phép `@Autowired ReservationService` nhận dependency mock từ context. Boot 3.3 mặc định reset @MockBean **sau mỗi test method**. Nhưng reset mock không reset DB, cache, topic hay singleton mutable state khác; không nhầm nó với `@DirtiesContext`.

## 22. Spring Boot integration test dùng @MockBean đúng chỗ

`src/test/java/com/example/mockdiagnostics/ReservationServiceSpringTest.java`:

```java
package com.example.mockdiagnostics;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ReservationServiceSpringTest {

    @Autowired
    ReservationService service;

    @MockBean
    InventoryClient inventory;

    @MockBean
    ReservationRepository repository;

    @Test
    void mockBeansAreInjectedIntoSpringManagedService() {
        when(inventory.find("SPR-1"))
                .thenReturn(Optional.of(new Stock("SPR-1", 4)));

        Reservation result = service.reserve("SPR-1", 2);

        assertEquals(new Reservation("SPR-1", 2), result);
        verify(inventory).find("SPR-1");
        verify(repository).save(new Reservation("SPR-1", 2));
    }

    @Test
    void invalidInputDoesNotUseSpringMockBeans() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.reserve(" ", 1));

        verifyNoInteractions(inventory, repository);
    }
}
```

**Có 2 phương thức `@Test`**. Ở đây Spring Boot tạo `ReservationService` thực và injects hai `@MockBean`, thay cho two demo adapters trong `MockitoDiagnosticsApplication`. Không thêm `@ExtendWith(MockitoExtension.class)` lên Spring test này: Spring Boot Test đã quản lý mocks/extension lifecycle qua TestContext support.

### Vì sao Spring test không cần strict-stubbing giống unit test?

`@MockBean` được Boot quản lý và reset theo TestContext; chi tiết strictness không nhất thiết tương đương một test class chạy bằng `MockitoExtension` mặc định. Vì vậy đừng dựa vào việc unused stub chắc chắn bị ném y hệt giữa hai loại test. Dù framework có báo hay không, vẫn nên khai báo stubs tối thiểu trong từng test.

### Trường hợp Spring có nhiều beans cùng interface

Nếu có hai `InventoryClient` beans (primary và fallback), `@MockBean InventoryClient` theo type có thể không biết thay bean nào. Chọn đúng `name` hoặc `@Qualifier` và test rằng injected collaborator thực là mock cần verify. Đừng thêm mock cùng type một cách mơ hồ rồi tự cho rằng nó sẽ thay hết mọi instances.

### Khi mock cần hành vi lúc context refresh

Theo tài liệu Spring Boot, `@MockBean` được cấu hình ở test method **sau** khi Spring context đã refresh. Nếu một bean gọi dependency trong `@PostConstruct`, `SmartInitializingSingleton` hoặc application startup, bạn không thể stub mock trong `@Test` rồi kỳ vọng stubbing đã có **trước** startup. Dùng cấu hình `@TestConfiguration`/`@Bean` tạo mock và stub trước phase cần thiết, hoặc refactor side effects khỏi construction/startup. Đây là lỗi **verify sai lifecycle**, không phải chỉ sai thread.

## 23. @MockBean và @MockitoBean theo phiên bản Spring

**Với project Spring Boot 3.3.5:**

```java
import org.springframework.boot.test.mock.mockito.MockBean;
```

Spring Framework 6.2 giới thiệu `org.springframework.test.context.bean.override.mockito.MockitoBean` và `MockitoSpyBean`, và Spring Boot từ 3.4 bắt đầu deprecate legacy Boot `@MockBean`/`@SpyBean`. Không copy import `@MockitoBean` vào một dự án Boot 3.3/Framework 6.1 rồi kết luận Mockito hỏng khi code không biên dịch.

Khi migrate framework, xem release notes và kiểm thử lại:
- Bean override by name/type.
- Qualifier behavior.
- Context cache keys.
- Reset/lifecycle semantics.
- Injection/proxy identity.
- Setup stubbing cho initialization.
- Test slices đang dùng annotations tương ứng.

Không trộn hai version instructions trong cùng một runnable project.

## 24. Async verify: thời điểm là một phần của contract

Trong một method đồng bộ như `ReservationService.reserve`, sau khi call trả về thì dependency invocations đã xảy ra. Trong một method `@Async`, callback Reactor, `CompletableFuture`, scheduler hoặc message listener, lời gọi `publish` có thể **chỉ schedule work**.

Một test sai:

```java
publisher.publishLater("EV-1"); 
verify(sink).publish("EV-1"); // Có thể chạy trước worker.
```

Đây là snippet không thuộc project code test; lỗi nằm ở việc verify ngay sau enqueue. Nếu worker chưa chạy, Mockito báo `Wanted but not invoked`. Tăng `Thread.sleep(1000)` chỉ che race trên một máy, không đảm bảo CI đáng tin.

### Cách chuẩn: hoàn thành future trước rồi verify

`CompletableFuture.runAsync(...)` trả một future đại diện cho công việc. Nếu test gọi `future.get(5, SECONDS)` và thành công, câu `verify` sau đó có một **happens-before/completion boundary** có ý nghĩa, không phụ thuộc vào sleep.

Với listener/worker không trả future, hãy dùng `CountDownLatch`, `CompletableFuture` probe, Awaitility hoặc state từ output thực có bounded wait. Không verify trước khi dependency work đã đạt điểm hoàn tất mà test muốn bảo vệ.

## 25. EventSink và DeferredPublisher: code async đầy đủ

`src/main/java/com/example/mockdiagnostics/EventSink.java`:

```java
package com.example.mockdiagnostics;

public interface EventSink {
    void publish(String eventId);
}
```

`src/main/java/com/example/mockdiagnostics/DeferredPublisher.java`:

```java
package com.example.mockdiagnostics;

import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

public final class DeferredPublisher {

    private final Executor executor;
    private final EventSink sink;

    public DeferredPublisher(Executor executor, EventSink sink) {
        this.executor = Objects.requireNonNull(executor);
        this.sink = Objects.requireNonNull(sink);
    }

    public CompletableFuture<Void> publishLater(String eventId) {
        Objects.requireNonNull(eventId);

        return CompletableFuture.runAsync(
                () -> sink.publish(eventId),
                executor);
    }
}
```

Executor được inject để test có quyền điều khiển thread/lifecycle, không cần `@SpringBootTest` cho đơn vị logic này. In production, adapter có thể được Spring-managed executor; trong unit test, `Executors.newSingleThreadExecutor()` được tạo/đóng trong mỗi test.

Nếu bạn đổi implementation sang Reactor `Mono` hoặc `@Async`, phải kiểm tra publisher/scheduler/subscription semantics; không dùng `future.get` khi API chỉ trả Publisher chưa subscribe.

## 26. AsyncVerificationTest: future, controlled gate và worker failure

`src/test/java/com/example/mockdiagnostics/AsyncVerificationTest.java`:

```java
package com.example.mockdiagnostics;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

@ExtendWith(MockitoExtension.class)
class AsyncVerificationTest {

    @Mock
    EventSink sink;

    @Test
    void waitsForCompletionBeforeVerifyingInteraction()
            throws Exception {

        ExecutorService pool =
                Executors.newSingleThreadExecutor();

        try {
            DeferredPublisher publisher =
                    new DeferredPublisher(pool, sink);

            CompletableFuture<Void> done =
                    publisher.publishLater("EV-1");

            done.get(5, TimeUnit.SECONDS);

            verify(sink).publish("EV-1");
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void controlledGateMakesNeverVerificationMeaningful()
            throws Exception {

        ExecutorService pool =
                Executors.newSingleThreadExecutor();

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Executor gatedExecutor = command ->
                pool.execute(() -> {
                    started.countDown();
                    try {
                        if (!release.await(
                                5, TimeUnit.SECONDS)) {
                            throw new IllegalStateException(
                                    "gate timed out");
                        }
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(e);
                    }
                    command.run();
                });

        try {
            DeferredPublisher publisher =
                    new DeferredPublisher(gatedExecutor, sink);

            CompletableFuture<Void> done =
                    publisher.publishLater("EV-2");

            assertTrue(started.await(5, TimeUnit.SECONDS));

            // Worker đã bắt đầu nhưng bị chặn bởi gate.
            // Khẳng định "chưa gọi" ở điểm kiểm soát này.
            verifyNoInteractions(sink);

            release.countDown();
            done.get(5, TimeUnit.SECONDS);

            // Sau khi worker hoàn thành mới khẳng định "đã gọi".
            verify(sink).publish("EV-2");
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }

    @Test
    void asyncFailureSurfacesViaFuture()
            throws Exception {

        doThrow(new IllegalStateException("sink unavailable"))
                .when(sink).publish("EV-3");

        ExecutorService pool =
                Executors.newSingleThreadExecutor();

        try {
            DeferredPublisher publisher =
                    new DeferredPublisher(pool, sink);

            CompletableFuture<Void> done =
                    publisher.publishLater("EV-3");

            ExecutionException error = assertThrows(
                    ExecutionException.class,
                    () -> done.get(5, TimeUnit.SECONDS));

            IllegalStateException cause = assertInstanceOf(
                    IllegalStateException.class,
                    error.getCause());

            assertEquals("sink unavailable", cause.getMessage());
            verify(sink).publish("EV-3");
        } finally {
            pool.shutdownNow();
        }
    }
}
```

**Có 3 phương thức `@Test`** trong class async. Ở đây không có `Thread.sleep`; mỗi test tạo một executor và đóng nó. Failure của worker được quan sát qua `ExecutionException.getCause()` từ `CompletableFuture.get`, chứ không qua `assertThrows` ngay trên `publishLater`.

### Điểm quan trọng nhất trong gated test

`verifyNoInteractions(sink)` chạy **khi worker bị chặn** ở latch mà test đã xác nhận `started`. Đó là một assertion có ý nghĩa tại điểm trạng thái được điều khiển. Sau khi mở gate, `done.get(...)` xác nhận task hoàn thành và `verify(sink).publish("EV-2")` mới được gọi.

Nếu gọi `verify(sink, never()).publish(...)` **trước khi worker hoàn thành mà không có gate**, assertion có thể pass tại thời điểm T nhưng worker sẽ gọi mock ngay sau đó. Một câu verify không thể chứng minh “sẽ không bao giờ xảy ra trong tương lai” khi asynchronous task vẫn chạy.

### Có cần awaitTermination?

Trong ba tests, `done.get`/failure future đã hoàn tất trước finally trong normal path, nên `shutdownNow` giải phóng executor. Nếu test timeout, `shutdownNow` cố interrupt task và tests fail; với một production-grade concurrency fixture có nhiều tasks blocking, có thể bổ sung bounded `awaitTermination` để đảm bảo worker không rò sang test tiếp. Không dùng `Thread.stop` hoặc unbounded wait.

## 27. Mockito.timeout và Mockito.after: có ích nhưng dễ hiểu sai

Mockito có verification modes chờ:

```java
verify(sink, timeout(1000)).publish("EV-1");
verify(sink, timeout(1000).times(2)).publish("EV-1");
verify(sink, after(500).never()).publish("EV-2");
```

Đây là **snippets minh họa**, không cùng pass trên lịch sử calls của demo. Cần static imports `Mockito.timeout` và `Mockito.after`.

- `timeout(1000)` kiểm tra lại trong tối đa khoảng 1000 ms; nó có thể **trả về sớm ngay khi điều kiện đạt**, không đợi toàn bộ công việc hoàn thành.
- `timeout(...).times(2)` trở thành success khi thấy đủ hai calls, nhưng không chứng minh caller sẽ không có call thứ ba **sau khi verify trả về**.
- `after(...)` chờ theo khoảng quan sát rồi verify, có thể hữu ích cho assertion về không có interaction trong một khoảng kiểm soát, nhưng không chứng minh vắng mặt mãi mãi.
- Mockito docs khuyên dùng timed verification **tiết chế**; nếu business method trả future/latch hoặc state hoàn tất, đó thường là boundary mạnh hơn.
- `timeout` không thay thế `StepVerifier` cho reactive stream, không thay `MockMvc` cho HTTP request/response, không thay Kafka acknowledgment và không bảo đảm DB transaction commit.
- Mockito tài liệu ghi những hạn chế khi kết hợp timed verification với `InOrder`; không xây một async order test dựa vào API combination mà phiên bản Mockito không hỗ trợ.

**Ưu tiên:** await đúng signal hoàn tất → assert business state → verify interactions khi chúng mang ý nghĩa contract. Dùng `timeout` khi không thể expose completion signal và cần một eventual invocation check có giới hạn.

## 28. Test @Async, HTTP, Kafka và callback: chờ cái gì?

| Hệ thống | Readiness/completion đáng tin | Không nên suy |
| --- | --- | --- |
| `CompletableFuture` | `future.get(timeout)`/`join` có outer timeout policy | Schedule thành công = xử lý xong |
| Spring `@Async` void | Latch/test probe hoặc business outcome | Caller return = listener xong |
| Reactor `Mono/Flux` | `StepVerifier`/subscription outcome | Khai báo Publisher = đã subscribe |
| MockMvc synchronous request | `mvc.perform(...).andExpect(...)` | Không phù hợp cho controller async chưa dispatch |
| Spring MVC async controller | `asyncStarted` + `asyncDispatch` khi applicable | First perform đã có final response |
| Kafka listener | Partition assignment, message result, bounded wait | Producer send ack = consumer xử lý |
| RabbitMQ | Queue/listener readiness, bounded consumer result | Publish confirm = consumer ACK |
| DB transaction | Query sau transaction/commit boundary | Mock repository.save = row persisted |
| Scheduled job | Job completion/status/event probe | Scheduler.start = job hoàn tất |

Không cố giải quyết verify timing bằng `Mockito.reset` giữa chừng. Reset xóa both stubbing và invocation history của mock, có thể khiến timing race khó thấy hơn.

## 29. Mockito.verifyNoMoreInteractions và strict stubs không giống nhau

Hai khái niệm liên quan nhưng không đồng nghĩa:

- **Strict stubbing** phân tích stubs để phát hiện việc không dùng hoặc arguments mismatch.
- **Verify/verifyNoMoreInteractions** phân tích lịch sử **invocations** để bảo vệ call contract.

Một test có thể **không có unused stub** nhưng vẫn `Wanted but not invoked` nếu verify sai method. Ngược lại, test có thể verify đúng một method nhưng còn unused stub khác do setup thừa. `STRICT_STUBS` có một số behavior tự coi stubbed invocations được verify trong các tình huống `verifyNoMoreInteractions`, nhưng không nên dựa vào chi tiết này để biến unit test thành snapshot của mọi interaction.

**Quy tắc:** stubbing tối thiểu, assertions về outcome trước, verify interactions quan trọng sau. Tránh over-mocking và quá nhiều asserts cho implementation detail.

## 30. Mockito.mockingDetails: xem test đang giữ loại object nào

Trong debug có thể kiểm tra:

```java
System.out.println(
    Mockito.mockingDetails(inventory).isMock());

System.out.println(
    Mockito.mockingDetails(inventory).getInvocations());
```

Đây là **snippet diagnostic**, cần import `org.mockito.Mockito` và mock inventory đã được tạo. Không phải output cố định: invocations phụ thuộc lịch sử đã chạy. Đừng commit print này vô hạn; nó có thể đưa arguments nhạy cảm vào CI logs. Nếu phải chẩn đoán trong build server, dùng logger/test report đã redaction và gỡ diagnostic sau khi sửa.

Với Spring proxies, một bean có thể là AOP proxy quanh target, nên `isMock()` trên proxy có thể không phản ánh Mockito target trực tiếp. Dùng Spring Test bean override wiring và xác minh actual collaborator bằng integration assertions thay vì đoán từ một print.

## 31. WrongTypeOfReturnValue và stubbing trên spy

`WrongTypeOfReturnValue` có thể xuất hiện khi một stub được gán return value không phù hợp method thực hoặc khi spy/overload/concurrency khiến Mockito bắt sai invocation ở thời điểm setup. Nên:

1. Kiểm tra method signature/interface generic type.
2. Kiểm tra overload và imports của `when`/`given`.
3. Nếu object là spy, dùng `doReturn(...).when(spy).method(...)` để tránh method thật bị gọi lúc stubbing.
4. Không thực hiện stubbing đồng thời trên cùng một mock từ nhiều threads mà không có lifecycle control.
5. Không dùng raw types/casts để ép một wrong result vào API và làm test xanh giả.
6. Giữ Mockito phiên bản tương thích với JDK 17 và Spring Boot BOM.

### Stubbing một method final hoặc static

Mockito 5 hỗ trợ nhiều tình huống final/static mocking tùy mock maker/instrumentation, nhưng chúng có constraints. Với static mocks, dùng `MockedStatic` trong try-with-resources để đóng scope, tránh rò behavior sang tests khác. Tuy nhiên nếu cần mock nhiều static functions của service, đó thường là dấu hiệu code khó test; cân nhắc inject time, HTTP client hoặc repository thay vì mock global state.

## 32. Dùng @BeforeEach, reset và Spring TestContext đúng cách

Một test suite hay có setup:

```java
@BeforeEach
void setup() {
    Mockito.reset(inventory);
    when(inventory.find("SKU-DEFAULT")).thenReturn(...);
}
```

Đây là **pseudocode cố ý có rủi ro**. Với `MockitoExtension`, mỗi test đã được cấp mocks và strictness session thích hợp. Reset thường không cần, còn stub mặc định có thể unused ở nhiều nhánh. Với `@MockBean`, Spring Boot 3.3 đã reset mock sau mỗi test theo default; một manual `Mockito.reset` giữa execution có thể xóa history trước khi verify.

Tách fixture:

- Common setup **tạo subject** và immutable test data.
- Mỗi test **stub đúng branch**.
- Mỗi test verify khi code đã hoàn tất.
- Nếu một shared mock có lifecycle xuyên async/test methods, đảm bảo worker đã stop/join trước reset.
- Nếu Spring context cache tái sử dụng context, phân biệt mock state reset với mutable beans/DB/cache không tự reset.
- Với Testcontainers/brokers, dùng resource namespace/cleanup thật; mock reset không xóa rows/messages.

## 33. Chẩn đoán Mockito exception theo báo cáo

| Exception / message | Dấu hiệu | Cách điều tra |
| --- | --- | --- |
| `UnnecessaryStubbingException` | Stub khai báo không được dùng | Lần theo branch, giảm setup |
| `PotentialStubbingProblem` | Arguments thực khác expected stubbing | So sánh actual call/stub |
| `WantedButNotInvoked` | Không có invocation phù hợp | Kiểm tra service gọi đúng mock/branch/timing |
| `TooManyActualInvocations` | Call count vượt expected | Kiểm tra retry/loops/duplicate listeners |
| `NeverWantedButInvoked` | Method không mong đợi đã được gọi | Kiểm tra early-return/guard |
| `ArgumentsAreDifferent` | Method giống nhưng arguments khác | Captor/equals/matcher/normalization |
| `InvalidUseOfMatchersException` | Matcher misuse | Dùng all matchers cho method invocation |
| `NotAMockException` | Object trong `verify/reset` không phải mock | Xác minh @Mock/@MockBean/spy identity |
| `WrongTypeOfReturnValue` | Stub return type sai hoặc spy real method | Kiểm tra method overload/return và doReturn |
| `UnfinishedStubbingException` | `when(...)` chưa hoàn tất thenReturn | Hoàn tất setup, không nested stubbing |
| `UnfinishedVerificationException` | `verify(mock)` thiếu method | Gọi method ở sau verify |
| `NullInsteadOfMockException` | Mock reference null | MockitoExtension chưa bật/field chưa init |
| `NotAMockException` trên Spring bean | Proxy/target hoặc mock sai instance | Xem Boot @MockBean wiring |

Tên exception trong bảng mô tả nhóm thường gặp; **text exact** tùy Mockito version, Java proxy hoặc đoạn code. Đừng assert nguyên văn lỗi framework trong business test trừ khi bạn cố tình kiểm tra framework behavior.

## 34. Quy trình debug 12 bước

1. Đọc failed test class/method và **first meaningful cause** trong Gradle/JUnit report.
2. Xem failure xảy ra **khi stubbing**, **khi code under test chạy**, **lúc verify**, hay **MockitoExtension teardown**.
3. In/inspect actual invocations nếu cần, với dữ liệu an toàn.
4. Xác nhận đúng mock instance đang được inject vào SUT.
5. Nếu dùng Spring, phân biệt `@MockBean` trong context với `@Mock` chỉ nằm ở field test.
6. Kiểm tra argument type/value, whitespace, equals/hashCode, matchers và null behavior.
7. Xác nhận branch mà test chạy có thực sự đến dependency call không.
8. Nếu strict stubbing báo unused, xóa stub thừa trước khi cân nhắc lenient.
9. Nếu verify sai count, tìm retry/loop/duplicate listener và không tự giảm verification chỉ để pass.
10. Nếu spy/setup gọi method thật, chuyển sang doReturn/doThrow family.
11. Nếu async, đợi completion signal/future/transaction outcome trước verify; không dùng `Thread.sleep`.
12. Chạy riêng test và cả suite; kiểm tra JUnit report, Spring context cache/shared state và CI scheduling.

### Phân biệt compile failure với Mockito runtime failure

Nếu `when(repository.save(...))` không biên dịch do method `void`, Gradle fail ở `compileTestJava` và **JUnit chưa chạy**. Đừng tìm `UnnecessaryStubbingException` trong XML chưa được sinh. Nếu import `@MockitoBean` không tồn tại trên Boot 3.3, đó là version/API compile mismatch chứ không phải mock interaction problem.

## 35. Các anti-pattern nên tránh

| Anti-pattern | Vì sao nguy hiểm | Giải pháp |
| --- | --- | --- |
| Stub mọi dependency trong @BeforeEach | Strict unused + setup rối | Stub per test |
| `lenient` toàn class để test xanh | Che mismatch và unused stubs | Dùng selective leniency cực hiếm |
| Verify mà không gọi SUT | Không có invocation | Act trước Assert/Verify |
| Mock service thay vì dependency của service | Bỏ qua logic cần test | Dùng service thật, mock boundaries |
| `@Mock` trong Spring test nhưng @Autowired SUT | Không thay Spring bean | `@MockBean`/test configuration đúng |
| Verify mock instance khác | Interaction history nằm ở instance khác | Constructor injection, inspect actual wiring |
| Verify trước async completion | Race khiến flaky | Future/latch/await business state |
| `Thread.sleep` để chờ | Không deterministic, chậm CI | Signal có deadline |
| `when(spy.realCall())` trên side-effect method | Chạy real logic lúc setup | `doReturn`/`doThrow` |
| Dùng `any()` cho mọi argument | Test mất contract | `eq`/captor cho values quan trọng |
| Trộn matcher với raw argument | Mockito matcher misuse | `eq(raw)` cho các args còn lại |
| `verifyNoMoreInteractions` khắp nơi | Over-specify implementation | Chỉ verify critical calls |
| Tự tăng `times` khi fail | Có thể che duplicate charge/retry | Điều tra extra invocation |
| `reset(mock)` trước verify | Xóa invocation history | Bỏ reset không cần thiết |
| Default mock answer được xem là business success | Mock chưa stub vẫn trả empty/default | Explicit stub và assert outcome |
| Test assert chỉ call count, bỏ result | Có thể pass dù tính sai business logic | Assert return/error + invocation |
| Spring @MockBean configured sau context refresh | Không sửa startup side effects đã xảy ra | Test @Bean config từ trước hoặc refactor |
| Kết luận DB write từ verify(repo.save) | Mock no-op, không có DB transaction | Integration test DB thật |

## 36. Test boundaries và observability khi điều tra lỗi

Với Spring Boot, Mockito failure thường chỉ là một tín hiệu phụ; cần xác định lỗi **thật**:

- **Unit service**: assertion outcome và verify adapter call.
- **Spring context**: bean replacement/qualifier/proxy; startup logs nếu wiring fail.
- **HTTP layer**: MockMvc/WebTestClient xác minh request/response, không chỉ controller mock.
- **Persistence**: DB integration/transactions, không suy từ mocked repository.
- **Messaging**: producer send call khác consumer ACK/process; cần readiness/result.
- **Asynchronous**: future/latch completion, error propagation và execution-thread ownership.
- **Retry**: kiểm tra cả attempt count và final state.
- **Metrics**: Mockito verification không chứng minh Micrometer counter hay trace được ghi; cần test registry/observation handler khi thuộc requirement.

Khi debug trong CI, JUnit XML/HTML và full stacktrace giúp phân biệt exception xảy ra trong test method hay teardown của MockitoExtension. Với `UnnecessaryStubbingException`, assertion có thể đã pass nhưng extension báo lỗi sau test; đó vẫn là failed test và nên sửa setup.

## 37. Chạy project và xem reports

Nếu đã tạo Gradle Wrapper:

```bash
./gradlew clean test
./gradlew test --tests 'com.example.mockdiagnostics.ReservationServiceTest'
./gradlew test --tests 'com.example.mockdiagnostics.SpyDiagnosticsTest'
./gradlew test --tests 'com.example.mockdiagnostics.AsyncVerificationTest'
./gradlew test --tests 'com.example.mockdiagnostics.ReservationServiceSpringTest'
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test
.\gradlew.bat test --tests "com.example.mockdiagnostics.ReservationServiceTest"
```

Máy đã có Gradle tương thích nhưng chưa có Wrapper:

```bash
gradle clean test
```

Reports mặc định của Gradle `Test`:

```text
build/reports/tests/test/index.html
build/test-results/test/TEST-*.xml
```

**Tổng số method trong source: 15 phương thức `@Test`**, gồm 8 ReservationService unit, 2 spy, 3 async và 2 Spring Boot integration. Đây là **số đếm từ mã nguồn**, không phải kết quả 15 tests PASSED. Trong quá trình biên soạn bài **chưa chạy Gradle/JUnit thật**; chỉ xác nhận kết quả sau khi build reports được sinh và đọc.

### Khi test không compile

Kiểm tra Java 17, Spring Boot 3.3.5 Gradle plugin/dependencies, package/class filenames, static imports và `useJUnitPlatform()`. Nếu CI không tải được dependency hoặc toolchain, đó là build environment failure, không phải stubbing mismatch.

### Khi test run thành công nhưng HTML không có case mong đợi

Có thể filter `--tests` bỏ case, JUnit không discovery hoặc Gradle task UP-TO-DATE. Dùng `clean test` hoặc `--rerun-tasks` khi muốn kiểm chứng fresh run. Không suy “0 failures” thành “đã test hết” khi 0 methods được chạy.

## 38. Bài tập thực hành

1. Chạy unit tests; quan sát `@ExtendWith(MockitoExtension.class)` tự tạo mocks.
2. Cố ý chuyển một stub success vào `@BeforeEach` và chạy invalid-input test; đọc `UnnecessaryStubbingException`.
3. Stub `inventory.find("SKU-X")` nhưng gọi `reserve("SKU-Y",...)`; phân tích `PotentialStubbingProblem`.
4. Bỏ lời gọi `service.reserve` trước verify; đọc `Wanted but not invoked`.
5. Trong `repeatedCallsRequireExplicitCount` đổi `times(2)` thành mặc định; đọc invocation history.
6. Thêm một lần save ngoài ý muốn trong service; xem `verifyNoMoreInteractions` và count assertions phát hiện.
7. Đổi `Reservation` record thành class không override equals; dùng captor để kiểm tra fields thay vì identity.
8. Thử `anyString()` và `eq("SKU-1")`, kiểm tra argument contract không bị nới quá rộng.
9. Trộn `anyString()` và raw argument trong một method hai tham số; xem matcher misuse.
10. Thử `doThrow` trên void repository.save và assert exception propagation.
11. Dùng spy `StatefulFormatter` với `when` và `doReturn`; so sánh `calls()` ngay sau setup.
12. Thêm side effect network giả vào spy method và hiểu vì sao stubbing bằng `when` nguy hiểm.
13. Bỏ `@MockBean` khỏi Spring test nhưng vẫn inject Spring service, xem default adapter result và verify error.
14. Tạo hai beans cùng `InventoryClient` interface trong sandbox, kiểm tra @MockBean by name/qualifier.
15. Thử `@MockBean` stubbing tại test method khi dependency được gọi lúc context refresh; hiểu lifecycle limitation.
16. Trong AsyncVerificationTest, bỏ `done.get` và verify ngay; quan sát rủi ro race chứ không dùng sleep “sửa” nó.
17. Thêm một `CountDownLatch` gate để assert không có interaction trước khi release, sau đó verify một lần.
18. Thử `verify(sink, timeout(1000))`; giải thích vì sao nó không đảm bảo không có call thứ hai trong tương lai.
19. Mở JUnit HTML/XML sau một test fail ở MockitoExtension teardown, phân biệt stack location.
20. Thêm một real HTTP/DB integration test và xác định việc verify(mock) không chứng minh state thật.
21. Migrate project sang Spring Boot/Framework version mới trong sandbox, kiểm tra @MockBean/@MockitoBean đúng API.
22. Chạy cả suite theo nhiều JUnit/Gradle configurations và điều tra flaky nếu có.

## 39. Checklist QA trước khi merge

- [ ] Đã chọn đúng SUT thật và mock đúng collaborator boundary?
- [ ] Mocks được tạo bởi MockitoExtension hoặc Spring TestContext đúng lifecycle?
- [ ] Constructor/Spring bean thực sự nhận đúng mock instance?
- [ ] Mỗi stub được sử dụng bởi scenario của test?
- [ ] Không giữ stub dư trong @BeforeEach?
- [ ] Strictness không bị tắt toàn suite để che mismatch?
- [ ] Arguments stubbing khớp invocation thật; matcher type/null chính xác?
- [ ] Không trộn raw arguments với matchers sai syntax?
- [ ] Void method được stub bằng doThrow/doNothing khi cần?
- [ ] Spy được stub an toàn để tránh gọi real side effects lúc setup?
- [ ] Assertions về business output/error có mặt trước verify?
- [ ] Verify đúng method/args và counts theo business contract?
- [ ] Nếu nhiều invocations, đã xem retry/loop/callback trước khi đổi times?
- [ ] Có dùng ArgumentCaptor khi cần inspect object fields?
- [ ] InOrder chỉ kiểm tra thứ tự mà nghiệp vụ yêu cầu?
- [ ] verifyNoMoreInteractions không over-specify trivial methods?
- [ ] verifyNoInteractions/never chỉ được dùng khi boundary đã hoàn tất hoặc được gated?
- [ ] Async work được await bằng future/latch/result có timeout hữu hạn?
- [ ] Không dùng Thread.sleep hay stopwatch chính xác để chờ worker?
- [ ] @MockBean đúng Spring Boot 3.3 version, đúng bean type/name/qualifier?
- [ ] Không cấu hình stubs quá muộn sau Spring context refresh?
- [ ] Spring mock reset không bị nhầm với DB/cache cleanup?
- [ ] Test failure do compile/setup được phân biệt với Mockito runtime failure?
- [ ] Logs/mock diagnostics không chứa token/PII?
- [ ] Đã thực thi Gradle/CI và đọc JUnit reports trước khi tuyên bố PASS thật?

## 40. Tài liệu tham khảo

- [Mockito Core 5 — Mockito Javadoc](https://javadoc.io/doc/org.mockito/mockito-core/5.17.0/org.mockito/org/mockito/Mockito.html): stubbing, verification, spies, doReturn, lenient, timeout/after.
- [Mockito — MockitoExtension Javadoc](https://javadoc.io/doc/org.mockito/mockito-junit-jupiter/5.17.0/org.mockito.junit.jupiter/org/mockito/junit/jupiter/MockitoExtension.html): JUnit Jupiter lifecycle và strict stubbing.
- [Mockito — UnnecessaryStubbingException Javadoc](https://javadoc.io/doc/org.mockito/mockito-core/5.17.0/org.mockito/org/mockito/exceptions/misusing/UnnecessaryStubbingException.html): unused stubs và selective leniency.
- [Mockito — PotentialStubbingProblem Javadoc](https://javadoc.io/doc/org.mockito/mockito-core/5.17.0/org.mockito/org/mockito/exceptions/misusing/PotentialStubbingProblem.html): argument mismatch và strict stubbing.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@MockBean`, `@SpyBean`, Spring context/cache/reset.
- [Spring Boot 3.3 — MockBean Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/mock/mockito/MockBean.html): bean override và MockReset.AFTER.
- [Spring Framework 6.2 — MockitoBean and MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): migration context, không dùng trong Boot 3.3 project.
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/): JUnit `@Test`, extensions, parameterized/async test considerations.
- [Gradle — Testing in JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): `useJUnitPlatform`, test filters và HTML/XML reports.

## 41. Kết luận

**Một Mockito failure chỉ có thể được chẩn đoán chính xác khi tách ba bước: stub được khai báo, code under test thật sự gọi mock nào, và verify được thực hiện lúc nào.** Nếu `MockitoExtension` báo `UnnecessaryStubbingException`, ưu tiên xóa stub không cần; nếu báo mismatch, đối chiếu actual arguments; nếu `WantedButNotInvoked`, xác minh branch và mock instance trước khi thay verify. Với spy, `doReturn(...).when(spy)` tránh gọi real method lúc setup. Với Spring Boot 3.3, `@MockBean` thay collaborator trong ApplicationContext còn `@Mock` unit test không làm vậy.

**Đối với async**, luôn có completion signal có deadline rồi mới verify business interaction; `Mockito.timeout` chỉ là polling verification, không đồng nghĩa worker đã hoàn tất. Đừng tăng `times`, bật lenient toàn suite hoặc thêm `Thread.sleep` chỉ để làm bài test xanh. Mục tiêu là bảo vệ business contract bằng unit tests sạch, Spring wiring đúng, và hoàn thành QA bằng JUnit/Gradle reports **sau khi chạy thật**, không suy từ số test methods trong README.
