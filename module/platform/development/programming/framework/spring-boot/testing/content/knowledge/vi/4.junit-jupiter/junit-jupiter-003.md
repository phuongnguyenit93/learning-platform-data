# Vòng đời PER_METHOD, PER_CLASS và trạng thái dùng chung trong JUnit Jupiter

Một test có thể chạy độc lập hôm nay nhưng thất bại khi chạy cả suite vì các test đang vô tình chia sẻ trạng thái. Trong JUnit Jupiter, `@TestInstance` quyết định **JUnit tạo bao nhiêu đối tượng của lớp test**. Tuy nhiên, việc mỗi test có một đối tượng riêng **không tự cô lập** các trường `static`, Spring singleton bean, cơ sở dữ liệu, tệp, cache hay dịch vụ bên ngoài. Vì thế cần hiểu cả vòng đời test instance và nơi dữ liệu thực sự được lưu.

Bài này tập trung vào `TestInstance.Lifecycle.PER_METHOD` và `PER_CLASS`, thứ tự các lifecycle callback, hậu quả của mutable shared state, và cách kiểm thử Spring Boot mà không phụ thuộc vào test nào chạy trước.

## 1. Khái niệm: test instance là đối tượng nào?

Cho một lớp test:

```java
class PriceCalculatorTest {
    private int calls = 0;

    @Test
    void first() {
        calls++;
    }

    @Test
    void second() {
        calls++;
    }
}
```

Trường `calls` thuộc **đối tượng `PriceCalculatorTest`**, không phải thuộc từng phương thức. JUnit Jupiter phải quyết định có tạo một đối tượng mới trước khi chạy mỗi test, hay dùng chung một đối tượng cho các test trong lớp. Câu trả lời phụ thuộc vào **test instance lifecycle**.

| Thuộc tính | `PER_METHOD` | `PER_CLASS` |
| --- | --- | --- |
| Giá trị mặc định của JUnit Jupiter nếu không cấu hình khác | **Có** | Không |
| Số đối tượng lớp test | Mỗi test method/invocation có đối tượng mới | Một đối tượng dùng cho các test trong lớp |
| Trường instance thay đổi ở test trước | Không truyền qua đối tượng test kế tiếp | Có thể còn nguyên và ảnh hưởng test sau |
| `@BeforeEach` / `@AfterEach` | Chạy trước/sau mỗi test | Vẫn chạy trước/sau mỗi test |
| `@BeforeAll` / `@AfterAll` | Thông thường phải là `static` | Có thể là phương thức instance |
| Nguy cơ phụ thuộc thứ tự qua instance field | Thấp hơn, vì object mới | Cao hơn nếu state thay đổi mà không reset |
| Ảnh hưởng đến Spring singleton/DB/`static` | Không tự cô lập | Không tự cô lập |

JUnit Jupiter mặc định dùng `PER_METHOD` trừ khi lớp test hoặc cấu hình của JUnit Platform đã thay đổi lựa chọn đó. Có thể ghi rõ lifecycle ngay trên lớp để người đọc không phải đoán:

```java
@TestInstance(TestInstance.Lifecycle.PER_METHOD)
class ExampleTest {
    // Mỗi lần thực thi một test method có một đối tượng ExampleTest mới.
}
```

hoặc:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class ExampleTest {
    // Các test method trong lớp dùng chung một đối tượng ExampleTest.
}
```

**Hai ví dụ trên là trích đoạn minh họa**, cần import JUnit và định nghĩa test thực tế; phần 4 có các tệp hoàn chỉnh.

## 2. Trình tự vòng đời và các callback

Với lớp test thông thường, một chu kỳ của Jupiter gồm `@BeforeAll`, tạo/lấy test instance, `@BeforeEach`, chạy test, `@AfterEach` và cuối cùng `@AfterAll`. Vị trí tạo instance khác nhau theo lifecycle.

**`PER_METHOD` (mặc định):**

```text
@BeforeAll (static; một lần cho lớp)
    ├── new TestClass() -> @BeforeEach -> test A -> @AfterEach
    ├── new TestClass() -> @BeforeEach -> test B -> @AfterEach
    └── new TestClass() -> @BeforeEach -> test C -> @AfterEach
@AfterAll (static; một lần cho lớp)
```

**`PER_CLASS`:**

```text
new TestClass()  (một lần cho lớp)
@BeforeAll (được phép non-static)
    ├── @BeforeEach -> test A -> @AfterEach
    ├── @BeforeEach -> test B -> @AfterEach
    └── @BeforeEach -> test C -> @AfterEach
@AfterAll (được phép non-static)
```

Sơ đồ giả sử các test được chạy tuần tự và không biểu diễn thêm callback từ extension, lớp cha, interface hoặc nested tests. Không suy ra thứ tự A/B/C nếu **không có** cấu hình order rõ ràng.

Các annotation thực hiện vai trò khác nhau:

- **`@BeforeAll`** chạy một lần trước các test của container/lớp, phù hợp tạo fixture dùng chung hoặc chuẩn bị tài nguyên. Với `PER_METHOD`, phương thức này thông thường phải `static`; với `PER_CLASS` có thể truy cập instance field.
- **`@BeforeEach`** chạy trước từng phép thử, dùng để dựng hoặc reset trạng thái riêng của một test. Nó **vẫn** chạy cho mọi test khi `PER_CLASS`.
- **`@AfterEach`** chạy sau từng phép thử, thường dọn tài nguyên thuộc test hoặc kiểm tra hậu điều kiện.
- **`@AfterAll`** chạy một lần sau các test của container/lớp, thường giải phóng fixture dùng chung. Ràng buộc `static` tương tự `@BeforeAll`.
- **Constructor/instance field initializer** chạy mỗi lần JUnit tạo một test instance: nhiều lần trong `PER_METHOD`, một lần trong `PER_CLASS`.

Các lifecycle method của Jupiter không nên là `private` và phải có kiểu trả về `void`; JUnit cũng hỗ trợ parameter injection khi có resolver phù hợp. Nếu viết `@BeforeAll` là phương thức **non-static** trong lớp vẫn dùng `PER_METHOD`, JUnit sẽ báo lỗi lifecycle validation khi chạy test. Việc đổi sang `PER_CLASS` chỉ để “chữa lỗi static” có thể vô tình làm các trường mutable bị chia sẻ; hãy cân nhắc phạm vi tài nguyên trước.

## 3. Điều gì thực sự được chia sẻ?

Xét các loại trạng thái riêng biệt:

| Nơi lưu trạng thái | Được JUnit `PER_METHOD` làm mới? | Giải thích |
| --- | --- | --- |
| Instance field của lớp test | **Có** | Mỗi test nhận đối tượng lớp test mới và giá trị khởi tạo mới |
| Instance field của lớp test với `PER_CLASS` | **Không** | Cùng đối tượng được dùng suốt các test; phải tự reset nếu cần |
| `static` field | **Không** | Thuộc class, tồn tại độc lập với test instance |
| Đối tượng được giữ bởi static cache/singleton của ứng dụng | **Không** | Chỉ tạo mới test instance không làm mới dependency này |
| Spring singleton `@Autowired` | **Không bảo đảm** | Bean thuộc `ApplicationContext`; context có thể được cache và tái sử dụng |
| Dòng trong database, nội dung file, message queue | **Không** | Đây là state bên ngoài test instance; cần cơ chế isolate/cleanup riêng |
| Biến cục bộ trong một test method | **Tạo mới ở lần gọi mới** | Thường là cách dễ nhất để tránh test lây nhiễm nhau |

**Phân biệt “cùng instance” với “cùng dependency”:** Hai test method chạy với hai đối tượng test khác nhau vẫn có thể nhận cùng một singleton Spring bean qua `@Autowired`. Nếu bean thay đổi dữ liệu nội bộ, test sau có thể quan sát hiệu ứng từ test trước dù lớp test dùng `PER_METHOD`.

Đối tượng bất biến dùng chung (`String`, `List.of(...)`, `Map.of(...)` hoặc cấu hình chỉ đọc) thường an toàn hơn mutable fixture dùng chung. “An toàn hơn” ở đây là vì test không thay đổi được nội dung, chứ không phải vì `PER_CLASS` tự cung cấp isolation.

## 4. Ví dụ runnable: JUnit Jupiter và Spring Boot 3.3.x

Dự án mẫu dùng **Java 17+**, Gradle Groovy DSL, JUnit Jupiter trong `spring-boot-starter-test` và Spring Boot 3.3.5. Ví dụ chỉ sử dụng bộ đếm trong bộ nhớ để thấy rõ sự khác nhau giữa test instance và bean được Spring quản lý. Các test không cần database hoặc dịch vụ bên ngoài.

Bố cục:

```text
settings.gradle
build.gradle
src/main/java/com/example/lifecycle/LifecycleApplication.java
src/main/java/com/example/lifecycle/CounterService.java
src/test/java/com/example/lifecycle/PerMethodLifecycleTest.java
src/test/java/com/example/lifecycle/PerClassLifecycleTest.java
src/test/java/com/example/lifecycle/PerClassIsolatedTest.java
src/test/java/com/example/lifecycle/SpringContextSharedTest.java
src/test/java/com/example/lifecycle/SpringIndependentTest.java
```

### 4.1. Cấu hình dự án

**`settings.gradle`**

```groovy
rootProject.name = 'junit-lifecycle-evidence'
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

**`src/main/java/com/example/lifecycle/LifecycleApplication.java`**

```java
package com.example.lifecycle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LifecycleApplication {
    public static void main(String[] args) {
        SpringApplication.run(LifecycleApplication.class, args);
    }
}
```

**`src/main/java/com/example/lifecycle/CounterService.java`**

```java
package com.example.lifecycle;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;

@Service
public class CounterService {
    private final AtomicInteger value = new AtomicInteger();

    public int increment() {
        return value.incrementAndGet();
    }

    public int current() {
        return value.get();
    }

    public void reset() {
        value.set(0);
    }
}
```

`CounterService` mặc định là **singleton Spring bean** vì được khai báo `@Service`. `AtomicInteger` cho phép cập nhật số nguyên nguyên tử; nó không có nghĩa mỗi test được cấp một bộ đếm riêng và cũng không giải quyết mọi lỗi đồng thời của một kịch bản gồm nhiều thao tác.

### 4.2. `PER_METHOD`: đối tượng test mới, instance field mới

**`src/test/java/com/example/lifecycle/PerMethodLifecycleTest.java`**

```java
package com.example.lifecycle;

import java.util.List;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;

import static org.junit.jupiter.api.Assertions.assertEquals;

@TestInstance(TestInstance.Lifecycle.PER_METHOD)
class PerMethodLifecycleTest {
    private static List<String> categories;
    private int calls = 0;

    @BeforeAll
    static void prepareSharedReadOnlyFixture() {
        categories = List.of("standard", "express");
    }

    @BeforeEach
    void prepareEachTest() {
        assertEquals(0, calls);
        calls++;
    }

    @Test
    void firstScenario() {
        assertEquals(1, calls);
        assertEquals("standard", categories.get(0));
    }

    @Test
    void secondScenario() {
        assertEquals(1, calls);
        assertEquals("express", categories.get(1));
    }

    @AfterEach
    void checkEachTest() {
        assertEquals(1, calls);
    }

    @AfterAll
    static void verifySharedFixture() {
        assertEquals(2, categories.size());
    }
}
```

Dù test nào chạy trước, `calls` đều bắt đầu từ 0 vì mỗi test có một `PerMethodLifecycleTest` mới. `@BeforeEach` tăng `calls` thành 1, test và `@AfterEach` đều kiểm tra 1. Ngược lại, `categories` là `static` nên được chia sẻ giữa các test instance; trong ví dụ nó chứa danh sách bất biến và chỉ được đọc.

Đây là một ví dụ quan trọng về phạm vi: **`PER_METHOD` làm mới các trường instance của lớp test, không làm mới trường `static`.**

### 4.3. `PER_CLASS`: cùng đối tượng, thấy được thay đổi trước đó

**`src/test/java/com/example/lifecycle/PerClassLifecycleTest.java`**

```java
package com.example.lifecycle;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Order;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.TestMethodOrder;

import static org.junit.jupiter.api.Assertions.assertEquals;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class PerClassLifecycleTest {
    private int visits;

    @BeforeAll
    void initializeOnce() {
        visits = 0;
    }

    @BeforeEach
    void beforeEachScenario() {
        // Callback vẫn chạy trước từng test dù cùng một test instance.
    }

    @Test
    @Order(1)
    void firstScenario() {
        visits++;
        assertEquals(1, visits);
    }

    @Test
    @Order(2)
    void secondScenario() {
        visits++;
        assertEquals(2, visits);
    }

    @AfterAll
    void afterAllScenarios() {
        assertEquals(2, visits);
    }
}
```

Ở đây `@BeforeAll` và `@AfterAll` **không cần static** vì toàn bộ lớp dùng một instance. `visits` được tăng trong test thứ nhất, rồi test thứ hai nhìn thấy giá trị đó. `@TestMethodOrder(OrderAnnotation.class)` và `@Order` được dùng **chỉ để thí nghiệm có thứ tự rõ ràng**.

Đừng lấy kiểu phụ thuộc thứ tự trên làm mẫu kiến trúc thông thường. Nếu chạy một test lẻ bằng IDE, `secondScenario` có thể fail vì không có test đầu tiên tăng `visits`. Nếu một test thất bại trước khi cập nhật trạng thái, test sau cũng bị ảnh hưởng. Bộ test đáng tin cậy nên có thể chạy từng test độc lập.

### 4.4. `PER_CLASS` vẫn có thể giữ test độc lập

`PER_CLASS` phù hợp khi có fixture thật sự tốn kém và dùng chung một cách an toàn. Trong trường hợp mutable state thuộc từng kịch bản, tạo lại tại `@BeforeEach`.

**`src/test/java/com/example/lifecycle/PerClassIsolatedTest.java`**

```java
package com.example.lifecycle;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;

import static org.junit.jupiter.api.Assertions.assertEquals;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class PerClassIsolatedTest {
    private Map<String, Integer> fees;
    private List<String> visited;

    @BeforeAll
    void loadReadOnlyFixtureOnce() {
        fees = Map.of("standard", 30_000, "express", 50_000);
    }

    @BeforeEach
    void resetMutableState() {
        visited = new ArrayList<>();
    }

    @Test
    void standardScenario() {
        visited.add("standard");
        assertEquals(List.of("standard"), visited);
        assertEquals(30_000, fees.get("standard").intValue());
    }

    @Test
    void expressScenario() {
        visited.add("express");
        assertEquals(List.of("express"), visited);
        assertEquals(50_000, fees.get("express").intValue());
    }
}
```

`fees` được khởi tạo một lần bằng `Map.of` bất biến. `visited` là danh sách mutable được thay bằng instance mới trước **mỗi** test. Vì vậy hai test không phụ thuộc vào thứ tự gọi nhau, dù cùng dùng một instance `PerClassIsolatedTest`. Đây là cách dùng `PER_CLASS` có chủ đích hơn so với để một counter tăng xuyên suốt các test.

### 4.5. Trường hợp Spring Boot: `PER_METHOD` vẫn dùng chung singleton

**`src/test/java/com/example/lifecycle/SpringContextSharedTest.java`**

```java
package com.example.lifecycle;

import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Order;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.TestMethodOrder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@TestInstance(TestInstance.Lifecycle.PER_METHOD)
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class SpringContextSharedTest {
    @Autowired
    private CounterService counterService;

    private int personalMarker;

    @Test
    @Order(1)
    void firstJUnitInstanceChangesSpringSingleton() {
        assertEquals(0, personalMarker);
        counterService.reset();
        assertEquals(1, counterService.increment());
        personalMarker = 99;
    }

    @Test
    @Order(2)
    void secondJUnitInstanceSeesSameSpringSingleton() {
        assertEquals(0, personalMarker);
        assertEquals(1, counterService.current());
    }
}
```

JUnit tạo đối tượng `SpringContextSharedTest` khác nhau cho từng phương thức, nên `personalMarker` trong test thứ hai là 0 chứ không phải 99. Nhưng `counterService` được inject từ **Spring ApplicationContext** đang chạy: hai test vẫn nhận bean singleton thuộc context đó. Do đó test thứ hai có thể thấy giá trị 1 do test đầu tiên để lại.

Thí nghiệm cố ý dùng `@TestMethodOrder` để quan sát shared state một cách có thể dự đoán trong cấu hình chạy tuần tự. Đây **không phải** cách khuyến nghị để viết kiểm thử nghiệp vụ: nó chứng minh nguy cơ bị phụ thuộc vào test trước. Khi test chạy song song hoặc có tác nhân khác thay đổi singleton, thứ tự và kết quả có thể thay đổi.

**`src/test/java/com/example/lifecycle/SpringIndependentTest.java`**

```java
package com.example.lifecycle;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class SpringIndependentTest {
    @Autowired
    private CounterService counterService;

    @BeforeEach
    void resetSingletonBeforeEachScenario() {
        counterService.reset();
    }

    @Test
    void firstScenarioStartsFromZero() {
        assertEquals(0, counterService.current());
        assertEquals(1, counterService.increment());
    }

    @Test
    void secondScenarioAlsoStartsFromZero() {
        assertEquals(0, counterService.current());
        assertEquals(1, counterService.increment());
    }
}
```

Trong ví dụ chạy tuần tự này, reset ở `@BeforeEach` giúp mỗi kịch bản bắt đầu từ 0. Nhưng với hệ thống thật, một singleton đang được test đồng thời bởi lớp khác có thể bị reset giữa chừng; phương án mạnh hơn là **tránh dùng mutable singleton cho dữ liệu thuộc request/test**, hoặc cung cấp fixture/cơ chế isolation riêng. Trạng thái DB, message broker và file không được reset bởi phương thức `counterService.reset()`.

### 4.6. Cách chạy và bằng chứng mong đợi

Tạo Gradle Wrapper cho dự án hoặc dùng Wrapper có sẵn trong dự án mẫu. Từ thư mục gốc:

```bash
./gradlew test --tests com.example.lifecycle.PerMethodLifecycleTest
./gradlew test --tests com.example.lifecycle.PerClassLifecycleTest
./gradlew test --tests com.example.lifecycle.PerClassIsolatedTest
./gradlew test --tests com.example.lifecycle.SpringContextSharedTest
./gradlew test --tests com.example.lifecycle.SpringIndependentTest
./gradlew test
```

Trên Windows PowerShell/CMD, thay `./gradlew` bằng `gradlew.bat`. Khi không thay đổi cấu hình thực thi song song và code còn như trên, các assertion được thiết kế để **PASS**. Đây là **kỳ vọng từ mã mẫu**, không phải log Gradle thực tế được trích lại.

`PerMethodLifecycleTest` cho thấy `calls` luôn là 1 sau setup; `PerClassLifecycleTest` cho thấy `visits` đi từ 1 tới 2 theo order minh họa; `PerClassIsolatedTest` cho thấy `visited` mới cho từng test; `SpringContextSharedTest` cho thấy instance test mới vẫn nhìn thấy state của singleton; `SpringIndependentTest` minh họa reset tại `@BeforeEach`.

Bạn có thể thử bỏ `@TestMethodOrder` ở `PerClassLifecycleTest` hoặc chạy riêng `secondScenario`: việc kỳ vọng “2” lập tức trở nên không chắc chắn. Đó chính là dấu hiệu cần loại bỏ phụ thuộc thứ tự, thay vì chỉ bổ sung annotation order.

## 5. `@TestInstance` ảnh hưởng thế nào đến parameterized và repeated tests?

JUnit Jupiter dùng `PER_METHOD` cho mỗi lần thực thi test method, bao gồm từng invocation của `@ParameterizedTest` hoặc từng lần lặp của `@RepeatedTest`. Do đó khi cùng một parameterized method chạy với nhiều input, instance field thường lại bắt đầu từ giá trị khởi tạo ở mỗi invocation. Với `PER_CLASS`, mọi invocation dùng chung một instance nên một trường mutable có thể tích lũy giá trị.

Ví dụ bổ sung cho dự án trên:

```java
package com.example.lifecycle;

import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertEquals;

@TestInstance(TestInstance.Lifecycle.PER_METHOD)
class ParameterizedLifecycleTest {
    private int seen;

    @ParameterizedTest
    @ValueSource(ints = {1, 2, 3})
    void freshInstanceForEachInvocation(int input) {
        assertEquals(0, seen);
        seen++;
        assertEquals(1, seen);
        assertEquals(1, Integer.signum(input));
    }
}
```

Với annotation `PER_METHOD`, assertion `seen == 0` đầu invocation luôn đúng; `input` lần lượt là 1, 2, 3 nhưng thứ tự invocation không phải điều mà logic test phụ thuộc vào. Nếu chuyển sang `PER_CLASS` và **không reset `seen`**, test trên có thể fail từ invocation sau vì state đã đổi. `@BeforeEach` vẫn được chạy cho mỗi invocation để dựng trạng thái riêng khi cần.

Một ngoại lệ nâng cao đáng nhớ: các test được sinh bằng `@TestFactory` (`DynamicTest`) có quy tắc lifecycle khác test thường; `@BeforeEach` và `@AfterEach` bao quanh **factory method**, không tự chạy cho từng `DynamicTest` sinh ra. Vì vậy không dùng mô hình “mỗi dynamic test có callback riêng” khi thiết kế reset state.

## 6. Phân biệt test instance lifecycle với Spring TestContext cache

Đây là hai cơ chế có phạm vi và chủ sở hữu khác nhau:

| Cơ chế | Ai quản lý? | Đơn vị tái sử dụng | Cách chủ động kiểm soát |
| --- | --- | --- | --- |
| `PER_METHOD` / `PER_CLASS` | JUnit Jupiter | **Object của lớp test** | `@TestInstance`, `@BeforeEach`, `@BeforeAll` |
| Spring TestContext cache | Spring Test | **`ApplicationContext` và bean bên trong** | Cấu hình context, `@DirtiesContext`, tránh shared mutable bean |
| Giao dịch trong integration test | Spring transaction/test framework hoặc DB | **Dữ liệu và transaction** | Fixture, rollback khi phù hợp, cleanup rõ ràng |
| Static/cache ngoài Spring | JVM hoặc thư viện | **Classloader/process/resource** | Clear/restore hoặc thiết kế không giữ state |

Khi hai lớp `@SpringBootTest` có cấu hình context tương đương, Spring TestContext framework có thể dùng context đã cache. Test method trong cùng lớp cũng thường dùng context ấy. `@TestInstance(PER_METHOD)` chỉ tác động object test, **không buộc Spring tạo context mới**.

Trong một số trường hợp cần context khác vì test đã làm thay đổi cấu hình/bean không thể reset, có thể dùng:

```java
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
```

(Trích đoạn annotation; import từ `org.springframework.test.annotation.DirtiesContext`.) Đây là yêu cầu Spring loại context bị đánh dấu bẩn khỏi cache rồi dựng lại khi cần; nó có thể làm test **chậm rõ rệt**, nên không phải cách mặc định để đạt isolation. Đối với state trong DB, `@DirtiesContext` cũng **không tự xóa toàn bộ dữ liệu** của một database độc lập.

Một số Spring integration test dùng `@Transactional` và mặc định rollback giao dịch do test quản lý sau method; nhưng việc rollback phụ thuộc test transaction thực sự bao quanh thao tác. Khi test mở web server thật và gọi HTTP qua thread/transaction khác, không được giả định request server đã nằm trong transaction của test để tự rollback. Cần xác minh setup, commit, cleanup và transaction boundary của chính kịch bản đó.

**Đặc biệt với `PER_CLASS` + Spring:** injection vào instance chỉ xảy ra trong vòng đời của instance ấy. Nếu test chủ động làm bẩn/thay context giữa các phương thức, tham chiếu bean lưu trên instance dùng chung có thể trở nên lỗi thời tùy cách injection và context recreation. Nên ưu tiên `PER_METHOD` cho các test đòi hỏi context thay đổi thường xuyên, hoặc xây dựng fixture phù hợp và kiểm chứng dependency được cấp lại chính xác.

## 7. Làm thế nào để tránh flaky test và test phụ thuộc thứ tự?

Một bài test độc lập phải có khả năng chạy một mình hoặc nằm trong cả suite mà vẫn đạt cùng kết quả trên cùng điều kiện đầu vào. Các chiến lược thực hành:

1. **Chọn `PER_METHOD` mặc định** nếu không có lý do chắc chắn dùng `PER_CLASS`. Đặt dữ liệu biến thiên vào biến cục bộ, constructor của object được test, hoặc `@BeforeEach`.
2. **Nếu chọn `PER_CLASS`, tách tài nguyên read-only dùng chung khỏi state của từng ca.** Dựng fixture tốn kém một lần bằng `@BeforeAll`, nhưng reset hoặc tạo mới các collection mutable trước từng test.
3. **Không dùng `@Order` để che test dependency.** Order hợp lý cho các ví dụ đào tạo hoặc một bài kiểm thử có chủ đích về chuỗi trạng thái, nhưng không giải quyết được lỗi test thứ hai chỉ qua khi test thứ nhất chạy trước.
4. **Kiểm soát state bên ngoài test instance.** Không để static counter, singleton Spring, cache, database, queue hoặc file tạm dính dữ liệu sang test khác. Chọn reset, unique key/namespace, rollback được xác minh hoặc fixture độc lập theo nhu cầu.
5. **Dọn tài nguyên có vòng đời rõ ràng.** `@AfterEach` dọn tài nguyên thuộc một test; `@AfterAll` dọn fixture chung. Dọn tài nguyên nên bảo đảm không xóa dữ liệu của test khác, nhất là khi chạy song song.
6. **Chạy thử từng test riêng, cả class và cả suite.** Nếu kết quả thay đổi theo tập test chạy cùng, kiểm tra state leak trước khi nghi ngờ JUnit “chạy sai”.
7. **Bật chạy song song có chủ đích.** Một test đang xanh theo thứ tự tuần tự có thể có race condition khi nhiều test tác động cùng một singleton hay static field.

Với JUnit Jupiter, có thể cấu hình chạy song song bằng các thuộc tính `junit.jupiter.execution.parallel.*`. Nhưng `PER_CLASS` và test method ordering có những quy tắc mặc định bảo thủ hơn cho concurrency; khi cố tình dùng `@Execution(ExecutionMode.CONCURRENT)` hoặc cấu hình tương ứng, phải bảo vệ mutable shared state bằng isolation hoặc đồng bộ phù hợp. **Một `AtomicInteger` chỉ khiến thao tác tăng số an toàn ở mức nguyên tử, không bảo đảm các chuỗi “reset → increment → assert” của hai test độc lập không xen vào nhau.**

Nếu muốn kiểm tra một quy trình có trạng thái theo nhiều bước, cân nhắc đặt tất cả các bước cần thứ tự **bên trong một test method** với các assertion ở mỗi mốc, hoặc dùng fixture/đối tượng mới cho mỗi kịch bản. Chỉ chia quy trình thành nhiều `@Test` phụ thuộc nhau nếu thực sự cần và chấp nhận giới hạn chạy test riêng lẻ, retry và song song.

## 8. Cấu hình mặc định toàn bộ test suite: khi nào cần và rủi ro

JUnit Jupiter hỗ trợ thiết lập lifecycle mặc định trong `src/test/resources/junit-platform.properties`:

```properties
junit.jupiter.testinstance.lifecycle.default = per_class
```

Khi thuộc tính này có hiệu lực, các test class **không ghi `@TestInstance`** sẽ nhận `PER_CLASS`; class có annotation cụ thể vẫn làm theo annotation. Có thể dùng giá trị `per_method` để chọn kiểu mặc định tương ứng. Một cấu hình cấp suite có thể ảnh hưởng lớn đến test hiện có: các instance field trước đây được làm mới sẽ bắt đầu giữ state qua các test và những giả định về `@BeforeAll` có thể đổi.

Nếu đã dùng global configuration, bảo đảm IDE, command-line/CI và test runner đều nạp cùng cấu hình. Nếu không, test chạy thành công ở một môi trường nhưng thất bại ở nơi khác có thể do **lifecycle default khác nhau**. Trong phần lớn dự án, nên giữ mặc định `PER_METHOD` và chỉ đánh dấu `PER_CLASS` tại những lớp thực sự cần fixture dùng chung, kèm lời giải thích.

## 9. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Khả năng gây ra | Hướng kiểm tra/sửa |
| --- | --- | --- |
| Test B chỉ xanh khi chạy sau test A | B dựa trên instance field của `PER_CLASS`, singleton hoặc DB do A chuẩn bị | Chạy B riêng; cho B tự dựng fixture; bỏ phụ thuộc order |
| `@BeforeAll` non-static bị từ chối | Class vẫn dùng `PER_METHOD` | Đổi callback thành static, hoặc chọn `PER_CLASS` sau khi đánh giá shared state |
| Giá trị instance field bất ngờ bằng 0 trong test kế tiếp | `PER_METHOD` tạo instance mới | Dữ liệu mỗi ca phải tự chuẩn bị; nếu cần chia sẻ fixture, dùng cơ chế có chủ đích |
| `@Autowired` singleton vẫn giữ giá trị từ test trước | Spring context/bean được tái sử dụng | Reset trong fixture, thiết kế bean stateless, hoặc cô lập context khi thực sự cần |
| Test xanh riêng nhưng fail chạy cả suite | Static state, cache, DB hoặc tài nguyên ngoài bị rò rỉ | So sánh trạng thái trước/sau, dữ liệu test, profile và thứ tự class |
| Test fail ngẫu nhiên khi bật parallel | Race condition trên mutable shared state hoặc cleanup chéo | Dùng state riêng, đồng bộ hoặc resource lock khi phù hợp |
| Dùng `@DirtiesContext` làm suite rất chậm | Spring phải dựng lại context nhiều lần | Ưu tiên cleanup state thích hợp; đánh dấu dirty chỉ khi cần |
| Parameterized test với `PER_CLASS` cộng dồn counter | Mọi invocation dùng chung instance | Reset trong `@BeforeEach` hoặc chọn `PER_METHOD` |
| Dynamic test không nhận callback cho từng case | `@TestFactory` không có lifecycle callback riêng cho từng dynamic test | Tạo state ngay trong từng executable của dynamic test |

Một cách chẩn đoán có ích là xác định **đúng loại đối tượng đang giữ dữ liệu sai**: trường test instance, trường static, Spring bean, database hay hệ thống bên ngoài. Sau đó chọn phạm vi setup/teardown phù hợp, không đổi `PER_CLASS` sang `PER_METHOD` một cách mù quáng khi nguồn leak thực tế là singleton hoặc DB.

## 10. Bài tập tự kiểm tra

**Tình huống A — cùng instance hay không?** Lớp test có `private int count = 0;`, mỗi test gọi `count++`, không có `@BeforeEach` reset. Hai test sẽ nhìn thấy điều gì? Với `PER_METHOD`, mỗi test bắt đầu từ 0 và sau một lần tăng nhận 1. Với `PER_CLASS`, cùng instance có thể giữ count tăng qua các test; đừng kết luận thứ tự nếu không cấu hình order.

**Tình huống B — một singleton, hai test instance.** Hai phương thức `@SpringBootTest` nhận cùng `@Autowired CounterService`. Test thứ nhất tăng `CounterService` lên 1, test thứ hai dùng `PER_METHOD`. Test thứ hai có được bảo đảm thấy 0 không? **Không**. Vòng đời JUnit instance và vòng đời bean trong Spring context là hai cơ chế khác nhau.

**Tình huống C — không muốn chia sẻ nhưng cần setup đắt.** Có bảng tra cứu cấu hình cố định dùng cho 30 test và một `List` ghi sự kiện được từng test thay đổi. Chọn tạo bảng một lần (immutable) qua `@BeforeAll` trong `PER_CLASS` nếu phù hợp, đồng thời tạo `List` mới trong `@BeforeEach`. Không để event từ test trước lọt sang test sau.

**Tình huống D — chạy song song.** Hai test cùng gọi `counter.reset()`, `counter.increment()`, rồi assert 1 trên cùng singleton. Có thể cả hai đều FAIL dù `AtomicInteger` đúng về thread safety không? **Có**: các thao tác riêng lẻ là atomic, nhưng cả chuỗi không atomic; một test có thể reset trong lúc test kia đã tăng.

### Checklist trước khi viết hoặc review test

- Mặc định test instance đang là `PER_METHOD` hay `PER_CLASS`? Quyết định đến từ annotation hay `junit-platform.properties`?
- `@BeforeAll`, `@BeforeEach`, `@AfterEach`, `@AfterAll` đang tác động đúng phạm vi resource?
- Trường nào là instance field, trường nào là static, và dependency nào được Spring cache/tái sử dụng?
- Mỗi test có tự dựng input và expected outcome, không cần một test khác chạy trước?
- Khi có trạng thái mutable, ai reset/cleanup, và reset đó có an toàn khi chạy cả suite hay song song?
- Nếu dùng `@DirtiesContext`, đã hiểu chi phí restart context và giới hạn đối với DB/external resources chưa?
- Đã kiểm tra chạy test riêng, cả lớp và cả suite trong cùng điều kiện?

**Điểm cốt lõi:** `PER_METHOD` làm mới **đối tượng lớp test** cho từng lần thực thi; `PER_CLASS` giữ **một đối tượng lớp test** và cho phép instance lifecycle callback dùng chung fixture. Không lựa chọn nào tự reset mọi trạng thái của Spring Boot hay môi trường kiểm thử. Thiết kế test đáng tin đòi hỏi xác định chính xác phạm vi của dữ liệu và dọn/khởi tạo đúng phạm vi ấy.
