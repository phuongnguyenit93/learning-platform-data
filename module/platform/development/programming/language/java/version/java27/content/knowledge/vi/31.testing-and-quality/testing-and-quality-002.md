# JUnit, assertion và vòng đời fixture

Một bài kiểm thử tự động có giá trị khi nó **phát hiện hành vi sai**, mô tả đúng hợp đồng của chương trình và cho kết quả lặp lại được. Chỉ chạy một method rồi không có kiểm tra nào không chứng minh được tính đúng đắn. Ngược lại, một bộ kiểm thử phụ thuộc đồng hồ thật, dữ liệu được chia sẻ hoặc thứ tự chạy có thể thất bại ngẫu nhiên dù logic nghiệp vụ không đổi.

Trong hệ sinh thái Java, **JUnit** là nền tảng phổ biến để viết và chạy kiểm thử. Bài học này tập trung vào ba thành phần gắn kết chặt chẽ:

1. **JUnit Jupiter:** các annotation và API dùng để mô tả test, tổ chức quá trình thực thi và tích hợp công cụ build.
2. **Assertions:** những phép xác nhận *kết quả thực tế* có khớp *kỳ vọng* hay không, kể cả ngoại lệ, thời gian chạy và trạng thái của đối tượng.
3. **Test fixture lifecycle:** cách chuẩn bị, cách ly và dọn dẹp dữ liệu/tài nguyên trước và sau mỗi test hoặc mỗi nhóm test.

Bài học thuộc chương **Kiểm thử và chất lượng** của module **JAVA_VERSION_JAVA27 – Java 27 và các kiến thức liên quan**. Nội dung sử dụng **JUnit Jupiter 6.1.3**, một bản phát hành ổn định hiện hành phù hợp với JDK 27 (JUnit 6 yêu cầu Java 17 trở lên), cùng API Java SE 27. JUnit là **thư viện bên ngoài JDK**: nó không xuất hiện chỉ vì dự án được cấu hình Java 27. Theo yêu cầu sử dụng kiến thức còn phù hợp, các ví dụ mới không dựa vào cơ chế JUnit 4 `@RunWith`, `@Before`, `@After` hay JUnit Vintage.

## 1. JUnit Platform, Jupiter và Vintage khác nhau như thế nào?

JUnit hiện đại có ba thành phần thường thấy:

| Thành phần | Vai trò | Nên dùng trong dự án Java 27 mới? |
| --- | --- | --- |
| **JUnit Platform** | Phát hiện, điều phối và khởi chạy các test engines; tích hợp IDE, Maven, Gradle | **Có** |
| **JUnit Jupiter** | API viết test (`@Test`, `@BeforeEach`, `Assertions`...) và Jupiter test engine | **Có** |
| **JUnit Vintage** | Engine tương thích để chạy test JUnit 3/4 khi đang chuyển đổi | **Không dùng làm nền tảng test mới**; chỉ cân nhắc tạm thời khi migration |

Luồng chạy:

```text
    src/test/java (Jupiter tests)
              |
              v
      Maven / Gradle / IDE
              |
              v
         JUnit Platform
              |
              v
       Jupiter TestEngine
              |
        +-----+-------+
        |             |
       Test A        Test B
        |             |
    assertions    assertions
        |             |
        +------+------+
               |
       Test results / reports
```

Các import trong mã kiểm thử thường nằm trong `org.junit.jupiter.api`, không phải `org.junit.Test` hoặc `org.junit.Assert` của JUnit 4.

**Cần phân biệt:** JUnit 6.1.3 yêu cầu **Java 17+ khi chạy chính JUnit**, nhưng điều đó không bắt buộc application code phải sử dụng tính năng ngôn ngữ Java 17. Với module Java 27, chọn một JDK/toolchain hỗ trợ `--release 27` và cấu hình build tương ứng.

## 2. Cài đặt dependency và chạy test với Gradle hoặc Maven

Để mọi đoạn mã `@Test` được IDE và build tool nhận ra, phải có **JUnit Jupiter API và test engine** tương thích trên test classpath/module path.

### 2.1. Gradle Kotlin DSL (`build.gradle.kts`)

Ví dụ dùng JUnit BOM để đồng bộ phiên bản artifacts:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:6.1.3"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
```

`useJUnitPlatform()` giúp Gradle chạy tests trên JUnit Platform. BOM giữ các JUnit dependencies tương thích. `junit-jupiter` là artifact gộp API, engine và phần hỗ trợ cần thiết theo dependency metadata của JUnit; `junit-platform-launcher` hỗ trợ việc khởi chạy ổn định từ build tools/IDE.

Chạy:

```shell
./gradlew test
```

Trên Windows, dùng wrapper phù hợp: `gradlew.bat test`. Đây là **lệnh dành cho người học**, không phải kết quả đã chạy trong bước biên soạn tài liệu.

### 2.2. Maven (`pom.xml`)

Ví dụ khai báo BOM, JUnit Jupiter và Maven Surefire để test Java 27:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example.testing</groupId>
    <artifactId>junit-fixture-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>27</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit</groupId>
                <artifactId>junit-bom</artifactId>
                <version>6.1.3</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`Surefire` từ dòng 3.0.0 trở lên hỗ trợ JUnit 6 theo yêu cầu hiện hành; phiên bản 3.5.4 ở đây là **ví dụ cấu hình**, không phải tuyên bố bản Maven plugin mới nhất. Với Gradle/Maven hoặc framework có dependency management riêng, sử dụng versions tương thích được nhóm dự án duyệt. Không cần khai báo cả hai build systems trong cùng dự án.

Chạy:

```shell
mvn test
```

### 2.3. Cấu trúc source thông dụng

```text
src/
  main/
    java/
      example/pricing/InvoiceCalculator.java
  test/
    java/
      example/pricing/InvoiceCalculatorTest.java
    resources/
      ... dữ liệu kiểm thử riêng ...
```

Mã ứng dụng nằm trong `src/main/java`, mã test trong `src/test/java`; `@Test` thông thường không cần nằm trong artifact production. Khi chạy test trong IDE, bảo đảm IDE sử dụng cùng JDK và dependency resolution với build tool.

## 3. Một test nhỏ nhất và mô hình Arrange–Act–Assert

`@Test` đánh dấu một method làm test case trong JUnit Jupiter:

```java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class ArithmeticTest {
    @Test
    void addingTwoNumbersProducesTheirSum() {
        // Arrange: chuẩn bị đầu vào.
        int first = 2;
        int second = 3;

        // Act: gọi mã cần kiểm tra.
        int actual = Math.addExact(first, second);

        // Assert: xác minh kết quả quan sát được.
        assertEquals(5, actual);
    }
}
```

Ba bước thường dùng là **AAA**:

1. **Arrange:** thiết lập fixture và đầu vào, chuẩn bị dependencies cần thiết.
2. **Act:** kích hoạt một hành vi nghiệp vụ.
3. **Assert:** kiểm tra kết quả, lỗi hoặc side effect được yêu cầu.

Không phải mọi test phải có ba comment AAA, nhưng tư duy tách ba bước giúp nhận ra test đang kiểm tra **điều gì**. Tên method nên mô tả hành vi, ví dụ `rejectsNegativeQuantity`, thay vì `test1`.

### 3.1. Assertions phải kiểm tra hợp đồng cụ thể

Ví dụ kém:

```java
@Test
void badExample() {
    calculator.total(price, quantity, shipping);
    // Không assertion, không kiểm tra hành vi hoặc kết quả.
}
```

Test trên chỉ phát hiện một số exception không mong đợi. Nếu hợp đồng yêu cầu giá tiền chính xác, phải kiểm tra **giá trị**, hoặc nếu chỉ muốn khẳng định không ném exception thì dùng `assertDoesNotThrow(...)` và đặt tên test đúng ý nghĩa.

### 3.2. Lỗi assertion giúp xác định regression

`assertEquals(expected, actual)` thất bại khi hai giá trị không bằng nhau theo phép so sánh mà assertion áp dụng. Tổ chức thông thường là **expected trước, actual sau**; JUnit báo ra giá trị kỳ vọng/thực tế, thuận tiện đọc báo cáo CI.

## 4. Các assertion thông dụng trong JUnit Jupiter

Các phương thức tập trung ở `org.junit.jupiter.api.Assertions`:

| Assertion | Dùng để kiểm tra | Ví dụ ngắn |
| --- | --- | --- |
| `assertEquals(expected, actual)` | Giá trị bằng nhau | `assertEquals(42, result)` |
| `assertNotEquals(a, b)` | Giá trị khác nhau | `assertNotEquals("", name)` |
| `assertTrue(condition)` | Điều kiện đúng | `assertTrue(total.signum() >= 0)` |
| `assertFalse(condition)` | Điều kiện sai | `assertFalse(items.isEmpty())` |
| `assertNull(value)` | Giá trị `null` | `assertNull(missing)` |
| `assertNotNull(value)` | Giá trị khác `null` | `assertNotNull(customer)` |
| `assertSame(expected, actual)` | Cùng **object identity** | `assertSame(singleton, resolved)` |
| `assertNotSame(a, b)` | Khác **object identity** | `assertNotSame(first, second)` |
| `assertArrayEquals(expected, actual)` | Nội dung mảng bằng nhau | `assertArrayEquals(new int[]{1}, values)` |
| `assertIterableEquals(expected, actual)` | Phần tử theo thứ tự tương ứng | `assertIterableEquals(List.of(1, 2), result)` |
| `assertInstanceOf(Type.class, value)` | Thuộc kiểu được mong đợi | `assertInstanceOf(Number.class, value)` |
| `assertThrows(Type.class, code)` | Ném exception thuộc kiểu hoặc subtype mong đợi | `assertThrows(IllegalArgumentException.class, action)` |
| `assertThrowsExactly(Type.class, code)` | Ném **đúng kiểu** exception | `assertThrowsExactly(IllegalStateException.class, action)` |
| `assertDoesNotThrow(code)` | Không ném exception | `assertDoesNotThrow(service::refresh)` |
| `assertAll(heading, executables...)` | Nhóm nhiều assertions | `assertAll("invoice", ...)` |
| `assertTimeout(duration, executable)` | Thời gian thực thi không vượt mục tiêu | `assertTimeout(Duration.ofSeconds(2), action)` |

Các đoạn trong cột cuối là **snippets**; một số biến/method như `result` hay `action` phải được khai báo trong test thực tế.

### 4.1. Value equality khác identity

`assertEquals` dùng so sánh **giá trị** theo loại dữ liệu; `assertSame` kiểm tra hai tham chiếu trỏ vào **cùng đối tượng**.

```java
String first = new String("hello");
String second = new String("hello");

assertEquals(first, second);     // PASS: nội dung bằng nhau.
assertNotSame(first, second);    // PASS: hai object khác nhau.
```

Không dùng `assertSame` để kiểm tra hai `record`/DTO có dữ liệu bằng nhau nếu nghiệp vụ không yêu cầu dùng chung instance.

### 4.2. So sánh `BigDecimal` và số thực

`BigDecimal.equals` xét cả **giá trị và scale**. Vì thế:

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("10.0");
BigDecimal b = new BigDecimal("10.00");

assertNotEquals(a, b);                    // Khác scale.
assertEquals(0, a.compareTo(b));          // Bằng nhau về giá trị số.
```

Với tiền, cách kiểm tra phụ thuộc **hợp đồng scale**: nếu API yêu cầu luôn hai chữ số thập phân, `assertEquals` với `"10.00"` là hợp lý; nếu chỉ cần giá trị toán học, dùng `compareTo`.

Với `double`/`float` tính toán gần đúng, cân nhắc overload có **delta/tolerance**:

```java
assertEquals(0.3, 0.1 + 0.2, 1e-9);
```

Không ép mọi phép tính số thực sang phép bằng tuyệt đối khi rounding là thành phần của thuật toán.

## 5. Kiểm thử ngoại lệ với `assertThrows` và `assertThrowsExactly`

Kiểm thử đường lỗi là một phần quan trọng của hợp đồng:

```java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ValidationTest {
    @Test
    void rejectsNegativeQuantity() {
        IllegalArgumentException ex = assertThrows(
                IllegalArgumentException.class,
                () -> validateQuantity(-1));

        assertEquals("quantity must be non-negative", ex.getMessage());
    }

    private static void validateQuantity(int quantity) {
        if (quantity < 0) {
            throw new IllegalArgumentException(
                    "quantity must be non-negative");
        }
    }
}
```

`assertThrows(IllegalArgumentException.class, ...)` chấp nhận `IllegalArgumentException` **hoặc subclass** của nó. Nếu hợp đồng yêu cầu **chính xác** kiểu exception:

```java
IllegalArgumentException ex = assertThrowsExactly(
        IllegalArgumentException.class,
        () -> validateQuantity(-1));
```

Với JUnit 6/Jupiter, cả hai method **trả đối tượng exception** đã bắt để kiểm tra `message`, `cause` hoặc các thuộc tính nghiệp vụ.

### 5.1. Không nhầm failure message với exception message

```java
assertThrows(
        IllegalArgumentException.class,
        () -> validateQuantity(-1),
        "Expected a validation failure");
```

Chuỗi cuối là **message hiển thị nếu assertion thất bại**, không phải nội dung bắt buộc của exception. Muốn kiểm tra `exception.getMessage()`, dùng một assertion riêng.

### 5.2. Chỉ đặt thao tác dự kiến ném lỗi trong lambda

Không nên:

```java
assertThrows(IllegalArgumentException.class, () -> {
    prepareExternalData();  // Có thể ném cùng loại lỗi.
    validateQuantity(-1);  // Đối tượng cần kiểm tra.
});
```

Nếu phần chuẩn bị cũng có thể ném `IllegalArgumentException`, test có thể **pass vì lỗi sai vị trí**. Hãy đặt setup riêng và lambda ngắn:

```java
prepareExternalData();
assertThrowsExactly(
        IllegalArgumentException.class,
        () -> validateQuantity(-1));
```

`prepareExternalData` là method minh họa. Trong unit test tốt, setup thường không cần phụ thuộc I/O ngoài nếu có thể thay bằng một fake/stub.

## 6. Grouped assertions, lazy messages và số liệu trả về

### 6.1. `assertAll` để biết nhiều lỗi trong một lần chạy

```java
record Customer(String name, int age, boolean verified) {}

Customer customer = new Customer("An", 25, true);

assertAll("customer",
        () -> assertEquals("An", customer.name()),
        () -> assertTrue(customer.age() >= 18),
        () -> assertTrue(customer.verified()));
```

JUnit cố thực hiện các assertions trong nhóm và tổng hợp các failures thông thường thành `MultipleFailuresError`. Điều này hữu ích khi xác minh **một đối tượng kết quả có nhiều trường liên quan**. Không nhóm quá nhiều điều kiện nghiệp vụ độc lập chỉ để giảm số lượng test cases.

### 6.2. Failure message dạng Supplier

```java
assertEquals(
        3,
        results.size(),
        () -> "Unexpected result count: " + expensiveToFormat(results));
```

`Supplier<String>` cho phép **tạo message khi cần**, tránh tính toán chuỗi đắt đỏ trên đường test pass. `expensiveToFormat` và `results` là thành phần giả định.

### 6.3. `assertDoesNotThrow` không thay thế xác minh kết quả

```java
String normalized = assertDoesNotThrow(
        () -> "  java  ".strip());

assertEquals("java", normalized);
```

Nếu nghiệp vụ có kết quả quan trọng, nên assert nó, không chỉ xác nhận “không ném lỗi”.

## 7. Java `assert` và JUnit assertions là hai cơ chế khác nhau

Java có từ khóa `assert` của ngôn ngữ:

```java
assert count >= 0 : "count must not be negative";
```

Java language assertions thường **bị tắt** khi không chạy JVM với `-ea`/`-enableassertions`. Vì vậy một test dùng mỗi `assert expression;` có thể không thực hiện kiểm tra như dự tính khi build/IDE thay đổi cấu hình JVM.

JUnit assertions là các method được chạy khi test method chạy, không phụ thuộc vào cờ `-ea`:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;

assertTrue(count >= 0, "count must not be negative");
```

**Khuyến nghị:** Dùng Jupiter `Assertions` để kiểm tra test outcomes. Java `assert` có vai trò riêng trong mã ứng dụng khi nhóm đã chủ động bật và hiểu semantics, nhưng **không** thay thế test assertions trong bộ kiểm thử hiện đại.

## 8. Fixture là gì? Phân biệt chuẩn bị, sử dụng và cleanup

**Test fixture** gồm những đối tượng, dữ liệu và tài nguyên cần có để test chạy được:

- Một instance service/repository cần kiểm tra.
- In-memory fake database hoặc collection các bản ghi.
- File tạm, thư mục tạm, test clock.
- Mock/fake của HTTP gateway hoặc message publisher.
- Với integration tests: container, database schema hoặc test server được quản lý.

Một fixture tốt phải **dễ dựng, độc lập, có cơ chế dọn dẹp và không phụ thuộc thứ tự chạy**.

Ví dụ vòng đời mong muốn:

```text
         Trước nhóm tests
             @BeforeAll
                 |
       +---------+-----------+
       |                     |
   @BeforeEach A         @BeforeEach B
       |                     |
     @Test A               @Test B
       |                     |
   @AfterEach A          @AfterEach B
       +---------+-----------+
                 |
             @AfterAll
```

Sơ đồ chỉ thể hiện **phạm vi lifecycle**, không phải cam kết hai test sẽ chạy song song hoặc A luôn chạy trước B. Thứ tự methods được JUnit quản lý và không nên trở thành một phụ thuộc nghiệp vụ.

## 9. Các annotation điều khiển vòng đời fixture

JUnit Jupiter có bốn lifecycle annotations chính:

| Annotation | Khi nào chạy? | Mục đích thường gặp |
| --- | --- | --- |
| `@BeforeAll` | Trước các test methods của một test container/class | Chuẩn bị tài nguyên đắt đỏ dùng chung an toàn |
| `@BeforeEach` | Trước mỗi test method hoặc invocation phù hợp | Tạo fixture **riêng** hoặc reset state |
| `@AfterEach` | Sau mỗi test method hoặc invocation phù hợp | Đóng tài nguyên thuộc test, dọn side effects |
| `@AfterAll` | Sau các test methods của container/class | Đóng tài nguyên dùng chung, giải phóng hạ tầng |

Với `@ParameterizedTest`, mỗi lần chạy với bộ dữ liệu riêng được xem là **một invocation** cho lifecycle: `@BeforeEach` và `@AfterEach` chạy **cho từng bộ tham số**. Với `@RepeatedTest` cũng tương tự. Với `@TestFactory`, callback lifecycle gắn với **method factory**, không tự chạy riêng cho mỗi `DynamicTest` được factory tạo ra.

### 9.1. Vòng đời điển hình

```text
                  @BeforeAll
                      |
            Tạo test instance #1
                      |
                  @BeforeEach
                      |
                  @Test #1
                      |
                  @AfterEach
                      |
            Tạo test instance #2
                      |
                  @BeforeEach
                      |
                  @Test #2
                      |
                  @AfterEach
                      |
                  @AfterAll
```

Sơ đồ giả định lifecycle mặc định `PER_METHOD`, với hai test methods được JUnit chạy theo một thứ tự minh họa. Các test methods không được bảo đảm chạy theo thứ tự source code.

### 9.2. `@BeforeAll`/`@AfterAll` mặc định phải là `static`

```java
import org.junit.jupiter.api.*;

class CatalogTest {
    @BeforeAll
    static void prepareSharedData() {
        // Chỉ chuẩn bị dữ liệu immutable hoặc resource dùng chung an toàn.
    }

    @AfterAll
    static void releaseSharedData() {
        // Dọn resource ở mức class nếu đã tạo.
    }

    @BeforeEach
    void prepareEachTest() {
        // Tạo/đặt lại fixture theo từng test.
    }

    @AfterEach
    void cleanEachTest() {
        // Dọn tài nguyên thuộc test hiện tại.
    }

    @Test
    void acceptsKnownCode() {
        Assertions.assertTrue("SKU-1".startsWith("SKU-"));
    }
}
```

Các callbacks `@BeforeAll`/`@AfterAll` có thể là **instance methods** nếu test class dùng `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`; quy tắc này được giải thích ở mục 12.

Các lifecycle methods không được `private`; JUnit có những quy tắc visibility/parameters riêng. Đối với tests thông thường, nên dùng **package-private** như trên và để framework phát hiện.

## 10. Fixture per-test: dùng `@BeforeEach` để reset dữ liệu

Trong nhiều dự án, mỗi test cần một phiên bản service và bộ dữ liệu độc lập. Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ShoppingListTest {
    private List<String> items;

    @BeforeEach
    void setUp() {
        items = new ArrayList<>();
    }

    @Test
    void addingAnItemIncreasesCount() {
        items.add("coffee");
        assertEquals(1, items.size());
    }

    @Test
    void newListIsEmpty() {
        assertTrue(items.isEmpty());
    }
}
```

Mỗi test bắt đầu bằng một `ArrayList` mới. Test thứ hai **không** phụ thuộc việc test thứ nhất đã thêm bao nhiêu phần tử, hay thứ tự runner đã chạy chúng.

### 10.1. Khi nào cần `@AfterEach`?

Nếu fixture chỉ là `ArrayList` không nắm tài nguyên ngoài, có thể **không cần** `@AfterEach`: GC xử lý object khi không còn reachable. `@AfterEach` hữu ích khi test tạo:

- File hoặc thư mục do ứng dụng tự quản lý.
- Socket, server, HTTP client, process hoặc executor cần đóng.
- Database transaction cần rollback và connection cần trả về pool.
- Global properties, system clock abstraction hoặc registry có thay đổi phải khôi phục.

**Không tạo teardown rỗng chỉ để đủ bốn annotation.** Dọn đúng tài nguyên thực tế, không tự gọi `System.gc()` hoặc chờ thời gian bất kỳ trong cleanup.

## 11. `PER_METHOD`: lifecycle mặc định và tính độc lập

JUnit Jupiter mặc định tạo **một test class instance mới trước mỗi test method** (`TestInstance.Lifecycle.PER_METHOD`). Điều này giúp instance fields không tự rò trạng thái từ test này sang test khác:

```java
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class PerMethodExample {
    private final List<String> events = new ArrayList<>();

    @Test
    void oneTestCanModifyItsInstance() {
        events.add("created");
        assertEquals(List.of("created"), events);
    }

    @Test
    void anotherTestStartsWithNewInstance() {
        assertTrue(events.isEmpty());
    }
}
```

Hai tests trên chạy độc lập vì hai giá trị `events` thuộc **hai test instances khác nhau**. Với tài nguyên mutable được cấp từ `static` fields, singleton, database thật hoặc external service, mặc định `PER_METHOD` **không tự cách ly** các đối tượng đó.

### 11.1. Instance mới có xóa được mọi side effect không?

Không. Những thứ sau có thể vẫn được chia sẻ:

- `static` state, cache/singleton trong application code.
- Filesystem, biến môi trường, JVM system properties, locale/timezone mặc định.
- Database hoặc message broker có dữ liệu chung.
- Network ports, thread pools, shared external service.

Thiết kế test isolation phải xét **tài nguyên ở ngoài test instance**, không chỉ annotation lifecycle.

## 12. `PER_CLASS`: một instance cho nhiều tests

Khi chọn:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class SharedFixtureTest {
    // Một instance của SharedFixtureTest phục vụ các tests trong class.
}
```

JUnit dùng **cùng một test class instance** cho các test methods trong container đó. Điều này có ích nếu fixture tạo đắt đỏ và được dùng chung an toàn, hoặc muốn khai báo `@BeforeAll`/`@AfterAll` là instance methods:

```java
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class PerClassExample {
    private final List<String> workingData = new ArrayList<>();
    private List<String> referenceData;

    @BeforeAll
    void loadReferenceData() {
        referenceData = List.of("A", "B"); // Immutable snapshot.
    }

    @BeforeEach
    void resetWorkingData() {
        workingData.clear(); // Rất quan trọng vì instance được dùng lại.
    }

    @Test
    void addOneItem() {
        workingData.add("A");
        assertEquals(1, workingData.size());
    }

    @Test
    void startEmptyOnEveryTest() {
        assertTrue(workingData.isEmpty());
        assertEquals(2, referenceData.size());
    }

    @AfterAll
    void releaseReferenceData() {
        referenceData = null;
    }
}
```

**Đánh đổi:** Nếu test A thay đổi instance fields và test B nhìn thấy state đó, test B có thể phụ thuộc thứ tự chạy. Vì vậy `PER_CLASS` không nên trở thành mặc định toàn dự án chỉ để tránh tạo object rẻ.

### 12.1. Thay đổi default ở cấp dự án

JUnit Jupiter cho phép cấu hình:

```properties
# src/test/resources/junit-platform.properties
junit.jupiter.testinstance.lifecycle.default = per_method
```

`per_method` cũng là mặc định chuẩn; ví dụ chỉ làm rõ ý nghĩa. Có thể đổi thành `per_class`, nhưng nếu IDE và CI dùng defaults khác nhau, tests dễ hoạt động không nhất quán. Nếu cần đổi, cấu hình qua `junit-platform.properties` được quản lý chung trong repository và kiểm tra parallel safety.

### 12.2. Parallel execution và shared mutable state

Khi kích hoạt chạy song song, tests `PER_CLASS` có thể cùng nhìn vào mutable instance fields; tests có `static` shared state cũng chịu vấn đề tương tự. Cần chọn một trong những cách:

1. Ưu tiên state bất biến hoặc fixture riêng cho test.
2. Dùng cơ chế phân tách tài nguyên theo test ID.
3. Sử dụng cấu hình execution/resource locking của JUnit khi thực sự cần serial hóa.
4. Chỉ dùng đồng bộ hóa khi test đang kiểm tra concurrency hoặc hạ tầng bắt buộc chia sẻ.

Không giải quyết test race bằng cách thêm `Thread.sleep(...)` để “đợi chắc đã”.

## 13. Cleanup hiện đại: `@TempDir`, `@AutoClose` và `try-with-resources`

### 13.1. `@TempDir` tạo thư mục riêng phục vụ test

JUnit Jupiter có built-in extension `@TempDir`, có thể cấp `Path`:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class ExportTest {
    @Test
    void writesReportToTemporaryDirectory(@TempDir Path tempDir)
            throws Exception {

        Path report = tempDir.resolve("report.txt");
        Files.writeString(report, "OK");

        assertTrue(Files.isRegularFile(report));
        assertEquals("OK", Files.readString(report));
    }
}
```

`@TempDir` tạo thư mục tạm cho phạm vi được annotate và **mặc định dọn khi hoàn tất**. Với injection ở test method parameter như trên, mỗi test có thư mục riêng. `@TempDir` cũng có thể dùng ở một số lifecycle parameters và fields; scope có thể rộng hơn khi khai báo chung ở mức class.

Không sử dụng các đường dẫn cố định như `/tmp/shared-test-output` cho mọi tests: file có thể bị xóa hoặc ghi đè khi chạy song song. Không giữ lại các file nhạy cảm trong temporary directory chỉ vì môi trường CI sẽ tự dọn.

### 13.2. `@AutoClose` cho field chứa resource

JUnit Jupiter có `@AutoClose` để tự gọi `close()` trên field sau vòng đời phù hợp:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.junit.jupiter.api.AutoClose;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ExecutorTest {
    @AutoClose
    private final ExecutorService executor =
            Executors.newSingleThreadExecutor();

    @Test
    void executesTask() throws Exception {
        assertEquals("done", executor.submit(() -> "done").get());
    }
}
```

Với fixture theo `PER_METHOD`, resource trên được tạo cho một test instance và đóng khi vòng đời của instance đó kết thúc. Field `static` với `@AutoClose` thường có phạm vi class và đóng tại lifecycle tương ứng.

Không để nhiều resources phụ thuộc nhau mà lại giả định thứ tự đóng của nhiều `@AutoClose` fields trong cùng class là một thứ tự tùy ý do mình mong muốn. Khi phải đóng có thứ tự, hãy viết cleanup có trình tự rõ ràng hoặc đóng trong cùng một `try-with-resources`.

### 13.3. `try-with-resources` ngay trong test

Nếu resource chỉ dùng trong một test body, có thể không cần lifecycle callback:

```java
@Test
void readsFromStream() throws Exception {
    try (var stream = new java.io.ByteArrayInputStream(
            new byte[] {1, 2, 3})) {
        assertEquals(1, stream.read());
    }
}
```

Một test độc lập tự quản lý resource có phạm vi sử dụng rất rõ; không nên “đẩy hết tài nguyên vào `@BeforeAll`” chỉ vì có lifecycle annotation.

## 14. `@Nested` và fixture theo bối cảnh

`@Nested` cho phép nhóm tests theo bối cảnh nghiệp vụ. Một nested test class (non-static inner class) có thể dùng fixture của outer class và thêm fixture riêng:

```java
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;

class CartTest {
    private List<String> cart;

    @BeforeEach
    void createEmptyCart() {
        cart = new ArrayList<>();
    }

    @Test
    void cartStartsEmpty() {
        assertTrue(cart.isEmpty());
    }

    @Nested
    class WhenCartContainsOneItem {
        @BeforeEach
        void addFirstItem() {
            cart.add("tea");
        }

        @Test
        void countIsOne() {
            assertEquals(1, cart.size());
        }

        @Test
        void firstItemIsTea() {
            assertEquals("tea", cart.getFirst());
        }
    }
}
```

Ở nested test, `CartTest.createEmptyCart()` chạy trước callback `addFirstItem()` thuộc inner class. Hai nested tests vẫn có fixture per-method độc lập; không phải test `countIsOne()` thêm phần tử để `firstItemIsTea()` dùng lại.

**Không** chọn `@Nested` để tạo chuỗi tests phụ thuộc nhau kiểu “đăng ký → đăng nhập → thanh toán” nếu mỗi bước phải dựa vào side effect của test trước. Với workflow integration thật, gộp các bước thành **một test scenario** với setup/cleanup minh bạch hoặc thiết kế state độc lập.

## 15. `@ParameterizedTest` và vòng đời mỗi lần gọi

Parameterized tests giảm việc lặp lại cấu trúc khi cùng một hành vi cần kiểm tra nhiều bộ dữ liệu:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import static org.junit.jupiter.api.Assertions.*;

class QuantityValidationTest {
    private int setupCalls;

    @BeforeEach
    void prepareFixture() {
        setupCalls = 1;
    }

    @ParameterizedTest
    @CsvSource({
        "0, true",
        "1, true",
        "-1, false"
    })
    void acceptsOnlyNonNegativeQuantity(int quantity, boolean expected) {
        assertEquals(1, setupCalls);
        assertEquals(expected, quantity >= 0);
    }
}
```

JUnit thực thi `@BeforeEach` cho **mỗi invocation** tương ứng từng row; trong lifecycle mặc định `PER_METHOD`, mỗi invocation còn có test instance riêng. Không để một bộ dữ liệu thay đổi `static` cache rồi khiến row tiếp theo phụ thuộc vào nó.

Những nguồn tham số thông dụng:

- `@ValueSource`: các giá trị cùng kiểu như `ints`, `strings`.
- `@CsvSource`: nhiều giá trị cho một invocation.
- `@MethodSource`: factory cung cấp arguments, thích hợp với case phức tạp.
- `@NullSource` và `@EmptySource`: bổ sung case `null` hoặc tập rỗng theo kiểu phù hợp.

JUnit 6 cũng hỗ trợ **parameterized classes**, nhưng phần này tập trung vào API `@ParameterizedTest` đã ổn định; không cần dùng các tính năng thử nghiệm chỉ để có tests tham số hóa.

## 16. Dependency injection sẵn có của JUnit Jupiter

JUnit Jupiter có cơ chế giải quyết tham số cho một số kiểu, ví dụ `TestInfo` và `TestReporter`, hoặc `@TempDir Path`. Không nên suy rằng mọi tham số constructor/test method được Jupiter tự động tạo từ dependency injection container của ứng dụng.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInfo;
import static org.junit.jupiter.api.Assertions.*;

class MetadataTest {
    @BeforeEach
    void logDescription(TestInfo testInfo) {
        assertNotNull(testInfo.getDisplayName());
    }

    @Test
    void testHasMetadata(TestInfo testInfo) {
        assertFalse(testInfo.getDisplayName().isBlank());
    }
}
```

Để inject repository, HTTP client fake, clock hoặc các dependencies nghiệp vụ, nhiều dự án dùng **constructor/manual wiring** trong fixture hoặc một JUnit `Extension`/framework test integration được cấu hình cụ thể. Không bắt buộc đưa toàn bộ unit tests vào Spring/container chỉ để tạo một object Java thông thường.

## 17. Kiểm thử thời gian: `assertTimeout`, `@Timeout` và đồng hồ giả lập

Có hai nhu cầu **khác nhau**: kiểm tra logic sử dụng thời gian và kiểm tra thời gian thực thi.

### 17.1. `assertTimeout` đo thời gian chạy, không ngắt trước hạn

```java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class TimeoutExample {
    @Test
    void finishesQuickly() {
        assertTimeout(Duration.ofSeconds(2), () -> {
            String text = "hello".toUpperCase();
            assertEquals("HELLO", text);
        });
    }
}
```

`assertTimeout` chạy đoạn code trong **cùng thread gọi assertion**, rồi đánh giá thời gian hoàn thành. Nếu code bị treo quá hạn, nó **không tự động dừng ngay** ở thời điểm timeout; vì vậy vẫn cần timeout thật ở network/database client nếu test thao tác với I/O.

### 17.2. `assertTimeoutPreemptively` có cảnh báo về thread

`assertTimeoutPreemptively` có thể thực thi đoạn cần kiểm tra trên **thread khác** để có timeout sớm hơn. Điều đó nguy hiểm khi test dựa vào `ThreadLocal`, transaction context, request context hoặc framework có state gắn thread. Sau timeout, công việc được gọi có thể không dừng ngay nếu nó không hợp tác với interruption.

Đặc biệt, trong tests sử dụng transaction managed bằng `ThreadLocal`, chạy code trên thread khác có thể khiến thao tác ngoài transaction test và dẫn tới side effects thật. Đừng chọn preemptive timeout chỉ vì “nhanh hơn” mà không xét cách quản lý context.

### 17.3. `@Timeout` áp dụng ở cấp method

```java
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

class DeadlineTest {
    @Test
    @Timeout(value = 500, unit = TimeUnit.MILLISECONDS)
    void completesWithinDeadline() {
        // Logic cần kiểm tra.
    }
}
```

Mặc định `@Timeout` dùng **giây** nếu không khai báo `unit`. Có thể cấu hình thread mode và timeout defaults theo User Guide. Nếu cần deadline cho I/O, chỉ thêm annotation là chưa đủ để bảo đảm connection/query đã bị hủy thành công.

### 17.4. Với logic ngày giờ, dùng `Clock.fixed` thay vì `Thread.sleep`

Test logic hết hạn nên kiểm soát **thời điểm**, không nên đợi đồng hồ thật nhảy qua ngưỡng:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ExpirationTest {
    @Test
    void tokenExpiresAtBoundary() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-27T12:00:00Z"),
                ZoneOffset.UTC);
        Instant deadline = Instant.parse("2026-11-27T12:00:00Z");

        assertFalse(Instant.now(clock).isBefore(deadline));
    }
}
```

Trong code production, inject `Clock` vào service cần kiểm tra và so sánh thời điểm theo hợp đồng. Đừng mock thời gian bằng cách thay toàn bộ timezone mặc định của JVM nếu chỉ một service cần biết `Instant.now()`.

## 18. `Assumptions`, `@Disabled` và `@Tag`: phân biệt skipped với failed

### 18.1. Assumption khiến test bị aborted

```java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assumptions.assumeTrue;
import static org.junit.jupiter.api.Assertions.*;

class EnvironmentTest {
    @Test
    void requiresExplicitIntegrationEnvironment() {
        assumeTrue(
                "true".equals(System.getenv("RUN_INTEGRATION_TESTS")),
                "Integration environment not enabled");

        // Chỉ chạy khi điều kiện phù hợp.
        assertTrue(true);
    }
}
```

Nếu assumption sai, invocation được xem là **aborted**, không phải assertion failure thông thường. Không dùng assumption để che lỗi nghiệp vụ: ví dụ “nếu kết quả sai thì skip” khiến test không còn chứng minh đúng/sai.

### 18.2. `@Disabled` và `@Tag`

```java
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

class TestCategories {
    @Test
    @Tag("unit")
    void fastLogicTest() {
        // Chạy trong bộ unit tests.
    }

    @Test
    @Tag("integration")
    void databaseIntegrationTest() {
        // Cần môi trường integration đã cấu hình.
    }

    @Test
    @Disabled("Issue TEST-123: đang sửa fixture theo hợp đồng mới")
    void temporarilyUnavailableTest() {
        // Phải được bật lại theo kế hoạch, không để bị quên.
    }
}
```

`@Tag` giúp chọn nhóm tests ở build/CI; nó **không tự bảo đảm** test có/không có side effects. `@Disabled` nên có **lý do và kế hoạch xử lý**, không phải công cụ mặc định để làm pipeline xanh khi test đang thất bại.

## 19. Thứ tự thực thi và parallel tests: đừng dựa vào “test A chạy trước”

Theo JUnit Jupiter, thứ tự test methods mặc định được xác định bởi một thuật toán **ổn định nhưng cố tình không hiển nhiên**. Không coi thứ tự viết method trong source là thứ tự chạy.

**Thiết kế tốt:**

- Mỗi test tự chuẩn bị dữ liệu cần thiết.
- Không có test nào đòi test trước tạo bản ghi cho mình.
- Không dùng state `static` mutable làm nguồn dữ liệu duy nhất.
- Khi integration tests dùng cùng DB, tạo namespace/transaction riêng, cleanup và kiểm soát xung đột.
- Khi chạy song song, resource được chia sẻ phải thread-safe hoặc được điều phối rõ ràng.

JUnit cung cấp `@TestMethodOrder` và `@Order` cho những trường hợp **thực sự cần thứ tự**, nhưng trong unit tests thông thường, **loại bỏ phụ thuộc thứ tự** giúp test bền vững và dễ chạy độc lập.

### 19.1. Một nguồn flaky test thường gặp

```java
// Anti-pattern: mutable shared state xuyên suốt các test methods.
static final List<String> shared = new ArrayList<>();

@Test
void stepOne() {
    shared.add("created");
}

@Test
void stepTwo() {
    assertEquals("created", shared.getFirst());
}
```

Nếu test `stepTwo()` chạy riêng, nó thất bại. Nếu chạy cùng suite, nó có thể pass hoặc fail tùy thứ tự. Cách khắc phục là **chuyển việc chuẩn bị state vào fixture của chính test**, không thêm `@Order(1)`/`@Order(2)` để che quan hệ phụ thuộc không cần thiết.

### 19.2. Parallel execution không phải miễn phí

JUnit Jupiter có khả năng parallel execution có thể cấu hình. Việc bật parallel làm lộ các vấn đề:

- Test viết chung một đường dẫn file.
- Dữ liệu cùng một DB table không có khóa phân vùng.
- Global system properties/locale/timezone bị đổi rồi không khôi phục.
- Dùng singleton/mock có mutable state giữa các tests.

Đừng bật parallel cho cả suite chỉ vì số cores tăng; trước hết bảo đảm fixture isolation và resource constraints. Nên chia rõ **unit tests nhanh, độc lập** với **integration tests có môi trường ngoài**.

## 20. Biên giới unit test, integration test và thư viện mocking

JUnit Jupiter quyết định **phát hiện, chạy test và assertions/lifecycle**, không tự tạo một mock cho mọi dependency. Thư viện như Mockito (nếu dự án lựa chọn) là **dependency khác**, không mặc nhiên có chỉ vì khai báo `junit-jupiter`.

| Kiểu test | Mục tiêu | Fixture thường gặp |
| --- | --- | --- |
| **Unit test** | Hành vi một unit nghiệp vụ và các edge cases | Object mới, fake/stub, `Clock.fixed`, in-memory collections |
| **Integration test** | Tương tác với database, HTTP, filesystem hoặc framework | Test database/service/container, fixture cleanup và timeout |
| **End-to-end test** | Kịch bản qua nhiều thành phần | Môi trường test riêng, dữ liệu có thể dọn, điều phối workflow |

Không cần mock `List`, `BigDecimal` hoặc các value objects đơn giản chỉ để “test đúng chuẩn”. Stub/mock có ý nghĩa khi cần **kiểm soát external dependency hoặc quan sát interaction là một phần của hợp đồng**.

### 20.1. Đừng assert implementation details không cần thiết

Nếu nghiệp vụ chỉ yêu cầu tổng hóa đơn chính xác, một test assert số lần gọi method private hoặc thứ tự các bước tính toán bên trong khiến refactoring vô hại cũng làm test fail. Ưu tiên **đầu ra và side effects công khai**; chỉ kiểm tra interaction khi đó thực sự là hợp đồng, ví dụ chỉ gọi gateway **một lần** để tránh thanh toán trùng.

### 20.2. Reset fixture không có nghĩa reset toàn bộ hệ thống

Một `@BeforeEach` tạo mới service không tự rollback dữ liệu DB. Integration tests cần chiến lược phù hợp: transaction/rollback, schema riêng, dữ liệu định danh duy nhất hoặc cleanup đáng tin cậy. Khi sử dụng container/service thật, phải đặt timeout và tránh làm rò tài nguyên qua các trường hợp exception.

## 21. Ví dụ dự án hoàn chỉnh: tính tổng hóa đơn

Ví dụ sau dùng Java 27 và **JUnit Jupiter 6.1.3** như `pom.xml` ở mục 2. Có hai file Java: một lớp sản phẩm và một lớp test. Bài kiểm thử minh họa `@BeforeEach`, assertions, exception checking, `@ParameterizedTest` và `@TempDir`.

### 21.1. Mã ứng dụng: `src/main/java/example/pricing/InvoiceCalculator.java`

```java
package example.pricing;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public final class InvoiceCalculator {
    public BigDecimal total(
            BigDecimal unitPrice, int quantity, BigDecimal shipping) {

        Objects.requireNonNull(unitPrice, "unitPrice");
        Objects.requireNonNull(shipping, "shipping");

        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException(
                    "unitPrice must be non-negative");
        }
        if (quantity < 0) {
            throw new IllegalArgumentException(
                    "quantity must be non-negative");
        }
        if (shipping.signum() < 0) {
            throw new IllegalArgumentException(
                    "shipping must be non-negative");
        }

        return unitPrice
                .multiply(BigDecimal.valueOf(quantity))
                .add(shipping)
                .setScale(2, RoundingMode.HALF_UP);
    }
}
```

**Hợp đồng minh họa:** số lượng là số nguyên không âm; đơn giá và phí vận chuyển không âm; kết quả luôn có **scale 2**, làm tròn `HALF_UP`. Không trộn `double` vào bài toán tiền vì làm mất tính chính xác thập phân được định nghĩa bởi `BigDecimal`.

### 21.2. Mã test: `src/test/java/example/pricing/InvoiceCalculatorTest.java`

```java
package example.pricing;

import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("Invoice calculation")
class InvoiceCalculatorTest {
    private InvoiceCalculator calculator;

    @BeforeEach
    void setUp() {
        calculator = new InvoiceCalculator();
    }

    @Test
    void computesTotalOfItemsAndShipping() {
        BigDecimal total = calculator.total(
                new BigDecimal("10.00"),
                2,
                new BigDecimal("2.50"));

        assertEquals(new BigDecimal("22.50"), total);
    }

    @Test
    void roundsToTwoDecimalPlaces() {
        BigDecimal total = calculator.total(
                new BigDecimal("0.335"),
                3,
                BigDecimal.ZERO);

        assertAll("rounded total",
                () -> assertEquals(new BigDecimal("1.01"), total),
                () -> assertEquals(2, total.scale()));
    }

    @ParameterizedTest
    @CsvSource({
        "0, 2.00",
        "1, 12.00",
        "3, 32.00"
    })
    void computesMultipleQuantities(int quantity, String expected) {
        BigDecimal total = calculator.total(
                new BigDecimal("10.00"),
                quantity,
                new BigDecimal("2.00"));

        assertEquals(new BigDecimal(expected), total);
    }

    @Nested
    class InvalidInputs {
        @Test
        void rejectsNegativeQuantity() {
            IllegalArgumentException ex = assertThrowsExactly(
                    IllegalArgumentException.class,
                    () -> calculator.total(
                            new BigDecimal("10.00"),
                            -1,
                            BigDecimal.ZERO));

            assertEquals("quantity must be non-negative", ex.getMessage());
        }

        @Test
        void rejectsNullUnitPrice() {
            assertThrowsExactly(
                    NullPointerException.class,
                    () -> calculator.total(null, 1, BigDecimal.ZERO));
        }
    }

    @Test
    void writesAReportInAnIsolatedDirectory(@TempDir Path tempDir)
            throws Exception {

        BigDecimal total = calculator.total(
                new BigDecimal("10.00"),
                2,
                new BigDecimal("2.50"));

        Path report = tempDir.resolve("invoice.txt");
        Files.writeString(report, total.toPlainString());

        assertTrue(Files.exists(report));
        assertEquals("22.50", Files.readString(report));
    }
}
```

Kết quả kỳ vọng khi chạy `mvn test`: những tests trong class `InvoiceCalculatorTest` và nested class đều pass. Số lần chạy bao gồm nhiều invocations của parameterized test; **không mặc định một method tương đương đúng một test case trong report**.

### 21.3. Những nguyên tắc minh họa trong ví dụ

1. `@BeforeEach` tạo `InvoiceCalculator` riêng cho từng invocation, tránh giữ state giữa các tests.
2. `assertEquals` kiểm tra **cả giá trị và scale** theo hợp đồng `BigDecimal`.
3. `assertAll` báo nhiều lỗi liên quan đến một kết quả nếu cần.
4. `assertThrowsExactly` và kiểm tra `message` chứng minh đúng đường validation.
5. `@ParameterizedTest` kiểm tra nhiều số lượng với ít đoạn logic trùng lặp; fixture vẫn chạy mỗi lần.
6. `@Nested` nhóm các tình huống invalid inputs mà không phụ thuộc thứ tự.
7. `@TempDir` cung cấp directory riêng và cleanup, tránh file path cố định.
8. Không cần `@AfterEach` trong demo vì `InvoiceCalculator` không giữ tài nguyên cần đóng và temp dir đã được JUnit quản lý.

**Giới hạn:** `mvn test`/`./gradlew test` chỉ chạy được khi môi trường đã có JDK 27, build tool/dependencies tương thích và có thể resolve artifacts. Ví dụ không sử dụng các tính năng preview của Java 27.

## 22. Fixture nâng cao: cleanup thất bại và thứ tự lifecycle

Trong tests tích hợp có tài nguyên thật, hãy nghĩ tới **quá trình setup mới hoàn thành một phần**. Ví dụ, test tạo thư mục tạm thành công nhưng việc khởi tạo database connection thất bại. Cleanup phải chịu được trạng thái chưa khởi tạo, thay vì ném `NullPointerException` và che nguyên nhân đầu tiên.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

class SafeCleanupExample {
    private Path temporaryFile;

    @BeforeEach
    void prepare() throws IOException {
        temporaryFile = Files.createTempFile("fixture-", ".txt");
        // Nếu còn bước setup sau đó thất bại, file vẫn cần được dọn.
    }

    @AfterEach
    void clean() throws IOException {
        if (temporaryFile != null) {
            Files.deleteIfExists(temporaryFile);
        }
    }
}
```

Đây là ví dụ **chỉ minh họa lifecycle**, không chứa `@Test`. Với test filesystem mới, `@TempDir` ở mục 13 thường tốt hơn cách tự tạo file như trên. Khi cleanup cho resource cần đúng thứ tự, đóng trong một method có thứ tự tường minh.

### 22.1. Nhiều lifecycle methods trong cùng một class

JUnit Jupiter **không bảo đảm** thứ tự do bạn tưởng tượng giữa nhiều methods cùng được đánh dấu `@BeforeEach` trong **một class**. Tương tự, thứ tự nhiều `@AfterEach` không phải lời hứa “đảo ngược các `@BeforeEach` có cùng tên”.

**Không viết** các callbacks phụ thuộc nhau theo cách này:

```java
@BeforeEach
void createConnection() { /* ... */ }

@BeforeEach
void prepareSchema() { /* Phụ thuộc createConnection(). */ }
```

Thay bằng một callback có trình tự rõ:

```java
@BeforeEach
void prepareDatabaseFixture() {
    createConnection();
    prepareSchema();
}
```

Các methods `createConnection`, `prepareSchema` chỉ là minh họa. Trong integration test thực tế, cần bảo đảm close/rollback hoặc reset schema ở phạm vi tương ứng.

### 22.2. Kế thừa lifecycle từ class cha

Khi test kế thừa một base test class, callback `@BeforeEach` từ superclass được chạy **trước** callback ở subclass theo quy tắc JUnit; `@AfterEach` của subclass chạy **trước** callback cleanup ở superclass. Dù vậy, không nên xây cây kế thừa fixture sâu chỉ để tái sử dụng vài dòng setup: điều đó khiến lifecycle khó đọc.

Composition, helper methods, `@TempDir`, `@AutoClose` và extensions thường dễ hiểu hơn khi fixtures bắt đầu phức tạp.

### 22.3. Assertions trong fixture

Không phải mọi assertion đều nên nằm trong `@Test`; fixture có thể kiểm tra một tiền điều kiện cần thiết. Nhưng nếu `@BeforeEach` chứa cả **logic nghiệp vụ cần kiểm tra**, một lỗi setup khiến nhiều tests cùng fail mà không phản ánh từng hành vi riêng.

Ưu tiên:

- Setup để dữ liệu có trạng thái được kiểm soát.
- Test body để xác nhận contract đang được kiểm tra.
- Teardown để giải phóng đúng resource.

## 23. Các lỗi thường gặp và cách sửa

| Sai lầm | Vấn đề | Cách xử lý |
| --- | --- | --- |
| Chỉ gọi method rồi không assert gì | Test có thể pass dù kết quả sai | Kiểm tra giá trị, lỗi hoặc side effect thật |
| Dùng Java `assert` thay Jupiter Assertions | Bị tắt khi không bật `-ea` | Dùng `org.junit.jupiter.api.Assertions` |
| Đảo `expected` và `actual` trong `assertEquals` | Báo lỗi khó hiểu, gây nhầm khi debug | `assertEquals(expected, actual)` |
| Dùng `assertSame` khi chỉ muốn so nội dung | So identity thay vì value | `assertEquals` |
| So `BigDecimal` bằng `equals` khi chỉ cần cùng giá trị số | `10.0` khác `10.00` về scale | `compareTo` hoặc chuẩn hóa scale đúng contract |
| Assert `double` bằng tuyệt đối khi phép tính có rounding | Test có thể flaky hoặc sai kỳ vọng | Dùng tolerance thích hợp |
| `assertThrows` lambda chứa cả bước setup có thể ném cùng lỗi | Test pass bởi exception sai nguồn | Lambda chỉ bao đoạn dự kiến ném lỗi |
| Nhầm message cuối của `assertThrows` là exception message | Không kiểm tra nội dung lỗi thực | Assert `ex.getMessage()` riêng |
| Cho rằng `assertTimeout` sẽ hủy task ngay | Thực thi cùng thread, không preempt | Timeouts I/O thật và lựa chọn timeout strategy |
| Dùng `assertTimeoutPreemptively` với transaction `ThreadLocal` | Test chạy thread khác, mất transaction context | Dùng timeout không preemptive hoặc điều phối context đúng |
| Dùng `@BeforeAll` non-static dưới lifecycle mặc định | Không đúng hợp đồng của callback thông thường | Dùng `static` hoặc `@TestInstance(PER_CLASS)` |
| Bật `PER_CLASS` rồi để state mutable giữa tests | Test bị phụ thuộc thứ tự, race khi parallel | Reset ở `@BeforeEach` hoặc giữ `PER_METHOD` |
| Tưởng `PER_METHOD` cách ly luôn database và `static` state | Shared external state vẫn còn | Dùng test data riêng, transaction, cleanup |
| Tạo hai `@BeforeEach` có phụ thuộc thứ tự | JUnit không hứa thứ tự như mong muốn | Gộp thành một method setup |
| Dùng `@TempDir` nhưng viết vào file cố định bên ngoài | Có thể va chạm/rò dữ liệu giữa tests | Đặt file bên trong `tempDir.resolve(...)` |
| Quên đóng socket/client/executor | Resource leak khiến tests khác lỗi | `@AutoClose`, `@AfterEach` hoặc try-with-resources |
| Dùng `Thread.sleep` để chờ async work | Flaky do scheduler và load | Future/completion condition với deadline |
| Giữ `static` mutable collections làm input giữa tests | Test phụ thuộc thứ tự chạy | Fixture riêng, immutable reference data |
| Bật song song với DB schema/file path chung | Race và data corruption | Isolation/resource coordination |
| Bỏ qua integration error bằng `assumeTrue(false)` | Che lỗi thật thành skipped | Assumptions chỉ cho yêu cầu môi trường hợp lệ |
| `@Disabled` không có lý do hoặc không theo dõi | Suite xanh giả tạo lâu dài | Có issue/lý do và kế hoạch bật lại |
| Dùng `org.junit.Test` cùng Jupiter rồi mong mọi annotation được nhận | Trộn APIs/engines khác nhau | Import `org.junit.jupiter.api.Test` |
| Tin `junit-jupiter` đã nằm trong JDK 27 | Thiếu dependency và test engine | Cấu hình Maven/Gradle và JUnit Platform |
| Dùng JUnit Vintage làm nền tảng test mới | Vintage chỉ hỗ trợ chuyển đổi test cũ | Viết mới bằng Jupiter |
| Hardcode fixtures cần network/DB production | Test không độc lập, rủi ro thay đổi dữ liệu | Dùng test environment và fake/stub phù hợp |
| Chạy đúng một lần rồi kết luận test không flaky | Không kiểm tra sự phụ thuộc tải hoặc order | Chạy lại, random hóa thứ tự khi cần, xem race/clock |

## 24. Checklist review chất lượng kiểm thử

1. **Tên test có diễn đạt hành vi và kỳ vọng không?** Đọc tên có hiểu trường hợp được bảo vệ?
2. **Có Arrange–Act–Assert rõ ràng không?** Đâu là hành động chính và assertion cốt lõi?
3. **Test có thể fail khi contract bị vi phạm không?** Thử sửa đầu ra sai có bị phát hiện?
4. **Expected và actual có đúng thứ tự không?** Kiểu so sánh là value, identity hay numerical tolerance?
5. **Có kiểm tra các giá trị biên, input `null`/rỗng và đường exception không?**
6. **`assertThrows` có lambda đủ hẹp không?** Cần `assertThrowsExactly` hay kiểm tra `cause/message`?
7. **Các assertions có xác nhận kết quả quan sát được không?** Tránh chỉ test method không ném lỗi.
8. **Fixture per-test có độc lập không?** Không phụ thuộc test nào chạy trước.
9. **`@BeforeEach` và `@AfterEach` có trách nhiệm rõ ràng không?** Setup và cleanup có phạm vi tương ứng?
10. **Dùng `@BeforeAll` chỉ với resource có thể chia sẻ an toàn?** Có teardown phù hợp?
11. **Nếu dùng `PER_CLASS`, shared mutable state đã được reset hoặc bảo vệ chưa?**
12. **Có nhiều lifecycle methods phụ thuộc thứ tự trong cùng class không?** Nên gom lại khi cần thứ tự.
13. **Tài nguyên file/network/executor được đóng bằng `@TempDir`, `@AutoClose` hay try-with-resources chưa?**
14. **Parameterized test có dữ liệu đọc được và assertions độc lập cho từng invocation không?**
15. **Nested tests có thêm bối cảnh rõ thay vì tạo workflow phụ thuộc test trước không?**
16. **Có phụ thuộc thời gian thực, timezone, locale hoặc random không?** Inject `Clock`/seed khi thích hợp.
17. **Test timeout có thể làm hỏng transaction context hoặc để task chạy sau khi báo fail không?**
18. **Có tách unit/integration/end-to-end và các dependencies cần thiết không?**
19. **JUnit Platform/Jupiter dependencies có đồng bộ phiên bản và tương thích Java 27 không?**
20. **`@Disabled`/assumption có làm ẩn một lỗi sản phẩm đáng lẽ phải fail không?**
21. **Tests có thể chạy riêng một test class/method và chạy trong CI mà không cần dữ liệu từ lần trước không?**
22. **Khi bật parallel, có tài nguyên toàn cục hay file/DB dùng chung gây race không?**
23. **Thông báo lỗi assertion có đủ cụ thể để debug, không lộ dữ liệu nhạy cảm không?**
24. **Build thực sự chạy tests và báo fail đúng khi assertion sai không?** Kiểm tra Surefire/Gradle test report.

## 25. Tổng kết

**JUnit Jupiter** cung cấp mô hình kiểm thử hiện đại cho Java 27, với `@Test` để biểu diễn hành vi cần kiểm tra, `Assertions` để đối chiếu kết quả và các lifecycle annotations để quản lý fixtures. Dùng JUnit Platform với Gradle/Maven được cấu hình nhất quán; không nhầm JUnit (dependency ngoài) với API tích hợp sẵn trong JDK.

Đối với assertions, hãy so **giá trị** khi hợp đồng nói về giá trị, so **identity** khi hợp đồng nói về cùng instance, và kiểm tra rõ **exception type/message** khi thử đường lỗi. `assertAll` và parameterized tests giúp tăng độ phủ có tổ chức; chúng không thay thế việc chọn kịch bản có ý nghĩa.

Với fixtures, **`PER_METHOD` là lựa chọn mặc định giúp cách ly instance state**. `@BeforeEach` tạo/reset dữ liệu cho từng test, `@AfterEach` giải phóng tài nguyên thuộc test; `@BeforeAll`/`@AfterAll` quản lý phạm vi rộng hơn, còn `PER_CLASS` yêu cầu cẩn trọng với state dùng chung. Ưu tiên `@TempDir`, `@AutoClose` và `try-with-resources` khi phù hợp; đừng phụ thuộc thứ tự test methods hoặc sleep để đồng bộ.

Một bộ kiểm thử đáng tin cậy là bộ kiểm thử **độc lập, có thể lặp lại, có khả năng phát hiện lỗi thực sự và cung cấp thông tin đủ để sửa lỗi**. Đây là nền tảng để mở rộng sang mocking, integration tests, mutation testing và quy trình chất lượng ở những bài tiếp theo.

## Tài liệu tham khảo

- [JUnit 6.1.3 — Overview](https://docs.junit.org/6.1.3/overview.html) — JUnit Platform, Jupiter, Vintage, phiên bản Java được hỗ trợ.
- [JUnit 6.1.3 — User Guide (full)](https://docs.junit.org/6.1.3/_exports/junit-user-guide-6.1.3.html) — annotations, assertions, fixtures, nested tests, lifecycle và extensions.
- [JUnit 6.1.3 — Build Support](https://docs.junit.org/6.1.3/running-tests/build-support.html) — Gradle, Maven, BOM, Surefire và JUnit Platform launcher.
- [JUnit 6.1.3 — Test Instance Lifecycle](https://docs.junit.org/6.1.3/writing-tests/test-instance-lifecycle.html) — `PER_METHOD` mặc định, `PER_CLASS`, cấu hình lifecycle.
- [JUnit 6.1.3 — Parameterized Classes and Tests](https://docs.junit.org/6.1.3/writing-tests/parameterized-classes-and-tests.html) — sources và lifecycle mỗi invocation.
- [JUnit 6.1.3 — Assertions API](https://docs.junit.org/6.1.3/api/org.junit.jupiter.api/org/junit/jupiter/api/Assertions.html) — `assertThrowsExactly`, `assertAll`, timeout và các phép xác minh.
- [JUnit 6.1.3 — Test API](https://docs.junit.org/6.1.3/api/org.junit.jupiter.api/org/junit/jupiter/api/Test.html) — test methods và quy tắc execution order.
- [JUnit 6.1.3 — AutoClose API](https://docs.junit.org/6.1.3/api/org.junit.jupiter.api/org/junit/jupiter/api/AutoClose.html) — quản lý tự động tài nguyên field.
- [JUnit 6.1.3 — Release Notes](https://docs.junit.org/6.1.3/release-notes.html) — thay đổi và tình trạng phiên bản ổn định.
- [Java SE 27 — Objects](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Objects.html) — `requireNonNull` trong mã ứng dụng minh họa.
- [Java SE 27 — Clock](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Clock.html) — đồng hồ có thể inject/test deterministically.
- [Java SE 27 — BigDecimal](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/math/BigDecimal.html) — phép tính tiền chính xác, scale và rounding.
