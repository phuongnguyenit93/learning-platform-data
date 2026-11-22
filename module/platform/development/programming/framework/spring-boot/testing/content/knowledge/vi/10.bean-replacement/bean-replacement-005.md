# Spy bean thật, tác động phụ và cách stub an toàn

## 1. Spy là gì, và vì sao “thay thế bean” không nhất thiết phải dùng mock hoàn toàn?

Trong dự án Spring Boot, có lúc cần giữ **phần lớn hành vi thật** của một Spring bean nhưng thay đổi hoặc quan sát **một số phương thức** trong lúc kiểm thử. Ví dụ, một service thực sự tính giá, validate và orchestration; chỉ một lời gọi tới gateway hoặc một phép tra cứu khó kiểm soát được thay bằng phản hồi cố định. Đây là tình huống của **spy** (*partial mock*).

Mockito có thể tạo spy của một object Java; Spring Boot Test 3.3.x cung cấp `@SpyBean` để áp dụng spy vào một bean trong `ApplicationContext`. Spy **khác mock mặc định** ở điểm rất quan trọng: **phương thức chưa stub thường gọi mã thật**. Vì thế spy có thể làm thay đổi state, gửi request, ghi cơ sở dữ liệu hoặc ném exception thực tế. Cần thận trọng cả trong **bước sắp đặt test (Arrange)**, chứ không chỉ khi thực thi hệ thống cần kiểm thử (Act).

Trong bài này:

- **Hành vi thật**: lời gọi vào phương thức của bean thật được chạy trừ khi đã stub.
- **Stubbing**: cấu hình Mockito để trả giá trị, ném lỗi, không làm gì hoặc dùng answer tùy biến cho invocation phù hợp.
- **Verification**: kiểm tra method đã được gọi với số lần/đối số mong muốn; không phải tự động gọi method thêm lần nữa.
- **Side effect (tác động phụ)**: ghi DB, thay đổi bộ đếm, gửi event, gọi HTTP, cập nhật cache hoặc những hành động khác ngoài việc tính toán giá trị trả về.
- **Stub an toàn**: thiết lập stub mà **không vô tình chạy method thật trong lúc cấu hình**, thông thường bằng nhóm API `doReturn`/`doThrow`/`doAnswer`/`doNothing`.

Mục tiêu của bài: hiểu rõ phạm vi spy, tạo và sử dụng `@SpyBean` đúng phiên bản, thấy được nguyên nhân nguy hiểm của `when(spy.method())`, thực hành các cách stub an toàn, thiết kế assertion cho side effect và biết lúc nào nên thay spy bằng mock.

## 2. Phân biệt mock, spy Java thuần và spy bean Spring

| Công cụ | Đối tượng được sử dụng | Lời gọi chưa stub | Có nằm trong Spring `ApplicationContext`? |
| --- | --- | --- | --- |
| `Mockito.mock(Foo.class)` | Mockito mock | Mặc định trả default value, không chạy mã thật | Không, trừ khi tự đăng ký vào context |
| `@Mock` với `MockitoExtension` | Mockito mock được khởi tạo cho test | Không chạy mã thật theo mặc định | Không tự thay Spring bean |
| `Mockito.spy(realObject)` | Mockito spy của object Java | Thông thường chạy mã thật trên spy | Không tự thay Spring bean |
| `@Spy` với `MockitoExtension` | Mockito spy cho field test | Thông thường chạy mã thật | Không tự thay Spring bean |
| `@MockBean` (Boot 3.3.x) | Mock được đăng ký/thay trong Spring Test context | Không chạy mã thật theo mặc định | **Có** |
| `@SpyBean` (Boot 3.3.x) | Spy áp dụng cho Spring bean trong Test context | **Chạy mã thật trừ khi stub** | **Có** |

Chọn theo hợp đồng muốn kiểm tra:

1. Muốn một **unit test thật sự cô lập** với gateway/DB? Mock collaborator rồi tạo service thật bằng constructor.
2. Muốn Spring dựng **bean thật** và chỉ quan sát vài phương thức? `@SpyBean` có thể phù hợp.
3. Muốn Spring dựng service thật, nhưng **không muốn gọi payment/email/HTTP thật**? Thường dùng `@MockBean` cho **dependency có side effect**, và chỉ dùng spy cho phần cần giữ logic thật.
4. Muốn xem một lời gọi có xảy ra mà không đổi hành vi? Spy và `verify(...)` có thể hữu ích, nhưng chỉ khi việc xác minh interaction đó có giá trị nghiệp vụ.

**Không đồng nhất `@Spy` với `@SpyBean`.** Nếu test có `@Autowired CheckoutService service`, rồi tạo một `@Spy PriceCalculator calculator` trong field khác, `service` chưa chắc đang dùng spy đó. Spring vẫn có thể inject một PriceCalculator thật khác từ context. `@SpyBean` làm việc ở cấp bean của Test context, nhờ đó service lấy dependency từ Spring có thể dùng spy mà test quan sát.

## 3. Bản chất: spy vẫn thực thi method thật

Với một mock bình thường:

```java
Calculator calculator = mock(Calculator.class);
int result = calculator.calculate(100); // Mặc định int -> 0
```

Với spy:

```java
Calculator calculator = spy(new Calculator());
int result = calculator.calculate(100); // Mã calculate(...) thật được chạy
```

Hai đoạn này là **cú pháp minh họa**; cần định nghĩa class `Calculator` và các import Mockito phù hợp nếu muốn chạy riêng.

Nếu `calculate(...)` gọi database, ghi audit hoặc thay đổi một biến, spy có thể thực hiện những hiệu ứng đó. Mockito **không biến method thật thành một hàm an toàn** chỉ nhờ bao nó bằng spy.

### Ba điểm dễ bỏ sót

**(1) Stubbing có thể gọi mã thật:** với spy, `when(spy.calculate(100)).thenReturn(110)` yêu cầu Java đánh giá `spy.calculate(100)` trước khi đi vào `when(...)`, vì thế method thật có thể chạy **ngay khi Arrange**.

**(2) Stub chỉ áp dụng khi invocation khớp:** nếu bạn stub `doReturn(110).when(spy).calculate(100)` nhưng SUT gọi `calculate(101)`, lời gọi `calculate(101)` vẫn có thể chạy thật.

**(3) Spy có thể quan sát, không nhất thiết cô lập:** việc viết `verify(spy).calculate(100)` chỉ xác nhận invocation đã được ghi nhận. Nó không xóa hoặc hoàn tác side effect đã xảy ra trước đó.

Với Spring bean còn có một điểm nữa: context được tạo trong bước thiết lập test. Tác động phụ ở `@PostConstruct`, bean initialization, `ApplicationRunner` hoặc listener lúc context refresh có thể xảy ra **trước khi test method kịp stub spy**.

## 4. Quy tắc quan trọng nhất: `when(...).thenReturn(...)` có thể nguy hiểm trên spy

Trong Mockito, hai cách sau thường giống nhau về kết quả trả về **khi method đã được stub**, nhưng **khác nhau ở thời điểm thiết lập**:

```java
// Có rủi ro: spy.method() thực thi ngay lúc stubbing.
when(spy.method(arg)).thenReturn(fakeValue);

// An toàn hơn cho spy: không gọi method thật lúc tạo stub.
doReturn(fakeValue).when(spy).method(arg);
```

Cả hai dòng là **mẫu cú pháp**, giả định `spy`, `method`, `arg`, `fakeValue` đã được định nghĩa. Không copy nguyên văn thành class Java độc lập.

**Vì sao khác nhau?** Trong biểu thức `when(spy.method(arg))`, Java phải gọi `spy.method(arg)` để lấy đối số đưa vào `when(...)`. Mockito ghi nhận lời gọi rồi gắn stubbing, nhưng với spy, lời gọi này mặc định đi tới real method. Với `doReturn(value).when(spy).method(arg)`, Mockito chuyển sang chế độ định nghĩa stub trước khi method matcher được gọi; real implementation không cần chạy trong bước này.

### Tình huống 1: method thật ném exception

Giả sử `spy` là một danh sách rỗng:

```java
List<String> spy = spy(new ArrayList<>());

// SAI: get(0) của list rỗng ném IndexOutOfBoundsException
// ngay ở lúc Arrange; test không kịp thiết lập stubbing.
when(spy.get(0)).thenReturn("thay thế");
```

Cách an toàn:

```java
List<String> spy = spy(new ArrayList<>());

doReturn("thay thế").when(spy).get(0);

assertEquals("thay thế", spy.get(0));
verify(spy).get(0);
```

Đây là các đoạn trích cần import `List`, `ArrayList`, `Mockito.spy`, `Mockito.doReturn`, `Mockito.verify` và `Assertions.assertEquals`. Ví dụ test hoàn chỉnh ở mục sau thực hiện ý tưởng tương tự.

### Tình huống 2: method thật có side effect

Giả sử `Gateway.charge(...)` sẽ thực hiện HTTP request thu tiền khi chạy thật. Câu lệnh:

```java
when(gatewaySpy.charge("order-1")).thenReturn("tx-test");
```

**có thể thu tiền ngay lúc chuẩn bị test**. Sau đó test có PASS cũng không có nghĩa side effect đã được chặn. Khi cần stub gateway trong spy:

```java
doReturn("tx-test")
        .when(gatewaySpy)
        .charge("order-1");
```

Tuy nhiên, một **mock hoàn toàn** thường là lựa chọn tốt hơn nếu không có lý do để giữ bất kỳ hành vi thật nào của gateway. Safe stubbing bảo vệ **invocation được stub**, không bảo đảm mọi method khác của spy sẽ không gọi hệ thống bên ngoài.

## 5. Chọn nhóm API doXxx cho spy

| Nhu cầu | API thường nên chọn | Lưu ý |
| --- | --- | --- |
| Method có return, muốn trả giá trị giả | `doReturn(value).when(spy).method(args)` | Không gọi real method trong lúc stubbing |
| Method phải ném exception mô phỏng | `doThrow(exception).when(spy).method(args)` | Hỗ trợ cả method `void` |
| Method `void` cần bỏ qua thực thi thật | `doNothing().when(spy).voidMethod(args)` | Có ích khi thật sẽ gửi email/event |
| Muốn logic phản hồi tự viết | `doAnswer(answer).when(spy).method(args)` | Không vô tình gọi method thật trừ khi answer chủ động làm vậy |
| Muốn trả lại việc chạy implementation thật | `doCallRealMethod().when(spy).method(args)` | Sử dụng có chủ đích; real method vẫn có thể tạo side effect |
| Muốn một method trả các kết quả nối tiếp | `doReturn(v1, v2).when(spy).method(args)` | Chỉ stub invocation khớp; kiểm tra retry/số lần |

Trên mock bình thường, `when(mock.method()).thenReturn(...)` thường dễ đọc và được dùng phổ biến. Trên **spy**, ưu tiên kiểu `doReturn` / `doThrow` / `doAnswer` để tránh gọi real method khi setup.

### Đánh đổi của doReturn

`doReturn` có thể kém kiểm tra kiểu hơn API `when(...).thenReturn(...)` tại thời điểm biên dịch do tham số là `Object`. Một số lỗi kiểu trả về chỉ lộ ra khi chạy test. Hãy giữ stubbing đơn giản, đúng type, không dùng `doReturn` một cách máy móc cho mọi mock.

### Không lạm dụng doNothing

Method `void` của một **mock thường** mặc định không làm gì, nên nhiều trường hợp không cần `doNothing()`. Với **spy**, method void chưa stub vẫn chạy thật. Nếu việc gọi method thật gửi email hoặc ghi dữ liệu, `doNothing().when(spy).send(...)` có tác dụng; nhưng nếu cả lớp gateway không cần chạy thật thì thay nó bằng mock sẽ an toàn và dễ hiểu hơn.

## 6. Dự án thực hành Spring Boot 3.3.x và Java 17+

Ví dụ dưới đây tạo các bean **thực sự nằm trong Spring context**, đồng thời cung cấp một bộ đếm nhỏ để quan sát tác động phụ. Nó không gọi network, database hay API thanh toán thực; vì vậy có thể học về spy mà không gây tác động bên ngoài.

Chọn Spring Boot **3.3.5** làm phiên bản minh họa, JDK 17+ và Gradle. Ở Boot 3.3.x sử dụng `org.springframework.boot.test.mock.mockito.SpyBean`. Với Boot 3.4 trở lên, API này bị deprecate để chuyển sang `@MockitoSpyBean` của Spring Framework; không tự đổi import khi project chưa dùng Framework 6.2+.

Cây thư mục:

```text
spy-bean-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/spylab/
│   ├── SpyLabApplication.java
│   ├── EffectRecorder.java
│   ├── QuoteCalculator.java
│   ├── ChargeGateway.java
│   ├── AuditPublisher.java
│   └── CheckoutService.java
└── src/test/java/com/example/spylab/
    ├── CheckoutSpyBeanTest.java
    └── PlainMockitoSpyTest.java
```

Tất cả file Java đặt đúng package `com.example.spylab`; file test ở cùng package giúp `@SpringBootTest` tự tìm class `@SpringBootApplication`.

### 6.1. Cấu hình Gradle

`settings.gradle`:

```groovy
rootProject.name = 'spy-bean-demo'
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
    }
}
```

`spring-boot-starter-test` cung cấp Spring Boot Test, JUnit Jupiter và Mockito. Không cần khai báo `MockitoExtension` thêm vào lớp `@SpringBootTest` chỉ để dùng `@SpyBean`.

Nếu dự án Spring Boot của bạn có BOM/plugin riêng, nên dùng dependency management hiện tại thay vì chép nguyên các phiên bản ở ví dụ. Cần kết nối Maven Central trong lần tải dependency đầu tiên và Gradle phù hợp với Boot 3.3.x.

### 6.2. Application root

`src/main/java/com/example/spylab/SpyLabApplication.java`:

```java
package com.example.spylab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SpyLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(SpyLabApplication.class, args);
    }
}
```

Không có HTTP server trong project này vì chỉ dùng `spring-boot-starter`, không thêm web starter.

### 6.3. Bộ ghi nhận side effect tách biệt với spy

`src/main/java/com/example/spylab/EffectRecorder.java`:

```java
package com.example.spylab;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class EffectRecorder {
    private final AtomicInteger quoteCalls = new AtomicInteger();
    private final AtomicInteger chargeCalls = new AtomicInteger();
    private final AtomicInteger auditCalls = new AtomicInteger();

    public void recordQuote() {
        quoteCalls.incrementAndGet();
    }

    public void recordCharge() {
        chargeCalls.incrementAndGet();
    }

    public void recordAudit() {
        auditCalls.incrementAndGet();
    }

    public int quoteCalls() {
        return quoteCalls.get();
    }

    public int chargeCalls() {
        return chargeCalls.get();
    }

    public int auditCalls() {
        return auditCalls.get();
    }

    public void reset() {
        quoteCalls.set(0);
        chargeCalls.set(0);
        auditCalls.set(0);
    }
}
```

Bộ đếm đóng vai trò bằng chứng độc lập về **real method có chạy hay không**. Nếu chỉ `verify(spy).method(...)`, ta biết Mockito có thấy lời gọi, nhưng không thể từ đó suy ra method đã bị chặn hay đã chạy thật. Với counter này, ta xác minh cả *invocation* và *side effect*.

Không dùng bộ đếm static chia sẻ toàn JVM; Spring context có thể được cache, nên test có `@BeforeEach` reset state. Trong ứng dụng thật, trạng thái persistent cũng cần cleanup/transaction phù hợp thay vì dựa vào Mockito reset.

### 6.4. Bean tính giá thật

`src/main/java/com/example/spylab/QuoteCalculator.java`:

```java
package com.example.spylab;

import org.springframework.stereotype.Component;

@Component
public class QuoteCalculator {
    private final EffectRecorder recorder;

    public QuoteCalculator(EffectRecorder recorder) {
        this.recorder = recorder;
    }

    public int totalCents(int subtotalCents) {
        recorder.recordQuote();

        if (subtotalCents < 0) {
            throw new IllegalArgumentException("negative subtotal");
        }

        return subtotalCents + subtotalCents / 10;
    }
}
```

Ví dụ `totalCents(100)` sẽ trả `110`, đồng thời tăng `quoteCalls`. Nếu method được stub an toàn bằng `doReturn(125)` cho đúng đối số, counter không tăng do real body không chạy. Đây chính là điều ta muốn quan sát.

### 6.5. Gateway và publisher thật nhưng an toàn trong sandbox ví dụ

`src/main/java/com/example/spylab/ChargeGateway.java`:

```java
package com.example.spylab;

import org.springframework.stereotype.Component;

@Component
public class ChargeGateway {
    private final EffectRecorder recorder;

    public ChargeGateway(EffectRecorder recorder) {
        this.recorder = recorder;
    }

    public String charge(int totalCents) {
        recorder.recordCharge();
        return "tx-live";
    }
}
```

`src/main/java/com/example/spylab/AuditPublisher.java`:

```java
package com.example.spylab;

import org.springframework.stereotype.Component;

@Component
public class AuditPublisher {
    private final EffectRecorder recorder;

    public AuditPublisher(EffectRecorder recorder) {
        this.recorder = recorder;
    }

    public void publish(String transactionId) {
        recorder.recordAudit();
    }
}
```

Đây là những **bean thật** nhưng chỉ tăng bộ đếm trong bộ nhớ, không gọi hệ thống thanh toán hoặc message broker. Trong production, lời gọi `charge(...)` hay `publish(...)` có thể gây side effect không thể hoàn tác; đó là lý do cần suy nghĩ kỹ trước khi áp dụng spy lên gateway thật.

### 6.6. Service điều phối nghiệp vụ thật

`src/main/java/com/example/spylab/CheckoutService.java`:

```java
package com.example.spylab;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final QuoteCalculator calculator;
    private final ChargeGateway gateway;
    private final AuditPublisher auditPublisher;

    public CheckoutService(
            QuoteCalculator calculator,
            ChargeGateway gateway,
            AuditPublisher auditPublisher) {
        this.calculator = calculator;
        this.gateway = gateway;
        this.auditPublisher = auditPublisher;
    }

    public Receipt checkout(int subtotalCents) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("negative subtotal");
        }

        int total = calculator.totalCents(subtotalCents);
        String transactionId = gateway.charge(total);
        auditPublisher.publish(transactionId);
        return new Receipt(total, transactionId);
    }

    public record Receipt(int totalCents, String transactionId) {
    }
}
```

Dòng chảy cần test:

```text
CheckoutService.checkout(100)
    ├── QuoteCalculator.totalCents(100)  -> 110
    │       └── recorder.quoteCalls += 1
    ├── ChargeGateway.charge(110)        -> "tx-live"
    │       └── recorder.chargeCalls += 1
    ├── AuditPublisher.publish("tx-live")
    │       └── recorder.auditCalls += 1
    └── Receipt(110, "tx-live")
```

Trong test dùng spy, bất kỳ phương thức nào **không được stub** vẫn thực hiện phần body thật, gồm cả các lời gọi đến `EffectRecorder`.

## 7. Bộ test Spring Boot hoàn chỉnh: 6 tình huống quan trọng

Tạo `src/test/java/com/example/spylab/CheckoutSpyBeanTest.java`:

```java
package com.example.spylab;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.SpyBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

@SpringBootTest
class CheckoutSpyBeanTest {

    @Autowired
    CheckoutService checkoutService;

    @Autowired
    EffectRecorder recorder;

    @SpyBean
    QuoteCalculator calculator;

    @SpyBean
    ChargeGateway gateway;

    @SpyBean
    AuditPublisher auditPublisher;

    @BeforeEach
    void resetRecordedEffects() {
        recorder.reset();
    }

    @Test
    void unstubbedSpyCallsRealMethods() {
        CheckoutService.Receipt result =
                checkoutService.checkout(100);

        assertEquals(
                new CheckoutService.Receipt(110, "tx-live"),
                result
        );
        assertEquals(1, recorder.quoteCalls());
        assertEquals(1, recorder.chargeCalls());
        assertEquals(1, recorder.auditCalls());

        verify(calculator, times(1)).totalCents(100);
        verify(gateway, times(1)).charge(110);
        verify(auditPublisher, times(1)).publish("tx-live");

        InOrder order = inOrder(calculator, gateway, auditPublisher);
        order.verify(calculator).totalCents(100);
        order.verify(gateway).charge(110);
        order.verify(auditPublisher).publish("tx-live");
    }

    @Test
    void doReturnStubsGatewayWithoutChargingDuringSetup() {
        doReturn("tx-test").when(gateway).charge(110);

        // Stubbing không gọi ChargeGateway.charge thật.
        assertEquals(0, recorder.chargeCalls());

        CheckoutService.Receipt result =
                checkoutService.checkout(100);

        assertEquals(
                new CheckoutService.Receipt(110, "tx-test"),
                result
        );
        assertEquals(1, recorder.quoteCalls());
        assertEquals(0, recorder.chargeCalls());
        assertEquals(1, recorder.auditCalls());

        verify(gateway, times(1)).charge(110);
        verify(auditPublisher).publish("tx-test");
    }

    @Test
    void doReturnStubsCalculatorWithoutExecutingRealCalculation() {
        doReturn(125).when(calculator).totalCents(100);

        assertEquals(0, recorder.quoteCalls());

        CheckoutService.Receipt result =
                checkoutService.checkout(100);

        assertEquals(
                new CheckoutService.Receipt(125, "tx-live"),
                result
        );
        assertEquals(0, recorder.quoteCalls());
        assertEquals(1, recorder.chargeCalls());
        assertEquals(1, recorder.auditCalls());

        verify(calculator).totalCents(100);
        verify(gateway).charge(125);
    }

    @Test
    void doThrowSimulatesGatewayFailureWithoutRealCharge() {
        doThrow(new IllegalStateException("gateway unavailable"))
                .when(gateway).charge(110);

        assertEquals(0, recorder.chargeCalls());

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> checkoutService.checkout(100)
        );

        assertEquals("gateway unavailable", error.getMessage());
        assertEquals(1, recorder.quoteCalls());
        assertEquals(0, recorder.chargeCalls());
        assertEquals(0, recorder.auditCalls());

        verify(gateway).charge(110);
        verifyNoInteractions(auditPublisher);
    }

    @Test
    void doNothingBlocksRealVoidPublisher() {
        doNothing().when(auditPublisher).publish("tx-live");

        assertEquals(0, recorder.auditCalls());

        CheckoutService.Receipt result =
                checkoutService.checkout(100);

        assertEquals(
                new CheckoutService.Receipt(110, "tx-live"),
                result
        );
        assertEquals(1, recorder.quoteCalls());
        assertEquals(1, recorder.chargeCalls());
        assertEquals(0, recorder.auditCalls());

        verify(auditPublisher, times(1)).publish("tx-live");
    }

    @Test
    void invalidInputNeverTouchesAnySpiedBean() {
        assertThrows(
                IllegalArgumentException.class,
                () -> checkoutService.checkout(-1)
        );

        assertEquals(0, recorder.quoteCalls());
        assertEquals(0, recorder.chargeCalls());
        assertEquals(0, recorder.auditCalls());

        verifyNoInteractions(calculator, gateway, auditPublisher);
    }
}
```

Chạy riêng class:

```bash
./gradlew test --tests "com.example.spylab.CheckoutSpyBeanTest"
```

Windows:

```powershell
.\gradlew.bat test --tests "com.example.spylab.CheckoutSpyBeanTest"
```

**Kỳ vọng: 6 test PASS** trên Spring Boot 3.3.5 với code đã cho. Các test không in stdout cố định. Gradle có thể hiển thị từng method `PASSED` nhờ cấu hình logging; HTML report ở `build/reports/tests/test/index.html`. Nếu chưa có Gradle Wrapper, dùng lệnh `gradle test` khi đã cài Gradle tương thích.

### Bảng kết quả kỳ vọng của 6 test

| Test | Return/exception | quoteCalls | chargeCalls | auditCalls |
| --- | --- | ---: | ---: | ---: |
| `unstubbedSpyCallsRealMethods` | `Receipt(110, "tx-live")` | 1 | 1 | 1 |
| `doReturnStubsGatewayWithoutChargingDuringSetup` | `Receipt(110, "tx-test")` | 1 | 0 | 1 |
| `doReturnStubsCalculatorWithoutExecutingRealCalculation` | `Receipt(125, "tx-live")` | 0 | 1 | 1 |
| `doThrowSimulatesGatewayFailureWithoutRealCharge` | `IllegalStateException` | 1 | 0 | 0 |
| `doNothingBlocksRealVoidPublisher` | `Receipt(110, "tx-live")` | 1 | 1 | 0 |
| `invalidInputNeverTouchesAnySpiedBean` | `IllegalArgumentException` | 0 | 0 | 0 |

Trong bảng, counter đo **lần real body chạy**, còn `verify(spy).method(...)` đo **invocation đã xảy ra trên spy**. Với method đã được stub, verify vẫn có thể PASS vì SUT vẫn gọi spy, trong khi bộ đếm side effect bằng 0. Phân biệt hai phép đo này là trọng tâm bài học.

### 7.1. Test 1: mặc định chạy real method

`unstubbedSpyCallsRealMethods` không thiết lập stub nào. Kết quả cho thấy bean trong Spring context vẫn làm phép tính, gọi gateway và publish. Spy không có nghĩa là mock an toàn. `InOrder` xác nhận thứ tự được yêu cầu: tính giá trước, charge sau, publish cuối. Chỉ kiểm tra thứ tự khi nghiệp vụ cần ràng buộc đó.

### 7.2. Test 2: doReturn ngăn tác động phụ ở bước Arrange và Act

`doReturn("tx-test").when(gateway).charge(110)` không làm tăng `chargeCalls` lúc setup. Khi checkout gọi `gateway.charge(110)`, Mockito trả "tx-test" mà không chạy `ChargeGateway.charge` thật. Dù vậy `QuoteCalculator` và `AuditPublisher` vẫn chạy thật, bởi chúng không được stub.

Đây là lý do **stub an toàn một method không làm toàn bộ luồng an toàn** nếu những collaborator khác vẫn có side effect. Trong production, nếu audit publisher phát message thật thì phải mock/stub riêng hoặc thiết kế test fixture cô lập.

### 7.3. Test 3: không làm phép tính thật nhưng vẫn chạy các bean còn lại

`doReturn(125).when(calculator).totalCents(100)` ngăn real body của calculator trong cả setup và invocation khớp. Checkout nhận giá 125, rồi gọi gateway thật với giá 125. Test dùng `verify(gateway).charge(125)` để xác minh tham số truyền sang bean kế tiếp; counter minh chứng gateway vẫn chạy.

Nếu muốn test “logic báo giá thật”, **không nên stub calculator** vì sẽ bỏ qua chính phần nghiệp vụ đang cần bảo vệ. Stubbing nên nằm ở dependency nằm ngoài phạm vi test.

### 7.4. Test 4: doThrow ngăn real charge nhưng vẫn test nhánh lỗi

`doThrow(new IllegalStateException(...)).when(gateway).charge(110)` không tự gọi charge thật khi sắp đặt. Khi SUT tới gateway, Mockito ném exception; audit không được gọi do luồng bị ngắt. Test dùng `assertThrows`, kiểm tra message, `verify(gateway)` và `verifyNoInteractions(auditPublisher)`.

Lưu ý code sample không có transaction hay cơ chế compensation. Trong ứng dụng thanh toán thật, một exception mạng có thể là **unknown outcome** (không biết đã charge hay chưa) thay vì “chắc chắn không charge”. Mockito chỉ giả lập phản hồi; muốn chứng minh retry an toàn phải có test ở mức provider/idempotency.

### 7.5. Test 5: method void cần doNothing nếu đó là spy

`AuditPublisher.publish(...)` trả `void`. Với spy, nếu không stub thì method chạy thật, tăng `auditCalls`. `doNothing().when(auditPublisher).publish("tx-live")` làm interaction vẫn được ghi nhận nhưng real body không chạy. Test chứng minh cả hai điều: `verify` PASS và counter vẫn 0.

Trên **mock** thuần, void method mặc định đã không làm gì. Không cần stubbing thừa nếu hành vi mặc định đáp ứng test.

### 7.6. Test 6: validation trước side effect

Với subtotal âm, `CheckoutService` ném exception ngay trước khi gọi calculator/gateway/publisher. Dùng `verifyNoInteractions(...)` bảo vệ ràng buộc “input không hợp lệ không được chạm tới dependency”. Thử cố ý đưa `calculator.totalCents(...)` lên trước validation: test sẽ FAIL vì spy bị gọi và side effect quote được ghi nhận.

## 8. Mockito.spy Java thuần: minh họa lỗi ngay lúc stub

Có thể học nguyên tắc an toàn của spy mà không tải Spring context. File sau là test JUnit độc lập trong cùng Gradle project:

`src/test/java/com/example/spylab/PlainMockitoSpyTest.java`:

```java
package com.example.spylab;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class PlainMockitoSpyTest {

    @Test
    void callingRealMethodDuringWhenCanFailBeforeAct() {
        List<String> spy = spy(new ArrayList<>());

        assertThrows(
                IndexOutOfBoundsException.class,
                () -> when(spy.get(0)).thenReturn("fake")
        );

        doReturn("fake").when(spy).get(0);

        assertEquals("fake", spy.get(0));
        // Lần gọi thực bị ném exception trước stubbing cũng có thể được Mockito ghi nhận;
        // không verify mặc định times(1) trên cùng spy tại đây.
    }

    @Test
    void unstubbedMethodsStillChangeSpyState() {
        List<String> original = new ArrayList<>();
        List<String> spy = spy(original);

        spy.add("real");
        assertEquals(List.of("real"), spy);

        // Mockito.spy(realObject) thông thường tạo spy
        // sao chép trạng thái tại thời điểm tạo.
        assertEquals(List.of(), original);
        verify(spy).add("real");
    }
}
```

Chạy:

```bash
./gradlew test --tests "com.example.spylab.PlainMockitoSpyTest"
```

**Kỳ vọng: 2 test PASS.** Test 1 **cố tình** dùng `assertThrows` để chứng minh `when(spy.get(0))` gọi thật và ném lỗi khi danh sách rỗng; sau đó dùng `doReturn` để stub an toàn. Test 2 cho thấy spy Java thuần không đồng nghĩa “delegating wrapper” tới đúng instance đã đưa vào: Mockito thông thường tạo một spy từ trạng thái của object, không bảo đảm sửa spy cũng sửa instance ban đầu.

**Giới hạn ví dụ:** chi tiết sao chép object của `Mockito.spy(realObject)` là hành vi Mockito ở ngữ cảnh spy Java thuần. `@SpyBean` tích hợp với **Spring bean lifecycle**, vì thế không được suy diễn máy móc rằng có thể gọi song song vào bean gốc đã bị thay và một spy độc lập như hai object Java thường.

Chạy toàn bộ hai test class:

```bash
./gradlew test
```

**Kỳ vọng: 8 test PASS** (6 Spring Boot Test + 2 Mockito Java thuần) với source đúng như trên. Chú ý đây là **kỳ vọng lý luận theo code**, không phải kết quả thực thi sẵn của một môi trường hiện hành.

## 9. @SpyBean trên Spring bean thật hoạt động thế nào?

Spring Boot Test 3.3.x thực hiện việc áp dụng Mockito spy qua hạ tầng test của Spring Boot. Điểm quan trọng đối với người dùng API:

1. `@SpringBootTest` tạo một `ApplicationContext` cho test.
2. Trong quá trình chuẩn bị context, hạ tầng Mockito test xử lý các khai báo `@SpyBean`.
3. Bean phù hợp trong context được spy; field test gắn `@SpyBean` được inject tham chiếu phục vụ stubbing và verification.
4. Những collaborator nhận bean đó từ Spring có thể tương tác qua spy trong khi thực thi.
5. Sau từng test, các spy/mocks trong Boot Test có thể được **reset** theo `MockReset`. Với `@SpyBean` của Boot 3.3.x, mặc định là `MockReset.AFTER`.

Điểm cuối **chỉ reset Mockito stubbing và invocation history**. Nó **không tự rollback database, không xóa message đã phát, không reset bộ đếm trong bean khác và không thay đổi state của mọi singleton**. Ví dụ phải gọi `recorder.reset()` vì `EffectRecorder` là Spring singleton chứa state mà Mockito reset của các spy không đụng tới.

### @SpyBean theo type hoặc name

Đặt trên field:

```java
@SpyBean
QuoteCalculator calculator;
```

Spring Boot suy ra bean type từ field. Nếu có **nhiều bean cùng type**, nên chọn đúng bean theo `name` hoặc qualifier phù hợp với cấu hình. Ví dụ:

```java
@SpyBean(name = "priorityQuoteCalculator")
QuoteCalculator calculator;
```

Đoạn thứ hai **chỉ minh họa cú pháp**, giả định context có bean tên `priorityQuoteCalculator`. Không thêm nó vào project mẫu trừ khi bạn chủ động tạo bean đó. Nếu chọn nhầm bean, SUT có thể vẫn dùng bean khác, khiến `verify` báo chưa được gọi.

Với bean chỉ được đăng ký trực tiếp như dependency không phải định nghĩa bean thông thường, Spring Boot có thể tạo thêm spied bean thay vì thay dependency đã biết; luôn kiểm tra collaborator được SUT thực sự inject.

### Một spy cho cả context, không phải một object mới theo từng test method

Các bean thông thường có scope `singleton` trong Spring context. TestContext có thể cache context cho nhiều test cùng cấu hình. Spy do Boot tạo được quản lý/reset theo lifecycle kiểm thử, nhưng **bean và state nghiệp vụ bên dưới** có thể được tái sử dụng. Đừng xem `@SpyBean` là cơ chế cô lập trạng thái test hoàn hảo.

Thực hành tốt: tránh trạng thái dùng chung không cần thiết, dùng test data riêng, transaction rollback hoặc cleanup phù hợp khi thao tác vào persistence. Nếu phải dùng `@DirtiesContext` để loại context khỏi cache, cân nhắc chi phí vì nó có thể khiến suite chạy chậm đáng kể.

## 10. AOP proxy: @Transactional, @Cacheable và sự phức tạp khi spy

Trong Spring, bean có thể đã được bọc bởi **AOP proxy** để thực hiện `@Transactional`, `@Cacheable`, `@Async`, security advice hoặc cross-cutting concern khác. Khi spy gặp proxy, cần phân biệt:

- Đối tượng proxy mà các bean khác nhìn thấy.
- Target object chứa logic nghiệp vụ.
- Điểm mà Mockito intercept một invocation.
- Advice của Spring có chạy trước/sau invocation hay không.

Đừng khẳng định “đã stub method nên không có side effect” cho **mọi lớp advice**. Safe stubbing giúp tránh chạy real **method body** trong lúc cấu hình trên spy thích hợp; một số proxy/advice có thể có hành vi riêng hoặc tạo context/transaction ở nơi khác.

### 10.1. proxyTargetAware của Spring Boot 3.3

`@SpyBean` có thuộc tính `proxyTargetAware` để giúp các API Mockito như `verify(...)` làm việc với target của AOP-advised bean. Nếu test không tìm được invocation trong khi app rõ ràng đã gọi qua Spring proxy, hãy kiểm tra:

- SUT có thực sự nhận đúng bean được spy không?
- Đây là JDK dynamic proxy hay CGLIB/class-based proxy?
- Mockito được gọi trên proxy hay trên target?
- `proxyTargetAware` đang dùng giá trị nào?
- Method được gọi từ bên ngoài proxy hay là self-invocation nội bộ?

Tùy trường hợp, Spring cung cấp `AopTestUtils.getTargetObject(...)` hoặc `getUltimateTargetObject(...)` trong `spring-test` để truy cập target phục vụ kiểm thử. Chỉ làm việc này khi thật sự cần và hiểu tác động của nhiều lớp proxy; không nên tháo proxy trong test thông thường rồi kết luận transaction/cache/security vẫn được kiểm chứng.

### 10.2. Self-invocation không giống external invocation

Ví dụ:

```java
@Service
public class ReportService {
    public void generate() {
        refreshCache(); // gọi nội bộ qua this
    }

    @Cacheable("reports")
    public String refreshCache() {
        return "ok";
    }
}
```

Đây là **đoạn minh họa**, không thuộc project chạy được ở mục 6–8; cần cấu hình cache và các import thích hợp. Lời gọi `refreshCache()` nội bộ có thể **bỏ qua proxy advice** theo cơ chế Spring AOP proxy-based. Không suy rằng spy sẽ luôn quan sát và stub mọi nhánh self-invocation như một lời gọi qua proxy từ collaborator. Nếu behavior của cache/transaction là hợp đồng, cần test từ ranh giới proxy thực và kiểm tra trạng thái/cache/DB thay vì chỉ verify một method nội bộ.

### 10.3. Spy trên @Transactional không hoàn tác side effect

Giả sử một real method mở transaction, gọi gateway thanh toán rồi ghi DB. Transaction rollback có thể hoàn tác DB trong một số điều kiện, nhưng **không hoàn tác charge đã xảy ra ở gateway ngoài transaction**. Dùng spy để thử đường lỗi phải cô lập các dịch vụ ngoài DB bằng mock/test double hoặc môi trường thử nghiệm an toàn.

Đặc biệt với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, request HTTP chạy ở thread server; `@Transactional` trên test method không tự đảm bảo rollback transaction bên server. Đây là ranh giới của integration test chứ không phải lỗi của Mockito.

## 11. @SpyBean so với @MockBean khi có side effect nguy hiểm

Tưởng tượng một hệ thống thanh toán:

```text
CheckoutService (thật)
  ├── FraudPolicy (logic thật)
  ├── PaymentGateway (HTTP charge thực)
  └── ReceiptPublisher (gửi message thực)
```

Bạn muốn kiểm tra service gọi fraud check, sau đó chỉ charge một lần và phát receipt nếu thành công. Một cấu hình **an toàn hơn** trong Spring Boot 3.3.x là:

```java
@SpringBootTest
class CheckoutIntegrationStyleTest {
    @Autowired
    CheckoutService checkoutService;

    @SpyBean
    FraudPolicy fraudPolicy; // Giữ logic thật để quan sát.

    @MockBean
    PaymentGateway paymentGateway; // Chặn gateway thật.

    @MockBean
    ReceiptPublisher receiptPublisher; // Chặn gửi event thật.

    @Test
    void chargesOnceAfterApproval() {
        // Stubbing gateway mock, gọi service, assert kết quả
        // và verify interaction theo hợp đồng.
    }
}
```

Đây là **ví dụ kiến trúc minh họa**, cần các class/domain/import thực của ứng dụng. Nó không chạy độc lập trong project mục 6 vì chưa định nghĩa `FraudPolicy`/`ReceiptPublisher`. Ý nghĩa là:

- **SUT và business policy** còn logic thật.
- **External side-effect collaborators** được mock hoàn toàn.
- Verify chỉ những interaction có ý nghĩa, ví dụ `verify(paymentGateway, times(1)).charge(...)`.
- Khi cần thay vài điều kiện của policy thật, có thể `doReturn(...)` trên spy với lời gọi phù hợp.

### Quy tắc an toàn khi quyết định spy hay mock

| Mục tiêu test | Lựa chọn thường tốt hơn |
| --- | --- |
| Unit test logic của CheckoutService | Service thật + Mockito mock dependencies, không nạp Spring |
| Kiểm tra bean wiring/DI của Spring | `@SpringBootTest` + test doubles cho gateway ngoài |
| Quan sát bean thật và chọn thay một method có thể kiểm soát | `@SpyBean`, stubbing doXxx có chủ đích |
| Không được để payment/email/HTTP thật xảy ra dưới bất kỳ nhánh nào | `@MockBean` hoặc sandbox/fake bảo vệ **mọi** đường đi |
| Kiểm tra @Transactional/@Cacheable/AOP | Spring test thực, assert effect ở boundary thay vì chỉ verify method |
| Test controller trả đúng HTTP status/JSON | `@WebMvcTest` + MockMvc + collaborator mock phù hợp |
| Kiểm tra hệ thống kết nối DB thực | Spring integration test + Testcontainers/test DB, fixture/cleanup rõ ràng |

Spy là công cụ đặc biệt có ích khi refactor legacy code hoặc khi cần giữ logic thật nhưng thay một điểm không ổn định. Với code được thiết kế tốt để test, constructor injection + mock boundary thường dễ bảo trì hơn.

## 12. Những giới hạn quan trọng của safe stubbing

### 12.1. Đối số phải khớp, nếu không real method vẫn chạy

Ví dụ:

```java
doReturn("tx-test").when(gateway).charge(110);

// Nhưng SUT lại gọi 115 vì input hoặc phép tính thay đổi.
checkoutService.checkout(105);
```

Đây là **phản ví dụ** dựa trên project mục 6: `checkout(105)` tính tổng `115` (chia nguyên), không khớp stub `charge(110)` nên `ChargeGateway.charge(115)` thật sẽ chạy. Với gateway bên ngoài thật, sự khác biệt nhỏ ở argument có thể tạo side effect rất nghiêm trọng.

Đừng che rủi ro này bằng `anyInt()` nếu muốn verify đúng giá tiền; tốt hơn là dùng **mock hoàn toàn** cho gateway. Nếu phải dùng matcher rộng trên spy, phải hiểu rõ những phương thức khác chưa được stub vẫn chạy.

### 12.2. Safe stubbing không chặn tác động khi khởi tạo context

Nếu bean có `@PostConstruct` gửi dữ liệu, test method chạy **sau** khi context đã được tạo. `doReturn(...).when(spy).method(...)` trong test không thể quay ngược thời gian để chặn `@PostConstruct`. Hãy tách tác động khỏi bean initialization, dùng cấu hình test/`@Profile`/`@ConditionalOn...` để tránh khởi tạo component nguy hiểm, hoặc thay dependency ngay khi tạo context.

### 12.3. Reset spy không reset state thực

Trong Boot 3.3.x, `@SpyBean` mặc định reset sau mỗi test method. Nó xóa stubbing/invocation của Mockito, **không xóa dữ liệu DB, cache, file hoặc counter** do real method thay đổi. Một test chỉ PASS khi chạy đơn lẻ nhưng FAIL trong suite thường do state bị để lại, không hẳn do Mockito quên reset.

### 12.4. Verify invocation không chứng minh side effect đã xảy ra hoặc bị chặn

Hai lời kiểm tra khác nhau:

```java
verify(gateway, times(1)).charge(110);
assertEquals(0, recorder.chargeCalls());
```

Cả hai có thể cùng PASS trong test doReturn: service đã gọi spy một lần, nhưng body thật của charge không chạy. Do đó, khi hợp đồng là “không gửi transaction thật”, chỉ verify số lần **không đủ**; cần kiểm tra boundary bên ngoài hoặc dùng mock thật sự cô lập gateway.

### 12.5. Stubbing một overload không tự chặn overload khác

Nếu class có `charge(int)` và `charge(Money)`, stubbing `charge(110)` không ảnh hưởng invocation `charge(new Money(...))`. Tương tự với một method tên khác hoặc các tham số không khớp matcher.

### 12.6. Final/static/private methods

Mockito hiện đại có nhiều khả năng mock final/static tùy mock maker và phiên bản; **không được** áp dụng máy móc các ví dụ cũ nói “mọi final method đều không spy được”. Tuy nhiên:

- Private method không phải public API để verify/stub trực tiếp như collaborator.
- Static mocking dùng API scoped khác như `MockedStatic`, không phải `@SpyBean` thông thường.
- Proxy Spring, final class/method và cách tạo bytecode có thể tương tác phức tạp.
- Nên đưa side-effect collaborator ra interface hoặc bean inject được thay vì phải spy private/static behavior.

### 12.7. Method async có thể chưa hoàn thành khi verify

Nếu `@Async` hoặc thread pool thực hiện side effect sau khi SUT trả về, gọi `verify(...)` quá sớm có thể cho kết quả sai. Chờ `CompletableFuture`/latch/signal hoàn thành theo hợp đồng, rồi verify. Đừng coi `Thread.sleep(100)` là giải pháp chắc chắn; test dễ flaky và không bảo vệ được side effect đến muộn.

## 13. Gắn với @WebMvcTest, @DataJpaTest và Spring TestContext

`@SpyBean` hoạt động với bean có mặt trong **test context** đang dựng. Nhưng một test slice chỉ tạo **một phần ứng dụng**:

- `@WebMvcTest` thường dựng phần MVC, controller, advice và các thành phần phù hợp với slice; service/repository bình thường có thể không có trong context.
- `@DataJpaTest` thường tập trung vào JPA entity/repository và phần cấu hình persistence phù hợp, không tự có mọi gateway/service.
- `@SpringBootTest` dựng context rộng hơn tùy cấu hình nguồn.

Nếu đặt `@SpyBean SomeService` vào một slice mà bean đó vốn không tồn tại, cơ chế của `@SpyBean` trong Boot 3.3 có thể thêm một bean spied instance, làm test có vẻ chạy nhưng thay đổi phạm vi slice. Điều này không tự chứng minh hệ thống production đã wiring đúng. Với controller test, mock service dependency thường là lựa chọn rõ ràng hơn. Với repository test, kiểm chứng DB state có thể giá trị hơn việc spy repository và verify từng query.

Khi gặp lỗi missing bean, xem lại **mục tiêu test** trước khi thêm spy để “cho context khởi tạo được”. Một spy có thể che dấu vấn đề cấu trúc test nếu nó không đại diện bean thật trong phạm vi đang kiểm tra.

## 14. Spring Boot 3.3 @SpyBean và Spring Framework 6.2 @MockitoSpyBean

API cần chọn theo **phiên bản thật của project**.

### Spring Boot 3.3.x

```java
import org.springframework.boot.test.mock.mockito.SpyBean;

@SpyBean
QuoteCalculator calculator;
```

Đây là annotation của **Spring Boot Test**. Nó tích hợp Mockito spy với `ApplicationContext` test và hỗ trợ cơ chế reset mặc định. Ví dụ hoàn chỉnh của bài dùng chính nhánh này.

### Spring Boot 3.4+ với Spring Framework 6.2+

`@SpyBean` và `@MockBean` của Spring Boot bị **deprecated từ 3.4** để chuyển sang các API của Spring Framework:

```java
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

@MockitoSpyBean
QuoteCalculator calculator;
```

Đoạn này là **cú pháp tương ứng cho stack có Spring Framework hỗ trợ**, không phải import dùng được trong Boot 3.3. Không mặc định sửa project từ `@SpyBean` thành `@MockitoSpyBean` khi chưa nâng cấp BOM.

**Quan trọng:** hai annotation không hoàn toàn tương đương về mọi hành vi. `@MockitoSpyBean` của Spring Framework dùng cơ chế **bean override WRAP** và yêu cầu bean phù hợp đã tồn tại; trong khi `@SpyBean` của Boot có thể bổ sung spy bean khi chưa có bean phù hợp theo quy tắc của nó. Kiểm tra qualifier/name, scope, tập bean bị áp dụng và context caching khi migrate.

Ở Spring Framework hiện đại, `@MockitoBean` thay bean bằng mock, còn `@MockitoSpyBean` wrap bean thật bằng spy. Không chuyển tùy tiện giữa hai loại vì sự khác biệt *chạy real method* là khác biệt về an toàn side effect.

## 15. Triệu chứng lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| DB bị ghi, email được gửi ngay lúc sắp đặt stub | `when(spy.method())` đã chạy real method | Đổi sang `doReturn`/`doThrow`/`doNothing` hoặc mock dependency |
| `IndexOutOfBoundsException` trước khi vào Act | Spy thực thi getter thật trên list rỗng | `doReturn(...).when(spy).get(0)` |
| `verify(spy)` báo “Wanted but not invoked” | SUT dùng bean/instance khác; proxy/target không khớp | Kiểm tra injection, bean name, AOP proxy |
| Test PASS riêng nhưng FAIL cùng suite | Real state không được reset; context cache tái sử dụng | Dọn fixture, reset state, cô lập test data |
| Bean thật vẫn gọi HTTP dù đã stub một method | Lời gọi khác method/khác argument, hoặc side effect ở bean khác | Mock boundary toàn phần; kiểm tra argument và mọi đường đi |
| Service thực không có trong `@WebMvcTest` | Slice không nạp service thông thường | Mock collaborator, import cấu hình cần thiết đúng mục tiêu |
| `NotAMockException` khi verify | Đang verify object thật/proxy sai hoặc spy không được inject | Kiểm tra Mockito spy và Spring proxy target |
| `UnnecessaryStubbingException` | Stub được thiết lập nhưng không dùng | Xóa stub thừa hoặc điều chỉnh đúng test case |
| AOP cache/transaction hoạt động không như dự đoán | Spy/proxy/self-invocation và advice làm đổi ranh giới | Test qua proxy công khai và assert effect ở boundary |
| Stub không chặn lời gọi lần thứ hai | Code dùng argument khác; method overload; spy reset | Xem invocation thực tế và matcher đúng contract |
| Không tìm thấy `@MockitoSpyBean` trong Boot 3.3 | Annotation thuộc Spring Framework mới hơn | Dùng `@SpyBean` đúng BOM hoặc nâng stack có chủ đích |

### Chiến lược debug theo thứ tự

1. **Đọc stack trace đầu tiên có ý nghĩa**. Lỗi ở lúc context refresh, Arrange/stubbing, Act hay Assert/Verify?
2. **Xác định instance thật đang dùng**: service lấy bean từ Spring hay object tạo thủ công bằng `new`? Type và name có đúng bean bị spy không?
3. **Kiểm tra lời stub**: dùng `when(spy.realMethod())` hay `doReturn(...).when(spy).realMethod()`?
4. **Kiểm tra matcher**: lời gọi thực có đúng các argument đã stub không? Nếu sai, spy có thể chạy thật.
5. **Kiểm tra mọi side-effect dependency**: chặn ở ranh giới payment/network/email/db để test an toàn.
6. **Kiểm tra state sau test**: Mockito reset khác với reset business state.
7. **Nếu có Spring AOP**, phân biệt proxy, target, self-invocation và advice.
8. **Rút gọn test**: nếu chỉ kiểm tra logic Java thuần, dùng mock collaborator và tránh full context.
9. **Xác minh bằng cả assertion và verify**: kết quả/exception có đúng không, side effect/call count có phù hợp không?
10. **Chạy lại cả nhóm test liên quan** để phát hiện context caching và state leakage.

## 16. Cách thiết kế bài test để ít giòn

Với logic nghiệp vụ, ưu tiên assert kết quả và trạng thái có thể quan sát được; verify lời gọi **khi đó là hợp đồng**, chẳng hạn “không charge hai lần” hoặc “không phát event khi gateway thất bại”.

**Test kém bền vững**:

```java
verify(service).calculateTax();
verify(service).normalizeName();
verify(service).buildRequest();
verify(service).save();
verifyNoMoreInteractions(service);
```

Đây là **phản ví dụ minh họa**, không phải đoạn độc lập có các class/method được định nghĩa. Nó khóa chặt implementation: refactor helper method có thể làm test FAIL dù nghiệp vụ không đổi.

**Test hướng hành vi**:

```java
CheckoutService.Receipt result = checkoutService.checkout(100);

assertEquals(110, result.totalCents());
verify(gateway, times(1)).charge(110);
```

Đây là đoạn rút ra từ test context ở mục 7; giả định các bean đã có và chưa bị stub khác. Nếu “đúng một lần charge” là điều kiện nghiệp vụ, `times(1)` bảo vệ nó. Nếu mục tiêu là “không charge thật”, phải assert counter/external fake state hoặc thay gateway bằng mock, bởi `verify` không ngăn charge.

Tránh spy chính **đối tượng đang test** nếu bạn có thể gọi real SUT và mock collaborators. Spy SUT làm test dễ biến thành kiểm tra internal call graph, trong khi mục tiêu cần bảo vệ là output hoặc side effect bên ngoài.

## 17. Checklist trước khi dùng spy bean thật

Trước khi chấp nhận một test có `@SpyBean`, trả lời:

1. **Lý do cần spy là gì?** Nếu chỉ cần fake return và verify call, mock có đủ không?
2. **Có side effect nguy hiểm nào trong method thật hoặc collaborator của nó?** DB, HTTP, email, queue, thanh toán?
3. **Stubbing có dùng doXxx không?** Tránh `when(spy.method())` gọi method thật lúc Arrange.
4. **Nếu argument không khớp, chuyện gì xảy ra?** Real method có thể chạy.
5. **SUT có nhận đúng bean được spy không?** Type, qualifier, name, Spring context?
6. **Test có dùng AOP proxy không?** `@Transactional`, `@Cacheable`, `@Async`, security advice?
7. **Bean có logic @PostConstruct hoặc init side effect không?** Test stub có thể đến quá muộn.
8. **State thật có được cleanup/reset không?** Mockito reset không đủ.
9. **Mọi thread/async task đã kết thúc trước verify chưa?**
10. **Có assert output/state bên cạnh verify interaction không?**
11. **Số lần/đối số/thứ tự được verify có thực sự thuộc contract không?**
12. **Stack đang dùng API nào?** Boot 3.3 `@SpyBean` hay Framework 6.2+ `@MockitoSpyBean`?

## 18. Bài thực hành có kiểm soát

Dùng code hoàn chỉnh ở mục 6–8:

1. Chạy toàn bộ test và xác nhận **8 test PASS**.
2. Trong `doReturnStubsGatewayWithoutChargingDuringSetup`, thử đổi dòng stub thành `when(gateway.charge(110)).thenReturn("tx-test")` **chỉ trên project sandbox**; dự đoán `recorder.chargeCalls()` tăng ngay trước khi gọi `checkoutService.checkout(...)`. Khôi phục `doReturn` sau khi quan sát.
3. Giữ `doReturn("tx-test").when(gateway).charge(110)` nhưng gọi checkout với một subtotal tạo ra total khác 110; chứng minh real `charge(...)` vẫn có thể chạy khi argument không khớp.
4. Trong `doNothingBlocksRealVoidPublisher`, bỏ `doNothing` và kiểm tra `auditCalls` chuyển từ 0 thành 1 như thế nào.
5. Trong `doThrowSimulatesGatewayFailureWithoutRealCharge`, kiểm tra rằng audit chưa được publish, dù calculator thật đã chạy.
6. Chuyển gateway sang `@MockBean` và cho stub thích hợp; giải thích vì sao mock an toàn hơn nếu gateway ngoài hệ thống có side effect nguy hiểm.
7. Giả định `QuoteCalculator` được `@Cacheable`; phân tích tại sao cần kiểm tra cả cache behavior qua Spring proxy chứ không chỉ verify một lần gọi nội bộ.
8. Giải thích vì sao Mockito reset của `@SpyBean` không thay thế `recorder.reset()` trong `@BeforeEach`.

Bài tập 2 và 3 cố tình minh họa **rủi ro** trên sandbox in-memory; không thử với gateway thanh toán, email hoặc database thật.

## 19. Tài liệu tham khảo theo phiên bản

- [Mockito — Spying on real objects và doReturn/doThrow](https://javadoc.io/doc/org.mockito/mockito-core/5.15.2/org.mockito/org/mockito/Mockito.html): giải thích real methods trên spy và những khác biệt của stubbing.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): mock/spy trong ApplicationContext, ảnh hưởng context cache, AOP proxy và test slices.
- [Spring Boot 3.3 — SpyBean API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/mock/mockito/SpyBean.html): `name`, `classes`, `reset`, `proxyTargetAware`.
- [Spring Framework — @MockitoBean và @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): cơ chế override/wrap bean trong TestContext hiện đại.
- [Spring Boot 3.4 Release Notes — Deprecations](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes): thay đổi API từ `@SpyBean` sang `@MockitoSpyBean`.

## 20. Tổng kết

**Spy giữ hành vi thật làm mặc định.** Khi áp dụng `@SpyBean` cho Spring bean trong Boot 3.3.x, một method chưa stub có thể thực thi nghiệp vụ và tạo side effect. Với spy, `when(spy.method())` có thể chạy real method ngay lúc chuẩn bị test; vì vậy **`doReturn`, `doThrow`, `doNothing` và `doAnswer` là các lựa chọn stubbing an toàn hơn** cho invocation cần thay đổi.

Dù stub đúng, các method khác hoặc invocation không khớp vẫn có thể chạy thật. Hãy kiểm tra đồng thời **kết quả trả về, lần gọi thực tế và side effect**, quản lý state xuyên test, phân biệt bean với AOP proxy và dùng mock hoàn toàn cho các dependency mà test tuyệt đối không được gọi thật. Spy hữu ích khi có mục tiêu rõ ràng, không phải thay thế mặc định cho thiết kế test cô lập.
