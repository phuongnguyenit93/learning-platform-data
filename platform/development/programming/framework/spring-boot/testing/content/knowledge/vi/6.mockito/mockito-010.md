# Khép phạm vi static mock và tránh làm rò trạng thái giữa các test với Mockito

`Mockito.mockStatic(...)` cho phép thay hành vi của phương thức `static` trong một khoảng thực thi được kiểm soát. Đây là công cụ hữu ích khi phải kiểm thử mã legacy hoặc một lời gọi static khó tách ngay khỏi nghiệp vụ. Tuy nhiên, nếu mở static mock rồi **không đóng**, hành vi giả lập có thể còn hiệu lực trên thread tạo mock, khiến test tiếp theo thấy kết quả sai, báo lỗi “static mocking is already registered in the current thread” hoặc trở nên phụ thuộc vào cách test runner tái sử dụng thread.

Bài học này giải thích vòng đời `MockedStatic<T>`, cơ chế đóng phạm vi bằng `try-with-resources` hoặc teardown có bảo đảm, cách kiểm chứng hành vi được khôi phục, giới hạn thread-local của Mockito và các lựa chọn thiết kế giảm sự phụ thuộc vào static mocking trong Spring Boot.

## 1. Vấn đề cần giải quyết: static mock là tài nguyên có vòng đời

Giả sử code nghiệp vụ gọi:

```java
int fee = RegionFees.baseFee("HCM");
```

Trong thực tế, `RegionFees.baseFee("HCM")` trả `18_000`. Test muốn giả lập một mức phí `4_000` để kiểm tra cách service sử dụng kết quả. Mockito có thể tạo bộ điều khiển:

```java
MockedStatic<RegionFees> staticFees = Mockito.mockStatic(RegionFees.class);
staticFees.when(() -> RegionFees.baseFee("HCM")).thenReturn(4_000);
```

Khi static mock còn **active**, lời gọi `RegionFees.baseFee("HCM")` trên thread đã tạo mock đi qua cơ chế stub của Mockito. Nếu không đóng `staticFees`, sự thay thế đó vẫn còn hiệu lực ở thread ấy sau khi test method kết thúc.

`MockedStatic<RegionFees>` không phải chỉ là một biến chứa dữ liệu mẫu; nó là **handle quản lý một scoped mock**. Mockito khuyến nghị đóng handle khi hoàn thành phần kiểm thử. Cách an toàn và dễ đọc nhất là `try-with-resources`, vì Java sẽ gọi `close()` khi rời khối, kể cả lúc có exception.

Cần phân biệt ba thứ:

| Thành phần | Vai trò | Khi kết thúc điều gì xảy ra? |
| --- | --- | --- |
| Phương thức `static` thật | Logic đang có trong mã ứng dụng | Vẫn tồn tại trong class; không bị viết lại vĩnh viễn |
| `MockedStatic<T>` | Bộ điều khiển việc giả lập static trong **scope/thread** tương ứng | `close()` kết thúc static mock đang active |
| Trạng thái thật bên ngoài mock | Static mutable field, cache, DB, file, Spring singleton… | **Không tự được reset** chỉ vì đóng `MockedStatic` |

Điểm cuối rất quan trọng: **đóng static mock phục hồi cơ chế gọi phương thức thật; không có nghĩa hoàn tác mọi side effect xảy ra trước đó**.

## 2. Static mock hoạt động trong phạm vi nào?

Theo contract của `MockedStatic` trong Mockito 5, static mock chỉ tác động đến **thread tạo ra nó** và không được dùng đối tượng `MockedStatic` từ thread khác. Vì vậy:

- Một `MockedStatic<T>` mở trên thread chạy JUnit có thể ảnh hưởng các lời gọi static tiếp theo **trên cùng thread** cho đến khi đóng.
- Một công việc chạy qua `CompletableFuture`, `@Async`, thread pool hoặc request thread khác **không mặc nhiên nhận stub** của thread JUnit.
- Không được chia sẻ cùng handle `MockedStatic` để gọi `when`, `verify` hoặc `close` qua nhiều thread; đây không phải tài nguyên thread-safe để sử dụng kiểu đó.
- Test runner có thể tái sử dụng thread cho nhiều test. Vì vậy rò static mock có thể ảnh hưởng test khác, nhưng **không được giả định mọi test đều chạy chung một thread** để giải thích mọi thất bại.

Phạm vi là **thread-local và theo thời gian còn active**, không phải “chỉ trong phương thức test” một cách tự động. Khối `try-with-resources` tạo ranh giới rõ ràng giữa phần giả lập và phần sử dụng hành vi thật.

### Trong scope, lời gọi static chưa được stub có gì khác?

Khi dùng `Mockito.mockStatic(RegionFees.class)` với default answer thông thường, phương thức static **không được stub** có thể trả giá trị mặc định của Mockito: `0` với `int`, `false` với `boolean`, `null` với nhiều kiểu tham chiếu. **Đừng mặc định những lời gọi khác sẽ chạy logic thật.**

Chẳng hạn, chỉ stub `RegionFees.baseFee("HCM")` thì `RegionFees.baseFee("HN")` trên thread mock có thể trả `0`, dù logic thật trả `22_000`. Cần thiết kế test kiểm tra đúng tác dụng phụ của việc thay thế. Nếu muốn giữ hành vi thật cho lời gọi không stub, có thể cân nhắc `Mockito.mockStatic(RegionFees.class, Mockito.CALLS_REAL_METHODS)`, nhưng phải đánh giá side effect của method thật, kể cả lúc thiết lập stub. Đừng dùng mặc định `CALLS_REAL_METHODS` mà chưa hiểu class được mock.

## 3. Cách ưu tiên: dùng `try-with-resources`

```java
assertEquals(18_000, RegionFees.baseFee("HCM")); // Hành vi thật.

try (MockedStatic<RegionFees> fees =
         Mockito.mockStatic(RegionFees.class)) {
    fees.when(() -> RegionFees.baseFee("HCM")).thenReturn(4_000);

    assertEquals(4_000, RegionFees.baseFee("HCM"));
    fees.verify(() -> RegionFees.baseFee("HCM"));
}

assertEquals(18_000, RegionFees.baseFee("HCM")); // Hành vi thật trở lại.
```

Đây là trích đoạn minh họa; các import và chương trình đầy đủ nằm ở phần 5. Đọc theo ba mốc: **trước scope** (18.000) → **trong scope** (4.000) → **sau scope** (18.000).

Lý do chọn `try-with-resources`:

1. `MockedStatic<T>` triển khai `AutoCloseable` qua `ScopedMock`; Java tự gọi `close()` ở cuối khối.
2. Nếu assertion thất bại hoặc code trong khối ném exception, trình tự thoát khối vẫn thực hiện đóng tài nguyên.
3. Mọi người đọc test nhìn thấy phạm vi tác dụng của stub ngay tại nơi tạo nó.
4. Test không cần giữ handle ở trường `static` hay ở một fixture sống qua nhiều test.
5. Test có thể assert hành vi thật sau scope để kiểm tra ranh giới vừa đóng đúng.

Giới hạn phạm vi **càng hẹp càng tốt**: bao toàn bộ test class hoặc `@BeforeAll` chỉ để stub một lời gọi trong một test khiến nhiều test khác vô tình chạy với hành vi giả.

## 4. Khi cần teardown thủ công: `@BeforeEach` đi với `@AfterEach`

Có trường hợp nhiều test trong một class cần tạo mock static theo cùng cách. Khi không thể đặt mỗi test trong `try-with-resources`, có thể mở scope trong `@BeforeEach` và đóng trong `@AfterEach`.

```java
private MockedStatic<RegionFees> fees;

@BeforeEach
void setUp() {
    fees = Mockito.mockStatic(RegionFees.class);
}

@AfterEach
void tearDown() {
    if (fees != null) {
        fees.closeOnDemand();
    }
}
```

Đây là **trích đoạn**, không phải một lớp test hoàn chỉnh; phần 5 có đầy đủ import. `@AfterEach` phải **đóng handle** thay vì chỉ gán `fees = null`. Gán `null` làm mất tham chiếu từ test nhưng không bảo đảm kết thúc bộ điều khiển static mock đã đăng ký với Mockito.

Sự khác nhau giữa các phương thức:

| API | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| `close()` | Đóng scoped mock; nếu đã đóng trước đó thì sẽ ném lỗi | `try-with-resources` hoặc teardown mà mỗi scope chỉ có một chủ sở hữu |
| `closeOnDemand()` | Đóng nếu còn active; không làm gì nếu đã đóng | Teardown cần chịu được tình huống scope đã được đóng sớm |
| `isClosed()` | Cho biết handle đã đóng chưa | Assertion chẩn đoán, không thay thế `close()` |
| `reset()` trên controller `MockedStatic` | Reset stubbing và lịch sử tương tác của **mock còn active** | Không dùng để kết thúc phạm vi |
| `clearInvocations()` | Xóa lịch sử invocation được ghi nhận | Không dùng để kết thúc phạm vi |

Theo JUnit Jupiter, `@AfterEach` vẫn được thiết kế để chạy sau từng lần thực thi test, kể cả khi test/assertion thất bại. Tuy vậy, khi phạm vi chỉ cần trong một đoạn, `try-with-resources` là cách gần vị trí sử dụng và ít đường rò hơn. Nếu setup có nhiều tài nguyên, nên quản lý việc dọn dẹp từng tài nguyên rõ ràng và tránh ghi đè một handle chưa đóng.

**Không nên chọn `@BeforeAll` + `@AfterAll` cho static mock của từng kịch bản**: scope khi đó kéo dài suốt lớp test. Những test không chủ định dùng stub có thể bị ảnh hưởng. Với test parallel, phạm vi thread-local còn làm cách mở ở một thread rồi sử dụng/đóng ở thread khác trở nên sai thiết kế.

## 5. Ví dụ hoàn chỉnh: Java 17+, Spring Boot và Mockito

Dự án nhỏ sau dùng Java 17, Spring Boot 3.3.5 và JUnit Jupiter. `spring-boot-starter-test` cung cấp Mockito cho test. Mockito 5 dùng inline mock maker theo cấu hình mặc định trên JVM thông thường, nên có thể mock static class do ứng dụng sở hữu. Ở Java 21+, có thể cần cấu hình instrumentation/Java agent rõ ràng tùy JDK và môi trường chạy; xem phần lưu ý môi trường ở cuối bài.

Quy tắc ví dụ:

- Phí theo vùng thông thường: HCM = 18.000, HN = 22.000, vùng khác = 30.000 (đồng).
- Đơn hàng trị giá **từ 200.000 trở lên**: miễn phí.
- Số tiền đơn hàng âm: ném `IllegalArgumentException`.
- Test có thể dùng static mock thay phí HCM thành 4.000 để xác nhận service sử dụng kết quả, sau đó phải trở về phí thực.

### 5.1. Cấu trúc tệp và Gradle

```text
settings.gradle
build.gradle
src/main/java/com/example/staticmock/StaticMockApplication.java
src/main/java/com/example/staticmock/RegionFees.java
src/main/java/com/example/staticmock/DeliveryQuoteService.java
src/test/java/com/example/staticmock/DeliveryQuoteServiceTest.java
src/test/java/com/example/staticmock/DeliveryQuoteSpringBootTest.java
src/test/java/com/example/staticmock/ExtensionManagedStaticTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'static-mock-scope'
```

**`build.gradle`**

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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Dùng Gradle Wrapper tương thích với Java 17. Phụ thuộc test của Spring Boot 3.3.5 quản lý các phiên bản JUnit/Mockito thích hợp cho bộ ví dụ, không cần tự trộn các phiên bản `mockito-core` và `mockito-inline`. Khả năng static mocking cần inline mock maker; từ Mockito 5, inline là mặc định trên JVM. Hệ thống có cấu hình `MockMaker` tùy chỉnh có thể thay đổi điều này.

**`src/main/java/com/example/staticmock/StaticMockApplication.java`**

```java
package com.example.staticmock;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StaticMockApplication {
    public static void main(String[] args) {
        SpringApplication.run(StaticMockApplication.class, args);
    }
}
```

**`src/main/java/com/example/staticmock/RegionFees.java`**

```java
package com.example.staticmock;

public final class RegionFees {
    private RegionFees() {
    }

    public static int baseFee(String region) {
        return switch (region) {
            case "HCM" -> 18_000;
            case "HN" -> 22_000;
            default -> 30_000;
        };
    }
}
```

Đây là class tiện ích có static method nhưng **không lưu mutable static state**. Switch expression dùng được ở Java 17. Ví dụ giả định `region` khác `null`; với `null`, switch trong code này không thuộc hợp đồng bài học.

**`src/main/java/com/example/staticmock/DeliveryQuoteService.java`**

```java
package com.example.staticmock;

import org.springframework.stereotype.Service;

@Service
public class DeliveryQuoteService {
    public int quote(String region, int orderAmount) {
        if (orderAmount < 0) {
            throw new IllegalArgumentException(
                    "orderAmount must be non-negative");
        }
        if (orderAmount >= 200_000) {
            return 0;
        }
        return RegionFees.baseFee(region);
    }
}
```

Service không giữ trạng thái. Mục tiêu static mock là **`RegionFees.baseFee`**, không phải `DeliveryQuoteService.quote`; test vẫn phải thực thi logic thật của service và assert đầu ra.

### 5.2. Test ưu tiên: scope rõ trong từng test method

**`src/test/java/com/example/staticmock/DeliveryQuoteServiceTest.java`**

```java
package com.example.staticmock;

import org.junit.jupiter.api.Test;
import org.mockito.MockedStatic;
import org.mockito.Mockito;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.times;

class DeliveryQuoteServiceTest {
    private final DeliveryQuoteService service =
            new DeliveryQuoteService();

    @Test
    void temporaryStaticFeeIsRestoredAfterScope() {
        assertEquals(18_000, service.quote("HCM", 100_000));

        try (MockedStatic<RegionFees> fees =
                     Mockito.mockStatic(RegionFees.class)) {
            fees.when(() -> RegionFees.baseFee("HCM"))
                    .thenReturn(4_000);

            assertEquals(4_000, service.quote("HCM", 100_000));
            fees.verify(() -> RegionFees.baseFee("HCM"), times(1));
        }

        assertEquals(18_000, service.quote("HCM", 100_000));
    }

    @Test
    void scopeIsClosedEvenWhenBlockThrows() {
        IllegalStateException failure = assertThrows(
                IllegalStateException.class,
                () -> {
                    try (MockedStatic<RegionFees> fees =
                                 Mockito.mockStatic(RegionFees.class)) {
                        fees.when(() -> RegionFees.baseFee("HN"))
                                .thenReturn(1_000);
                        assertEquals(1_000,
                                service.quote("HN", 100_000));
                        throw new IllegalStateException("simulated failure");
                    }
                });

        assertEquals("simulated failure", failure.getMessage());
        assertEquals(22_000, service.quote("HN", 100_000));
    }

    @Test
    void businessRuleDoesNotNeedStaticMock() {
        assertEquals(0, service.quote("HCM", 200_000));
        assertEquals(30_000, service.quote("OTHER", 150_000));
        assertThrows(IllegalArgumentException.class,
                () -> service.quote("HCM", -1));
    }
}
```

Test thứ nhất kiểm tra ba mốc **trước/đang/sau scope**. `verify(..., times(1))` yêu cầu service có gọi static method đúng một lần khi test gọi `quote` trong scope. Test thứ hai cố tình tạo exception **bên trong** khối để chứng minh `try-with-resources` vẫn đóng scope trước khi assertion bên ngoài kiểm tra giá trị thật 22.000. Test thứ ba dùng hành vi thật, giúp kiểm tra quy tắc miễn phí và phí mặc định.

**Dự kiến khi chạy mã nguyên bản:** ba test PASS. Đây là suy luận từ code được cung cấp, không phải kết quả lệnh Gradle đã quan sát trong môi trường này.

Lưu ý: dòng `RegionFees.baseFee("HCM")` trong lambda của `fees.when(...)` được Mockito sử dụng để **định nghĩa stubbing**, không nên suy ra nó là một lời gọi nghiệp vụ cần tính vào `verify(times(1))`. Test chỉ gọi `service.quote("HCM", 100_000)` một lần trong scope.

### 5.3. Khi cần `@BeforeEach`/`@AfterEach` cùng Spring Boot

**`src/test/java/com/example/staticmock/DeliveryQuoteSpringBootTest.java`**

```java
package com.example.staticmock;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.MockedStatic;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class DeliveryQuoteSpringBootTest {
    @Autowired
    private DeliveryQuoteService service;

    private MockedStatic<RegionFees> fees;

    @BeforeEach
    void openScope() {
        fees = Mockito.mockStatic(RegionFees.class);
    }

    @AfterEach
    void closeScope() {
        if (fees != null) {
            fees.closeOnDemand();
        }
    }

    @Test
    void hanoiFeeCanBeStubbedForThisTest() {
        fees.when(() -> RegionFees.baseFee("HN"))
                .thenReturn(2_000);

        assertEquals(2_000, service.quote("HN", 100_000));
    }

    @Test
    void hcmFeeCanBeStubbedForAnotherTest() {
        fees.when(() -> RegionFees.baseFee("HCM"))
                .thenReturn(7_000);

        assertEquals(7_000, service.quote("HCM", 100_000));
    }
}
```

`@SpringBootTest` khởi động application context rồi inject service. Mặc định JUnit Jupiter tạo test instance mới cho từng test method (`PER_METHOD`), nhưng **Spring context có thể được cache** giữa các method/class; việc tạo test instance mới không tự đóng static mock. Chính `closeScope()` mới kết thúc scoped mock của từng kịch bản.

Trong thiết kế này, các test được giả định chạy tuần tự trên thread thực thi các callback tương ứng. Nếu bật JUnit parallel execution hoặc chuyển tác vụ sang thread khác, cần đánh giá lại **chủ sở hữu thread** và việc mở/dùng/đóng static mock. Không sử dụng trường `static MockedStatic<...>` hoặc đưa handle cho các thread khác.

### 5.4. Tự động quản lý vòng đời bằng MockitoExtension

Mockito 5 cũng hỗ trợ tạo static mock được quản lý khi trường hoặc tham số có kiểu `MockedStatic<T>` được gắn `@Mock` và được xử lý bởi Mockito/JUnit extension tương ứng.

**`src/test/java/com/example/staticmock/ExtensionManagedStaticTest.java`**

```java
package com.example.staticmock;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.MockedStatic;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;

@ExtendWith(MockitoExtension.class)
class ExtensionManagedStaticTest {
    @Mock
    private MockedStatic<RegionFees> fees;

    @Test
    void extensionManagesStaticScope() {
        fees.when(() -> RegionFees.baseFee("HN"))
                .thenReturn(5_000);

        DeliveryQuoteService service = new DeliveryQuoteService();
        assertEquals(5_000, service.quote("HN", 100_000));
    }
}
```

Ở ví dụ này, MockitoExtension quản lý việc tạo và giải phóng mock theo test lifecycle. Không mở thêm một `Mockito.mockStatic(RegionFees.class)` của cùng class khi scope được extension tạo vẫn còn active; điều đó có thể gây xung đột đăng ký trên cùng thread.

Cơ chế `@Mock MockedStatic<T>` chỉ an toàn khi **extension/runner thật sự quản lý lifecycle**. Nếu tạo handle thủ công thì vẫn phải đóng thủ công hoặc dùng `try-with-resources`; một `@Mock` trên kiểu khác không khiến các static mock tự động được dọn.

## 6. Phản ví dụ: vì sao quên đóng làm rò state?

Đoạn sau **cố ý sai, chỉ để nhận diện anti-pattern**, không đưa vào bộ test runnable của phần 5:

```java
class LeakyStaticTest {
    @Test
    void stubsStaticAndForgetsCleanup() {
        MockedStatic<RegionFees> fees =
                Mockito.mockStatic(RegionFees.class);
        fees.when(() -> RegionFees.baseFee("HCM"))
                .thenReturn(0);

        assertEquals(0, RegionFees.baseFee("HCM"));
        // Không gọi fees.close(): static mock có thể còn active trên thread.
    }

    @Test
    void expectsRealFee() {
        assertEquals(18_000, RegionFees.baseFee("HCM"));
    }
}
```

Nếu test thứ hai chạy trên cùng thread **sau** test đầu, nó có thể thấy giá trị 0 do scoped mock bị bỏ quên và FAIL. Nếu khác thread hoặc chạy ngược thứ tự, test có thể xanh; đó là một dạng **flaky test/phụ thuộc thứ tự và lịch chạy**. Ngoài ra, một test khác cố `Mockito.mockStatic(RegionFees.class)` khi static mock cũ của cùng class còn active trên thread ấy có thể thất bại với lỗi kiểu “static mocking is already registered in the current thread”.

**Cách sửa ở chính nguyên nhân:** đặt `mockStatic` trong `try-with-resources`, hoặc ghép việc mở ở setup với `close`/ `closeOnDemand` trong teardown, hoặc dùng extension quản lý vòng đời. Không “chữa” bằng cách đổi `@TestMethodOrder` cho test mong chờ bị ảnh hưởng chạy trước, cũng không chỉ khởi động một JVM mới để che leak đang tồn tại.

### Test có assertion fail giữa chừng thì sao?

Nếu dùng kiểu thủ công:

```java
MockedStatic<RegionFees> fees = Mockito.mockStatic(RegionFees.class);
fees.when(() -> RegionFees.baseFee("HN")).thenReturn(1_000);
assertEquals(99_000, RegionFees.baseFee("HN")); // Chủ đích sẽ FAIL.
fees.close(); // Không chạy đến vì assertion đã FAIL.
```

thì lệnh `close()` phía sau assertion **không được thực thi**. Với `try-with-resources`, Java vẫn dọn scoped mock trong lúc thoát khối do assertion ném `AssertionFailedError`. Đây là một lý do then chốt để ưu tiên cú pháp ngôn ngữ thay vì phụ thuộc vào dòng lệnh cleanup cuối test.

Một cách thay thế rõ ràng nếu cần kiểm soát thủ công:

```java
MockedStatic<RegionFees> fees = Mockito.mockStatic(RegionFees.class);
try {
    fees.when(() -> RegionFees.baseFee("HN")).thenReturn(1_000);
    assertEquals(1_000, RegionFees.baseFee("HN"));
} finally {
    fees.close();
}
```

Các đoạn phản ví dụ ở đây là **trích đoạn** cần đặt trong lớp test có import thích hợp; không phải tệp Java độc lập. `try-with-resources` thường gọn và ít lỗi hơn.

## 7. Những API dễ bị nhầm với `close()`

`MockedStatic` có các thao tác để điều khiển stubbing/tương tác, nhưng **chỉ đóng scope mới giải phóng ảnh hưởng static mock**:

- `fees.when(...).thenReturn(...)` quy định hành vi trong scope.
- `fees.verify(...)` xác nhận lời gọi static có xảy ra như dự kiến.
- `fees.reset()` xóa cấu hình stubbing/lịch sử invocation của mock nhưng scope vẫn đang active; những lời gọi chưa stub có thể tiếp tục nhận default answer.
- `fees.clearInvocations()` xóa lịch sử xác minh, **không** trả method về logic thật.
- `fees.isClosed()` chỉ báo trạng thái, **không** dọn tài nguyên.
- `fees.close()` giải phóng scope; gọi lần thứ hai sẽ báo lỗi.
- `fees.closeOnDemand()` giải phóng nếu cần và an toàn khi đã đóng.
- `Mockito.reset(otherMock)` hoặc gán `fees = null` không phải cách kết thúc `MockedStatic` đang active.

Chẳng hạn, nếu reset một static mock rồi gọi `RegionFees.baseFee("HCM")`, method thật có thể **vẫn không được gọi** vì static mocking còn active. Vì vậy “test khác nhận phí 0” sau khi reset chưa chứng minh có bug trong production code; cần xác định có scoped mock nào chưa đóng hay không.

Đừng sử dụng thao tác xóa global framework state như một giải pháp thay thế mặc định cho một tài nguyên có chủ sở hữu xác định. Quản lý handle tại đúng nơi tạo nó giúp test độc lập và dễ truy lỗi.

## 8. Kết hợp với Spring Boot: context cache khác với static mock scope

Spring TestContext có thể **cache `ApplicationContext`** để giảm thời gian khởi động; bean singleton được tái sử dụng trong context tương ứng. Điều này độc lập với vòng đời `MockedStatic` của Mockito.

| Cơ chế | Đơn vị quản lý | Tình trạng sau test |
| --- | --- | --- |
| JUnit `PER_METHOD` | Đối tượng class test | Object test mới ở test khác; không giải phóng static mock bị mở sai |
| Spring TestContext cache | ApplicationContext và bean | Có thể tái sử dụng giữa test có cấu hình context tương đương |
| Mockito `MockedStatic` | Scoped mock trên thread tạo | Còn active đến khi `close`/`closeOnDemand` hoặc extension hoàn tất |
| Dữ liệu bên ngoài | DB, message broker, file, cache toàn cục | Cần cleanup/isolation riêng; không tự bị rollback khi đóng static mock |

`@DirtiesContext` yêu cầu Spring bỏ context bị đánh dấu bẩn, nhưng **không phải API để đóng `MockedStatic`**. Nếu dùng `@DirtiesContext` để thử “sửa” static mock leak, bạn có thể chỉ làm suite chậm hơn mà không giải quyết nguyên nhân.

Tương tự, `@MockBean` hoặc các cơ chế thay bean trong Spring context không tương đương với `Mockito.mockStatic`: một bên thay **Spring bean dependency** cho test context; một bên thay **lời gọi phương thức static trên thread**. Muốn kiểm tra static method được một service gọi, phải hiểu service thực thi trên thread nào. Một `MockMvc` setup có thể chạy trực tiếp pipeline MVC trong test thread, trong khi request qua server thật thường được xử lý trên thread server khác; không nên suy ra static mock của JUnit chắc chắn áp dụng cho cả hai.

**Không dùng static mock như cách thay cho toàn bộ quản lý trạng thái integration test.** Đóng scope không hoàn tác một transaction đã commit, không xóa file, không trả lại nội dung queue và không reset bộ đếm `static` thực sự bị thay đổi trước khi mock mở.

## 9. Static mock và chạy bất đồng bộ/song song

Mockito mô tả `MockedStatic` là scope gắn với thread khởi tạo. Hãy xét trích đoạn ý tưởng:

```java
try (MockedStatic<RegionFees> fees =
             Mockito.mockStatic(RegionFees.class)) {
    fees.when(() -> RegionFees.baseFee("HN")).thenReturn(1_000);

    // Thread test có static mock:
    assertEquals(1_000, RegionFees.baseFee("HN"));

    // Một worker thread khác thông thường dùng logic thật;
    // không suy diễn stub của thread test đã lan sang worker thread.
}
```

Nếu service chuyển xử lý sang `CompletableFuture.supplyAsync`, `@Async` hoặc thread do web server quản lý, stub mở ở JUnit thread **không tự được truyền sang thread ấy**. Đồng thời **đừng truyền cùng `MockedStatic` sang worker để `when`/ `close`**, vì API không được thiết kế để dùng từ thread khác.

Khi test cần kiểm soát một dependency được dùng trên nhiều thread, thay static call bằng **dependency có thể inject** (ví dụ interface `FeePolicy` hoặc `Clock` được tiêm qua constructor) sẽ đáng tin hơn. Dùng stub/mock ở cấp đối tượng đúng phạm vi và xử lý thread safety theo contract của dependency đó. Chỉ thay đổi JUnit thread scheduling để “cho stub hoạt động” có thể che lỗi thời điểm, không phải lời giải bền vững.

**Bật parallel execution:** với hai test cùng static mock một class nhưng chạy ở **hai thread riêng**, thread-local scope khiến chúng không nhất thiết xung đột chỉ vì cùng class. Nhưng nếu test lại chia sẻ một mock handle, mutable singleton, dữ liệu DB hoặc fixture, vẫn có thể xảy ra race condition. Không lấy đặc tính thread-local làm bảo đảm mọi test static mocking an toàn với parallelism.

## 10. Khi nào nên thay static mock bằng dependency injection?

Static mocking hợp lý khi đang làm việc với code legacy, một static adapter ít khi được chạm tới, hoặc chưa được phép refactor. Nhưng nếu một service ngày càng cần stub static utility về thời gian, random, trạng thái hệ thống, network, pricing hay feature flags, mock static có thể trở thành dấu hiệu **dependency bị ẩn trong mã nghiệp vụ**.

Thay vì:

```java
public int quote(String region, int orderAmount) {
    return RegionFees.baseFee(region);
}
```

có thể định nghĩa interface và inject dependency:

```java
public interface FeePolicy {
    int baseFee(String region);
}

@Component
public class DefaultFeePolicy implements FeePolicy {
    @Override
    public int baseFee(String region) {
        return RegionFees.baseFee(region);
    }
}

@Service
public class QuoteService {
    private final FeePolicy policy;

    public QuoteService(FeePolicy policy) {
        this.policy = policy;
    }

    public int quote(String region) {
        return policy.baseFee(region);
    }
}
```

Đây là các **trích đoạn thiết kế** đặt trong tệp/lớp riêng với import Spring thích hợp, không nằm trong danh sách tệp runnable của phần 5. Trong unit test, có thể tạo `FeePolicy policy = Mockito.mock(FeePolicy.class)`, stub `policy.baseFee("HCM")` và truyền policy vào `new QuoteService(policy)`. Khi đó test kiểm soát dependency **theo đối tượng và constructor**, không phải can thiệp vào phương thức static của cả thread.

Với mã mới, cấu trúc inject thường rõ ràng và dễ kiểm thử hơn. Với mã cũ chưa thay được, `try-with-resources` là ranh giới an toàn cần ưu tiên.

## 11. Cách chạy ví dụ và xác minh không rò state

Trong dự án có Gradle Wrapper, chạy:

```bash
./gradlew test --tests com.example.staticmock.DeliveryQuoteServiceTest
./gradlew test --tests com.example.staticmock.DeliveryQuoteSpringBootTest
./gradlew test --tests com.example.staticmock.ExtensionManagedStaticTest
./gradlew test
```

Trên Windows sử dụng `gradlew.bat test` với các tham số tương ứng. Khi code mẫu và môi trường đáp ứng điều kiện, các test được thiết kế để PASS. Output Gradle cụ thể phụ thuộc phiên bản/runner; không coi các lệnh trên là log đã thực thi.

Thứ tự chứng minh phù hợp:

1. Chạy unit test có scope: trong khối nhận fee giả, sau khối trả fee thật.
2. Thử test ném exception trong scope: ra khỏi khối vẫn phục hồi behavior thật.
3. Chạy Spring Boot tests nhiều method: scope mở trước từng test và đóng sau từng test.
4. Chạy cả suite và chạy lại từng test đơn lẻ: kết quả không phụ thuộc test khác khởi tạo mock trước.
5. Khi chuyển sang parallel hoặc async, xác minh rõ **thread nào thực thi lời gọi static**, không chỉ nhìn thấy stubbing trong một thread khác.
6. Nếu một test fail do trùng đăng ký static mock, điều tra scope bị mở và chưa đóng trong cùng thread, không chỉ xóa test đang báo lỗi.

Một kiểm tra phản chứng hữu ích là cố tình bỏ `try-with-resources` trong **bản thử nghiệm cô lập**, tạo static mock mà không đóng rồi chạy các test tuần tự trên cùng thread; bạn có thể thấy test sau nhận stub cũ hoặc xung đột đăng ký. Phục hồi cú pháp `try-with-resources` để sửa. Không đưa phản ví dụ này vào CI vì chính nó tạo nhiễu cho các test khác.

### Hạn chế môi trường cần biết

- Mockito 5 dùng inline mock maker mặc định trên JVM thông thường; nếu dự án ép mock maker khác hoặc chạy nền tảng không hỗ trợ instrumentation, static mocking có thể không khả dụng.
- Trên Java 21+, việc tự attach agent có cảnh báo/hạn chế của JDK; có thể phải cấu hình `mockito-core` như Java agent trong test JVM theo tài liệu phiên bản Mockito/JDK đang dùng. Đây là vấn đề **instrumentation**, khác hoàn toàn với lỗi không đóng `MockedStatic`.
- Một số class của JDK, class gắn chặt với classloader hoặc JVM intrinsics không phù hợp/không được phép static mock. Nên ưu tiên mock các class do ứng dụng sở hữu, như `RegionFees` trong ví dụ.
- Không nên đánh đồng “mock không hoạt động trên một worker thread” với “Mockito không hỗ trợ static mocking”; cần kiểm tra đúng thread, mock maker và scope.

Tham khảo tài liệu chính thức:

- Mockito `MockedStatic<T>`: https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/MockedStatic.html
- Mockito `ScopedMock` (`close`, `closeOnDemand`, `isClosed`): https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/ScopedMock.html
- Mockito `Mockito.mockStatic` và Java instrumentation: https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/Mockito.html

## 12. Checklist review một test có static mock

| Câu hỏi review | Yêu cầu đạt |
| --- | --- |
| Static mock được tạo ở đâu? | Có điểm mở scope rõ ràng trong test/setup |
| Ai chịu trách nhiệm đóng? | `try-with-resources`, `finally`, `@AfterEach` hoặc extension được cấu hình đúng |
| Khi assertion ném lỗi, scope có đóng không? | Cleanup vẫn chạy kể cả khi test fail |
| Có đóng mock ngay sau lúc cần không? | Scope nhỏ; không active suốt các test không liên quan |
| Có nhầm `reset` với `close` không? | Dùng `close`/`closeOnDemand` để kết thúc registration |
| Có mock nhiều lần cùng class trên một thread? | Không mở scope trùng khi scope trước chưa đóng |
| Các test có chia sẻ handle hoặc trường `static` không? | Không chuyển handle qua thread/test khác |
| Code dưới test có gọi async/server thread không? | Static stub được mở trên thread thực sự chạy lời gọi hoặc có thiết kế thay thế |
| Có kiểm tra behavior thật sau khi đóng không? | Khi phù hợp, assert giá trị thật được khôi phục |
| Đóng scope có đủ dọn state thật không? | DB, static mutable fields, cache và Spring bean được xử lý riêng nếu cần |

### Bài tập tự kiểm tra

**A.** Test mở `MockedStatic<RegionFees>` trong `@BeforeEach`, chỉ gán handle `null` ở `@AfterEach`. Có sạch scope không? **Không**: làm mất tham chiếu không thay việc giải phóng đăng ký static mock. Hãy gọi `close()` hoặc `closeOnDemand()`.

**B.** Test mở mock trong `try-with-resources`, assertion ném exception. Static mock có còn active sau khi thoát khối không? **Không**, Java tự đóng tài nguyên khi rời khối theo cơ chế `AutoCloseable` (bỏ qua các lỗi đặc biệt của chính thao tác cleanup). Đó là lợi ích của scope có quản lý.

**C.** `fees.reset()` rồi gọi phương thức static thật trong khi scope vẫn mở. Có bảo đảm logic thật được chạy không? **Không**; reset stubbing/invocation không phải đóng mock.

**D.** Test thread stub `RegionFees.baseFee("HN")`, nhưng service gọi method trên `@Async` worker. Có bảo đảm worker thấy stub không? **Không**; static mock của Mockito có phạm vi thread-local.

**E.** `@DirtiesContext` có phải giải pháp chuẩn cho static mock bị quên đóng? **Không**; nó liên quan Spring ApplicationContext cache, không giải phóng scoped mock của Mockito.

**F.** Bộ test xanh khi chạy riêng nhưng fail lúc chạy suite, đôi khi báo “static mocking is already registered”. Nên tìm gì trước? **Tìm static mock được mở trên thread tương ứng mà không được đóng**, đặc biệt các đoạn setup và nhánh test fail sớm; sửa bằng cleanup đúng phạm vi trước khi đổi test order.

**Kết luận:** Static mock là **tài nguyên có chủ sở hữu và vòng đời rõ ràng**. Dùng `try (MockedStatic<T> mock = Mockito.mockStatic(...)) { ... }` cho mỗi kịch bản là lựa chọn mặc định dễ kiểm chứng nhất. Với setup dùng chung, ghép mở scope cùng `@AfterEach` hoặc để MockitoExtension quản lý đúng lifecycle. Khi đóng scope, xác minh behavior thật đã trở lại, đồng thời nhớ rằng Spring context, dữ liệu thật và các worker thread có vòng đời riêng và cần được quản lý riêng.
