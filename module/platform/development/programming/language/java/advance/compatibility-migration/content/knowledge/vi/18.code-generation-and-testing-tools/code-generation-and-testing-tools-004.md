# JUnit, Surefire, Failsafe và test engine theo phiên bản Java

Khi nâng cấp một dự án Java từ JDK 8 lên 11, 17, 21 hoặc cao hơn, hệ thống kiểm thử có thể thất bại ngay cả khi mã nghiệp vụ đã biên dịch thành công. Một số trường hợp là lỗi phiên bản Java không tương thích với thư viện test; trường hợp khác xuất phát từ **JUnit test engine** không có trên runtime classpath, Maven Surefire hoặc Failsafe không nhận đúng bài test, plugin chạy test bằng một JVM khác với JVM dùng để compile, hoặc framework mocking/coverage chưa hỗ trợ cơ chế đóng gói module của JDK đích.

Nguy hiểm hơn lỗi test đỏ là tình huống **build xanh nhưng không chạy bài test nào**. Dự án có thể mất hàng trăm bài kiểm thử khi chuyển JUnit 4 sang JUnit Jupiter, đổi tên class test hoặc nâng Maven plugin. Nếu chỉ nhìn exit code của `mvn test`, nhóm phát triển có thể đánh giá sai mức độ tương thích sau migration.

Bài học thuộc chương **Sinh mã và công cụ test** của module **Java Advance Compatibility Migration**. Nội dung tập trung vào việc phân biệt **JUnit framework, JUnit Platform, test engine, Maven Surefire, Maven Failsafe**, chọn các phiên bản phù hợp với JDK và xây dựng quy trình kiểm tra có thể tái lập qua nhiều môi trường.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt JUnit 4, JUnit Jupiter, JUnit Platform và JUnit Vintage.
- Giải thích vì sao có test API nhưng thiếu test engine thì test không được phát hiện/chạy đúng.
- Hiểu nhiệm vụ của Maven Surefire trong pha `test` và Maven Failsafe trong các pha integration test.
- Chọn cấu hình thư viện, plugin và Java runtime phù hợp với phiên bản JDK mục tiêu.
- Chuyển test từ JUnit 4 sang Jupiter theo từng bước, không vô tình mất bài test cũ.
- Cấu hình Maven hoặc Gradle để chạy JUnit Platform, đồng thời quản lý các dependency test-only.
- Chẩn đoán `NoClassDefFoundError`, `UnsupportedClassVersionError`, `TestEngine` discovery failure, JPMS reflection error và kết quả “Tests run: 0”.
- Tổ chức ma trận CI để bảo đảm **đúng test, đúng JVM, đúng engine và đúng môi trường**.

## 2. Bức tranh tổng thể: JUnit và build tool làm những việc khác nhau

### 2.1. Bốn thành phần trong một lượt chạy test

Một luồng kiểm thử phổ biến có thể được hình dung:

```text
Mã test (*.java)
      |
      v
JUnit API: @Test, assertions, lifecycle annotations
      |
      v
JUnit Test Engine: khám phá và thực thi test
      |
      v
JUnit Platform Launcher / provider của build tool
      |
      v
Maven Surefire / Maven Failsafe / Gradle Test / IDE
      |
      v
JVM chạy test, classpath/module path, extension, mocking, report
```

Đây là mô hình khái niệm. Trong thực tế, engine, launcher và provider phối hợp theo cơ chế cụ thể của từng phiên bản công cụ. Điểm cần nhớ là **JUnit annotation không tự mở một tiến trình chạy test**, và Maven Surefire không phải một JUnit test engine.

### 2.2. JUnit 4 là gì?

JUnit 4 sử dụng các API quen thuộc:

```java
import org.junit.Test;
import static org.junit.Assert.assertEquals;

public class CalculatorTest {
    @Test
    public void addsTwoNumbers() {
        assertEquals(5, 2 + 3);
    }
}
```

Các thành phần như `@Before`, `@After`, `@RunWith`, `@Rule` và `@Category` thuộc hệ sinh thái JUnit 4. Công cụ thực thi có thể sử dụng runner của JUnit 4 hoặc đi qua **JUnit Vintage engine** trên JUnit Platform.

JUnit 4 vẫn hiện diện trong nhiều codebase legacy. Nâng JDK không tự yêu cầu đổi toàn bộ annotation sang Jupiter; nhưng cần bảo đảm runner/provider và các extension JUnit 4 cũ thực sự tương thích JDK đích.

### 2.3. JUnit Jupiter là gì?

JUnit Jupiter là mô hình lập trình và thực thi test hiện đại của JUnit 5, cũng tiếp tục được sử dụng trong các thế hệ JUnit mới phù hợp với phiên bản Java yêu cầu.

Ví dụ:

```java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(5, 2 + 3);
    }
}
```

Khác biệt đáng chú ý:

- Annotation là `org.junit.jupiter.api.Test`, **không** phải `org.junit.Test` của JUnit 4.
- Test class và method thông thường có thể có quyền package-private; không cần `public` như nhiều trường hợp JUnit 4.
- Lifecycle dùng `@BeforeEach`, `@AfterEach`, `@BeforeAll` và `@AfterAll`.
- Cơ chế mở rộng dùng `@ExtendWith` và Jupiter Extension API.
- Test được thực thi bởi **JUnit Jupiter TestEngine** khi launcher tìm thấy engine thích hợp.

### 2.4. JUnit Platform là gì?

**JUnit Platform** cung cấp hạ tầng khám phá và chạy các bài test thông qua mô hình TestEngine. Platform không đồng nghĩa chỉ có Jupiter; một launcher có thể tìm và chạy nhiều engine cùng tồn tại trong runtime.

Các thành phần thường được nhắc đến:

| Thành phần | Vai trò |
| --- | --- |
| `junit-jupiter-api` | Annotation, assertions và API dùng khi viết Jupiter test. |
| `junit-jupiter-engine` | `TestEngine` khám phá và thực thi Jupiter test. |
| `junit-jupiter-params` | Hỗ trợ parameterized test của Jupiter. |
| `junit-platform-launcher` | API để công cụ như IDE/build runner yêu cầu khám phá và chạy test. |
| `junit-vintage-engine` | `TestEngine` chạy các test JUnit 3/4 trên JUnit Platform, phục vụ chuyển đổi. |
| `junit:junit` | Framework JUnit 4, cần thiết nếu test còn import API JUnit 4. |

Tên artifact và cách khai báo dependency có thể khác tùy thế hệ JUnit. Cần dựa trên BOM/hướng dẫn của **đúng phiên bản đang sử dụng**, thay vì trộn tùy tiện artifact giữa các major release.

### 2.5. Vì sao phải phân biệt “API” và “engine”?

Ví dụ một module có `junit-jupiter-api` trong test compile classpath, nên đoạn source sau biên dịch được:

```java
import org.junit.jupiter.api.Test;

class ExampleTest {
    @Test
    void runs() {}
}
```

Nhưng nếu runtime không có Jupiter engine hoặc runner chưa được cấu hình JUnit Platform, bài test có thể không chạy hoặc launcher phát lỗi discovery. Vì vậy:

**“Test compile thành công” không có nghĩa “test đã thực thi”.**

Bằng chứng cần xem là số lượng test được khám phá/chạy, kết quả trong report và log engine/runner.

## 3. Chọn phiên bản theo Java: kiểm tra nhiều lớp tương thích

### 3.1. Những thành phần có thể có mức Java tối thiểu khác nhau

Một hệ thống kiểm thử thường có nhiều thành phần chạy trong JVM:

1. Source và class file của mã ứng dụng.
2. Source và class file của test.
3. JUnit API/Jupiter engine/Vintage engine.
4. JUnit Platform Launcher.
5. Maven Surefire/Failsafe provider hoặc Gradle Test infrastructure.
6. Mocking/proxy/bytecode libraries như Mockito, Byte Buddy, ASM.
7. Coverage và instrumentation agent như JaCoCo.
8. Framework integration, test container, database driver và ứng dụng được kiểm thử.

Mỗi thành phần có thể yêu cầu phiên bản Java tối thiểu riêng. Một dependency test mới hơn có thể khiến test JVM không khởi động, ngay cả khi sản phẩm vẫn được thiết kế để hỗ trợ Java 8.

### 3.2. Quy tắc với các dòng JUnit phổ biến

Về định hướng tương thích:

- **JUnit 4.13.x** thuộc thế hệ framework cũ, được dùng rộng rãi trong các dự án Java 8; cần xem runner và extension đi kèm khi lên JDK mới.
- **JUnit 5.x** có nền tảng Java 8 và cung cấp Jupiter/Platform/Vintage, phù hợp với nhiều dự án phải duy trì bytecode Java 8 trong khi nâng JVM thực thi.
- **JUnit 6.x** nâng mức Java tối thiểu lên Java 17; không chọn dòng này nếu test runtime vẫn phải chạy bằng Java 8 hoặc 11.

Mốc trên là **mức yêu cầu của dòng JUnit**, không bảo đảm mọi phiên bản plugin và thư viện test liên quan đều tương thích. Khi chọn bản release cụ thể, xem release notes và Java baseline của **từng artifact**. Không tự kết luận plugin Maven hoặc phiên bản Mockito hỗ trợ JDK đích chỉ vì JUnit đã hỗ trợ.

### 3.3. Ma trận định hướng khi migration

| JDK chạy test | Lựa chọn framework phổ biến | Điểm cần kiểm tra |
| --- | --- | --- |
| Java 8 | JUnit 4 hoặc dòng JUnit 5 tương thích Java 8 | Surefire/provider, Jupiter engine, Java bytecode của plugin/test dependency. |
| Java 11 | JUnit 4 hoặc JUnit 5.x | Engine discovery, Byte Buddy/Mockito/coverage, API bị tách khỏi JDK. |
| Java 17 | JUnit 5.x hoặc dòng JUnit mới có Java baseline phù hợp | Strong encapsulation, JPMS, JDK agents, reflective access. |
| Java 21+ | Phiên bản JUnit, test framework và tooling có tài liệu hỗ trợ JDK đó | Phiên bản JaCoCo/ASM/Byte Buddy, dynamic agent, class-file version, module access. |

Đây là một **cách sắp xếp kiểm tra**, không phải bảng “phiên bản mới nhất”. Các phiên bản chính xác phải được khóa trong build và đối chiếu với JDK do CI thực thi.

### 3.4. Java dùng để biên dịch khác Java dùng để chạy test

Một build có thể dùng JDK 21 để compile mã với `--release 11`. Bytecode sản phẩm khi đó nhắm Java 11, nhưng test vẫn có thể được chạy bằng JDK 21.

Ngược lại, nếu test dependency được biên dịch cho Java 17 mà JVM thực thi test là Java 11, runtime sẽ báo:

```text
java.lang.UnsupportedClassVersionError
```

Đừng chỉ nhìn `maven.compiler.release` để suy ra JDK chạy Surefire. Cần xác nhận **JVM được Surefire/Failsafe thực thi thực tế**, bao gồm toolchain và cấu hình fork.

## 4. Maven Surefire: chạy unit test trong pha `test`

### 4.1. Vai trò của Surefire

**Maven Surefire Plugin** chạy những bài test được cấu hình trong giai đoạn `test` của Maven lifecycle. Nó có cơ chế provider để giao việc thực thi cho framework thích hợp, ví dụ JUnit Platform khi runtime đã có test engine.

Luồng Maven phổ biến:

```text
validate -> compile -> test-compile -> test -> package -> verify
                                        |
                                        +-- Maven Surefire
                                            (unit test theo cấu hình)
```

Lệnh:

```bash
mvn test
```

thường chạy quá trình compile/test-compile cần thiết rồi đến Surefire. Nhưng nó **không tự động chạy Failsafe integration test** theo cách mong muốn nếu dự án chưa cấu hình plugin Failsafe.

### 4.2. Test class naming và inclusion patterns

Surefire có những quy tắc tên test mặc định phổ biến, ví dụ:

```text
Test*.java
*Test.java
*Tests.java
*TestCase.java
```

Các pattern thực tế áp dụng cho lớp test được biên dịch. Nếu nhóm đổi tên tất cả class sang `*IT` hoặc `*Spec` nhưng không cấu hình includes tương ứng, Surefire có thể không chạy bài nào.

Lưu ý: định nghĩa test được **engine khám phá** vẫn phải hợp lệ. Có class được Surefire chọn không đồng nghĩa Jupiter engine sẽ tìm thấy một test method có annotation đúng.

### 4.3. Unit test report ở đâu?

Trong cấu hình Maven thông thường, Surefire tạo báo cáo tại:

```text
target/surefire-reports/
```

Có thể có file XML theo định dạng test report và log text. Khi migration, không chỉ xem build xanh: cần đọc số lượng `tests`, `failures`, `errors`, `skipped` và tên test được ghi nhận.

### 4.4. Cấu hình Maven Surefire cho Jupiter

Ví dụ `pom.xml` dùng một bộ phiên bản minh họa, không phải gợi ý “latest”:

```xml
<properties>
    <maven.compiler.release>11</maven.compiler.release>
    <junit.version>5.11.4</junit.version>
    <surefire.version>3.5.2</surefire.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.11.4</version>
        <scope>test</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.2</version>
        </plugin>
    </plugins>
</build>
```

`junit-jupiter` là artifact tổng hợp trong dòng JUnit 5, giúp kéo các thành phần Jupiter thích hợp theo metadata của phiên bản tương ứng. Với cấu hình phụ thuộc khác, cần khai báo `junit-jupiter-engine` test runtime rõ ràng.

Các số version ở đây chỉ dùng để minh họa một cấu hình cụ thể; trong dự án thật hãy chọn phiên bản Maven plugin và JUnit đã xác minh tương thích với JDK/CI hiện tại, khóa chúng trong quản lý version và kiểm tra dependency tree.

### 4.5. Maven provider và engine discovery

Surefire 3.x thường có khả năng chạy JUnit Platform khi cấu hình đúng. Cơ chế provider thực tế phụ thuộc version và test classpath. Các điểm cần xác nhận:

- `junit-platform` infrastructure và test engine hiện diện đúng phiên bản.
- `org.junit.jupiter:junit-jupiter-engine` được đưa vào runtime qua dependency.
- Không có phiên bản JUnit Platform/Jupiter xung đột do dependency mediation.
- Test class được chọn bởi includes/excludes của Surefire.
- Không có cấu hình tag/engine filter loại hết test.
- JVM fork có classpath/module path phù hợp.

Nếu engine không có mặt, việc thêm annotation `@Test` vào source không giải quyết được vấn đề.

## 5. Maven Failsafe: chạy integration test và gate ở pha `verify`

### 5.1. Vì sao có Failsafe riêng?

**Maven Failsafe Plugin** được thiết kế cho kiểm thử tích hợp có thể cần ứng dụng, database, container hoặc các service phụ trợ đã được chuẩn bị trong lifecycle.

Thông thường plugin gắn hai goal:

- `failsafe:integration-test`: chạy bài integration test.
- `failsafe:verify`: đọc kết quả và khiến build thất bại khi có lỗi test theo cấu hình.

Luồng điển hình:

```text
package
  |
  v
pre-integration-test -> chuẩn bị hạ tầng nếu dự án cấu hình
  |
  v
integration-test -> Failsafe chạy integration tests
  |
  v
post-integration-test -> dọn dẹp hạ tầng nếu dự án cấu hình
  |
  v
verify -> Failsafe kiểm tra kết quả và đánh dấu build thất bại
```

Không phải chỉ cần đặt tên `*IT` thì Maven tự chạy integration test; cần bind plugin và lifecycle đúng cách.

### 5.2. Vì sao nên chạy `mvn verify`?

Ví dụ:

```bash
mvn verify
```

Khi đã cấu hình Surefire và Failsafe đúng, lệnh này chạy các pha cần thiết và kiểm tra kết quả integration test ở `verify`.

**Không dùng riêng `mvn integration-test` làm quality gate cuối cùng** rồi giả định đã kiểm tra đầy đủ kết quả Failsafe: goal `verify` mới là bước tổng kết fail/pass theo cách plugin được thiết kế, đồng thời cho phép các bước dọn dẹp sau integration test trong lifecycle chạy đúng thứ tự.

### 5.3. Quy ước tên test của Failsafe

Các pattern mặc định phổ biến:

```text
IT*.java
*IT.java
*ITCase.java
```

Nếu integration test đặt tên `OrderIntegrationTest`, cần khai báo include phù hợp hoặc điều chỉnh quy ước để Failsafe thực sự phát hiện.

Không nên tạo overlap giữa Surefire và Failsafe khiến một bài test chạy hai lần ngoài ý muốn.

### 5.4. Ví dụ cấu hình Failsafe với Jupiter

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <version>3.5.2</version>
    </plugin>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-failsafe-plugin</artifactId>
      <version>3.5.2</version>
      <executions>
        <execution>
          <goals>
            <goal>integration-test</goal>
            <goal>verify</goal>
          </goals>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
```

JUnit Jupiter engine nằm trong test dependencies của dự án, không tự xuất hiện chỉ vì Failsafe được khai báo. Nếu cần truy cập hạ tầng integration test, cấu hình khởi tạo, chờ readiness và cleanup trong các pha phù hợp.

Các thư mục báo cáo thường gặp:

```text
target/surefire-reports/
target/failsafe-reports/
```

Khi migration, ghi lại số lượng unit và integration tests riêng, không gộp thành một con số mơ hồ.

## 6. Vấn đề đặc biệt: JUnit 4, Jupiter và Vintage cùng tồn tại

### 6.1. Test JUnit 4 không tự trở thành Jupiter test

Test cũ:

```java
import org.junit.Before;
import org.junit.Test;
import static org.junit.Assert.assertEquals;

public class LegacyMathTest {
    private Calculator calculator;

    @Before
    public void setUp() {
        calculator = new Calculator();
    }

    @Test
    public void adds() {
        assertEquals(4, calculator.add(1, 3));
    }
}
```

Đổi dependency sang `junit-jupiter-api` nhưng giữ `org.junit.Test` không có nghĩa Jupiter engine sẽ chạy test này. API JUnit 4 và Jupiter là hai loại annotation khác nhau.

Có ba hướng:

1. Giữ runner/provider JUnit 4 trong giai đoạn chuyển tiếp.
2. Dùng **JUnit Vintage engine** để chạy test JUnit 4 trên JUnit Platform.
3. Di chuyển từng test sang Jupiter và bỏ Vintage khi hoàn tất.

### 6.2. Vintage engine dùng để làm gì?

Vintage là `TestEngine` cho phép JUnit Platform chạy test JUnit 3/4. Ví dụ một dự án hỗn hợp có thể khai báo:

```xml
<dependency>
    <groupId>junit</groupId>
    <artifactId>junit</artifactId>
    <version>4.13.2</version>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.junit.vintage</groupId>
    <artifactId>junit-vintage-engine</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>
```

Ví dụ này giả định các thành phần Jupiter/Platform còn lại cùng dòng tương thích. Không trộn Vintage engine ở một major version với Jupiter/Platform khác major mà chưa kiểm tra compatibility.

Trong những dòng JUnit mới, tình trạng hỗ trợ hoặc cung cấp Vintage có thể thay đổi; cần xác nhận release notes khi lựa chọn phiên bản. Vintage là công cụ **chuyển tiếp**, không phải mục tiêu để duy trì JUnit 4 mãi mãi.

### 6.3. Cảnh báo khi một class dùng annotation của cả hai framework

Một class đồng thời import `org.junit.Test` và `org.junit.jupiter.api.Test` dễ gây nhầm lẫn: có method do Vintage phát hiện, method khác do Jupiter phát hiện, còn lifecycle annotation có thể không khớp engine.

Ví dụ `@Before` của JUnit 4 không phải `@BeforeEach` của Jupiter. Nếu method Jupiter test kỳ vọng fixture được tạo bởi `@Before`, test có thể lỗi dù source compile.

Nên migration theo **từng class** hoặc từng tập test rõ ràng, không thêm annotation mới một cách cơ học vào một nửa method rồi dựa vào runner tự suy đoán.

### 6.4. Bảng ánh xạ JUnit 4 sang Jupiter

| JUnit 4 | JUnit Jupiter | Điểm cần chú ý |
| --- | --- | --- |
| `org.junit.Test` | `org.junit.jupiter.api.Test` | Hai annotation khác nhau. |
| `@Before` | `@BeforeEach` | Lifecycle trước mỗi test. |
| `@After` | `@AfterEach` | Lifecycle sau mỗi test. |
| `@BeforeClass` | `@BeforeAll` | Điều kiện static/`PER_CLASS` tùy cấu hình. |
| `@AfterClass` | `@AfterAll` | Tương tự lifecycle class. |
| `@Ignore` | `@Disabled` | Cần kiểm tra lý do và cách report skipped. |
| `@RunWith` | `@ExtendWith` hoặc cơ chế engine tương ứng | Không phải mọi runner chuyển đổi 1:1 thành extension. |
| `@Category` | `@Tag` | Cần cập nhật filter Surefire/CI. |
| `@Rule` / `@ClassRule` | Extension API hoặc thư viện tương thích | Không có ánh xạ tự động cho mọi rule. |
| `@Test(expected=...)` | `assertThrows(...)` | Kiểm tra phạm vi exception được assert. |
| `@Test(timeout=...)` | `assertTimeout` / `assertTimeoutPreemptively` | Preemptive timeout có thể chạy code ở thread khác, ảnh hưởng thread-local/transaction. |

Đổi test framework có thể làm semantics thay đổi. Cần xem test logic, lifecycle, extension order và báo cáo; không nên dùng replace-all import rồi coi là migration xong.

## 7. Chuyển một test sang Jupiter có kiểm soát

### 7.1. Ví dụ trước migration

```java
import org.junit.Before;
import org.junit.Test;
import static org.junit.Assert.assertEquals;

public class OrderTotalTest {
    private OrderCalculator calculator;

    @Before
    public void init() {
        calculator = new OrderCalculator();
    }

    @Test
    public void calculatesTotal() {
        assertEquals(120, calculator.total(100, 20));
    }
}
```

### 7.2. Ví dụ sau migration

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderTotalTest {
    private OrderCalculator calculator;

    @BeforeEach
    void init() {
        calculator = new OrderCalculator();
    }

    @Test
    void calculatesTotal() {
        assertEquals(120, calculator.total(100, 20));
    }
}
```

Trong ví dụ này, phép chuyển tương đối trực tiếp vì test chỉ có fixture instance đơn giản. Với runner tùy chỉnh, rule, concurrency, parameterized test hoặc Spring context, cần thêm extension/cấu hình tương ứng và kiểm tra tác động.

### 7.3. Test exception và timeout

JUnit 4 có thể dùng:

```java
@Test(expected = IllegalArgumentException.class)
public void rejectsInvalidInput() {
    service.process(null);
}
```

Jupiter thường dùng:

```java
@Test
void rejectsInvalidInput() {
    assertThrows(IllegalArgumentException.class,
        () -> service.process(null));
}
```

Cách thứ hai cho phép kiểm soát phạm vi lệnh dự kiến ném exception, giảm trường hợp một lệnh chuẩn bị fixture ném cùng exception làm test pass ngoài ý muốn.

Với timeout, lựa chọn giữa `assertTimeout` và `assertTimeoutPreemptively` có thể ảnh hưởng cách xử lý thread-local, transaction context và hủy tác vụ. Không thay đổi cơ chế timeout mà chưa test.

### 7.4. Parameterized test

JUnit Jupiter hỗ trợ parameterized test qua `junit-jupiter-params`:

```java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import static org.junit.jupiter.api.Assertions.assertEquals;

class DiscountTest {
    @ParameterizedTest
    @CsvSource({
        "100, 10, 90",
        "200, 20, 160"
    })
    void appliesDiscount(int price, int discount, int expected) {
        assertEquals(expected, price - (price * discount / 100));
    }
}
```

Để engine khám phá test này, cần API/params/engine tương thích. Bản JUnit Jupiter aggregate thường đã gồm các thành phần tương ứng; khi khai báo riêng từng artifact phải bảo đảm không thiếu `junit-jupiter-params`.

## 8. Maven: cấu hình đầy đủ cho giai đoạn chuyển đổi

Giả sử dự án Java 11 còn cả JUnit 4 và Jupiter tests. Một cấu hình minh họa:

```xml
<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>legacy-migration</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>11</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.11.4</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>junit</groupId>
      <artifactId>junit</artifactId>
      <version>4.13.2</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.vintage</groupId>
      <artifactId>junit-vintage-engine</artifactId>
      <version>5.11.4</version>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.2</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-failsafe-plugin</artifactId>
        <version>3.5.2</version>
        <executions>
          <execution>
            <goals>
              <goal>integration-test</goal>
              <goal>verify</goal>
            </goals>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
```

Đây là **ví dụ cấu hình có phiên bản cố định**, không phải một bộ phiên bản bảo đảm phù hợp mọi dự án hoặc mới nhất ở thời điểm đọc. Đặc biệt nếu JDK mục tiêu khác Java 11, cần kiểm tra lại plugin compatibility và Java baseline.

Sau khi chuyển xong JUnit 4 tests, loại dependency JUnit 4 và Vintage theo kế hoạch, chỉ khi xác nhận không còn runner/extension/engine cần chúng.

## 9. Gradle: `useJUnitPlatform()` và runtime engine

### 9.1. Cấu hình Jupiter cơ bản

Ví dụ Gradle Groovy DSL:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

`useJUnitPlatform()` nói với Gradle dùng JUnit Platform để khám phá/chạy test. Nó không tự cấp mọi engine dependency cần thiết. `junit-jupiter` đem vào những thành phần Jupiter theo metadata của dependency, còn `junit-platform-launcher` phải được căn chỉnh với thế hệ Platform tương thích.

Ví dụ dùng JDK 17 làm toolchain nhưng `junit-jupiter` phiên bản thuộc dòng Java 8 baseline; việc chọn JDK toolchain cần phù hợp với mục tiêu ứng dụng.

### 9.2. Khi có JUnit 4 tests

Nếu muốn dùng Vintage trong giai đoạn chuyển đổi:

```groovy
dependencies {
    testImplementation 'junit:junit:4.13.2'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.vintage:junit-vintage-engine:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

Nếu không dùng Vintage hoặc một runner riêng cho JUnit 4, các test cũ có thể không được thực thi khi chuyển task sang JUnit Platform.

### 9.3. Gradle không tự có Failsafe

Surefire và Failsafe là **Maven plugins**, không phải task mặc định của Gradle. Trong Gradle, integration test thường được tạo qua source set hoặc test suite riêng, với task `Test` cấu hình runtime classpath và `useJUnitPlatform()`.

Ví dụ ý tưởng:

```groovy
tasks.register('integrationTest', Test) {
    useJUnitPlatform()
    // Cấu hình testClassesDirs, classpath, dependency và lifecycle
    // theo source set hoặc JVM test suite của dự án.
}
```

Đoạn minh họa này chưa đủ để chạy integration test nếu chưa tạo source set/test suite và các phụ thuộc. Không thể thay `mvn verify` bằng một lệnh Gradle có tên giống vậy nếu dự án chưa khai báo đầy đủ task.

## 10. JUnit test engine được tìm bằng cơ chế nào?

### 10.1. TestEngine là plugin của Platform

JUnit Platform có API `org.junit.platform.engine.TestEngine`. Các engine triển khai API này để khám phá và thực thi test thuộc mô hình riêng.

Trong cấu hình classpath truyền thống, engine có thể được phát hiện qua cơ chế Java ServiceLoader và metadata dưới `META-INF/services`. Trên module path, việc khám phá cũng cần xét `provides`/`uses`, module resolution và class loader.

Vì vậy, các thao tác như shading, relocation, minimization hoặc tạo executable fat JAR có thể làm mất resource/provider liên quan đến test engine.

### 10.2. Thiếu engine, engine không phù hợp hoặc xung đột phiên bản

Các lỗi khác nhau cần phân loại:

| Tình huống | Triệu chứng có thể |
| --- | --- |
| Chỉ có Jupiter API, thiếu Jupiter engine | Không tìm thấy engine thích hợp hoặc test không được chạy theo kỳ vọng. |
| Runtime có nhiều Platform versions không tương thích | `NoSuchMethodError`, `NoClassDefFoundError` hoặc lỗi khám phá engine. |
| Có Vintage nhưng thiếu JUnit 4 hoặc engine không tương thích | Lỗi khám phá/chạy legacy tests. |
| Metadata `META-INF/services` bị mất khi shading | Launcher không thấy engine/provider. |
| Engine có mặt nhưng test class bị exclude | Build có thể chạy 0 test thuộc scope. |
| Engine được lọc bằng include/exclude engine hoặc tags | Chỉ một phần test được thực thi. |

Hướng điều tra là kiểm tra **test runtime classpath**, service metadata, plugin provider, engine selection và báo cáo, không chỉ thêm thêm một dependency theo phỏng đoán.

### 10.3. Engine ID và cách chia nhóm

Jupiter và Vintage có engine ID riêng (thường lần lượt là `junit-jupiter` và `junit-vintage`). Một số launcher/runner cho phép include hoặc exclude engine cụ thể.

Việc bật filter chỉ chạy Jupiter trong giai đoạn còn test JUnit 4 có thể khiến báo cáo xanh nhưng mất toàn bộ legacy tests. Nếu muốn tắt Vintage, phải xác nhận các bài test cũ đã được chuyển hoặc loại khỏi scope có chủ đích.

## 11. JDK mới ảnh hưởng Mockito, Byte Buddy, ASM và JaCoCo

### 11.1. JUnit không phải nguồn duy nhất của lỗi test

Một test đơn giản chỉ dùng `assertEquals` có thể chạy tốt, trong khi test dùng mocking/bytecode instrumentation thất bại trên JDK mới. Lý do thường là dependency của:

- Mockito và inline mocking.
- Byte Buddy hoặc ASM dùng để đọc/sinh class.
- JaCoCo agent đo coverage.
- Spring Test, Hibernate, CDI hoặc framework tạo proxy.
- Annotation processor hoặc generated test fixtures.
- Testcontainers và thư viện integration khác.

Những công cụ này có thể chạm đến class-file format, reflection, Java agent hoặc APIs thay đổi theo JDK.

### 11.2. `UnsupportedClassVersionError`

Ví dụ test JVM thấp hơn phiên bản class file:

```text
UnsupportedClassVersionError:
  ... has been compiled by a more recent version of the Java Runtime
```

Đây không phải lỗi do JUnit annotation. Cần so Java class file version của ứng dụng, test, engine hoặc plugin và JDK đang thực thi.

Một dự án compile bằng JDK 21 với `--release 11` nhưng dùng test dependency chỉ hỗ trợ Java 17 vẫn không thể chạy test trên Java 11.

### 11.3. Lỗi Byte Buddy hoặc ASM chưa hỗ trợ class file mới

Một số thư viện có thể báo không nhận diện được class file version của JDK đích, hoặc gợi ý nâng Byte Buddy/ASM. Khi đó, không nên thay `--add-opens` một cách ngẫu nhiên; cần nâng đúng dependency parsing/generating bytecode.

Lưu ý dependency có thể đến **bắc cầu** từ Mockito hoặc framework khác. Kiểm tra dependency tree để biết phiên bản thực sự được chọn.

### 11.4. JaCoCo và coverage

Khi nâng JDK, JaCoCo cần hỗ trợ class file version mới và cơ chế instrumentation được dùng. Một JaCoCo cũ có thể gây lỗi ngay khi test JVM khởi động hoặc khi agent xử lý class mới.

Với Maven, plugin JaCoCo thường đặt Java agent vào thuộc tính `argLine`; Surefire/Failsafe cần tiếp nhận và truyền giá trị này tới forked JVM. Nếu cấu hình `argLine` thủ công ghi đè thay vì gộp, coverage có thể biến mất dù test vẫn pass.

Không nên mặc định report coverage bằng 0 nghĩa là code không chạy; cũng có thể agent không được gắn đúng.

### 11.5. Java agent và dynamic attach

Mocking/instrumentation có thể sử dụng Java agent hoặc cơ chế attach vào JVM. Một số phiên bản JDK phát cảnh báo hoặc siết hành vi liên quan dynamic agent loading. Cần xem chính sách JDK đích, phiên bản Mockito/Byte Buddy/JaCoCo và hướng dẫn của framework.

Nếu cần agent, ưu tiên cấu hình theo cơ chế được hỗ trợ thay vì thêm cờ nhằm ẩn cảnh báo mà chưa hiểu nguyên nhân.

## 12. JPMS, reflection và module path khi chạy test

### 12.1. Khi test module được đặt trên module path

Nếu ứng dụng sử dụng `module-info.java`, Surefire hoặc Gradle có thể tổ chức test bằng module path và cơ chế patch module. Khi đó, bài test có thể chịu quy tắc JPMS về:

- Module readability.
- Package exports.
- Package opens.
- Test class có nằm cùng package/module với production class hay không.
- Runtime engine/launcher có được phân giải và đọc đúng module hay không.

Một test có thể pass khi chạy trên classpath nhưng lỗi trên module path. Không nên coi cách chạy IDE là bằng chứng CI modular cũng đúng.

### 12.2. Lỗi `InaccessibleObjectException`

Các framework reflection/mocking có thể yêu cầu truy cập field hoặc constructor không public. Trên JDK mới, thiếu `opens` hoặc `--add-opens` có thể phát sinh:

```text
java.lang.reflect.InaccessibleObjectException:
  module ... does not "opens ..." to ...
```

Hướng ưu tiên là nâng framework hoặc sửa module descriptor khi sở hữu module. Chỉ dùng `--add-opens` đúng package/target khi thật sự cần trong giai đoạn chuyển tiếp.

Ví dụ minh họa JVM chạy test trên classpath:

```text
--add-opens java.base/java.lang=ALL-UNNAMED
```

Không dùng cờ này mặc định cho mọi dự án. Nó mở quyền khá rộng cho các unnamed modules và không khắc phục lỗi class-file format hoặc engine discovery.

### 12.3. Đặt cờ ở JVM nào?

Với Maven Surefire, `argLine` thường dùng để truyền JVM arguments cho forked test JVM:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <version>3.5.2</version>
  <configuration>
    <argLine>
      --add-opens java.base/java.lang=ALL-UNNAMED
    </argLine>
  </configuration>
</plugin>
```

Ví dụ chỉ để minh họa vị trí cấu hình. Nếu dự án có JaCoCo hoặc JVM arguments khác, phải gộp `argLine` đúng cách, không ghi đè. Với Failsafe, cần kiểm tra cấu hình của JVM integration test riêng.

Không thêm cờ vào compiler plugin rồi giả định nó được truyền cho test JVM. Đây là hai tiến trình hoặc ngữ cảnh khác nhau.

### 12.4. `useModulePath` và workaround

Một số bản Surefire hỗ trợ cấu hình `useModulePath` để kiểm soát cách đặt lớp khi chạy test. Chuyển hết test về classpath có thể là một workaround hữu ích trong một bước migration, nhưng nó cũng có thể che lỗi module-path thực sự mà production sẽ gặp.

Nên ghi rõ quyết định: hệ thống cam kết chạy classpath hay module path? Test pipeline cần phản ánh kiến trúc triển khai mà sản phẩm hỗ trợ.

## 13. Test “xanh giả” khi không có bài test nào được chạy

### 13.1. Vì sao đây là rủi ro lớn?

Giả sử trước migration:

```text
Tests run: 842, Failures: 0, Errors: 0, Skipped: 7
```

Sau khi đổi JUnit/provider:

```text
Tests run: 0, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Nếu pipeline chỉ kiểm tra exit code, nó có thể cho phép phát hành một bản Java chưa được kiểm chứng.

Có nhiều nguyên nhân:

- Surefire includes không khớp tên class.
- Test class chuyển sang directory/source set không được compile.
- Chỉ còn API Jupiter mà engine không có trên test runtime.
- Mất Vintage engine làm JUnit 4 tests biến mất.
- Tags/engine filters loại toàn bộ tests.
- Profile build vô tình skip test.
- Maven/Gradle task chạy không phải task được CI kỳ vọng.

### 13.2. Cách phòng tránh

Thiết lập ít nhất ba lớp bằng chứng:

1. **Report presence:** báo cáo XML/test result được tạo trong mỗi module cần có test.
2. **Test count:** số bài test được thực thi không giảm đột ngột mà không có giải thích.
3. **Known sentinel test:** có một test đơn giản chắc chắn được khám phá; nếu không có, pipeline phải báo lỗi.

Khi xây chính sách, chú ý module thuần thư viện hoặc BOM có thể **cố ý không có test**. Ngưỡng số lượng test cần phù hợp module, không nên ép mọi module chạy ít nhất một test một cách máy móc.

### 13.3. `failIfNoTests`

Surefire/Failsafe có những tùy chọn kiểm soát phản ứng khi không tìm thấy bài test. Ví dụ trong module được yêu cầu có unit test:

```xml
<configuration>
    <failIfNoTests>true</failIfNoTests>
</configuration>
```

Cần dùng cho phạm vi thích hợp và vẫn đọc report để xác minh số lượng/engine. Tùy chọn này không thay thế kiểm tra đầy đủ các trường hợp filter, skip và mismatch mà build thực tế có thể cho là hợp lệ.

### 13.4. Không chỉ đếm test class

Một test class có thể chứa nhiều parameterized invocations hoặc dynamic tests. Số lần thực thi hiển thị trong report có thể khác số method `@Test` hoặc số file `*Test.java`.

Khi lập baseline, ghi rõ metric mà CI theo dõi (test cases, containers, invocations hoặc report count) để so sánh chính xác.

## 14. Kiểm tra môi trường Maven/CI thật sự

### 14.1. Kiểm tra Java và Maven

Trên máy hoặc agent CI:

```bash
java -version
javac -version
mvn -version
```

Các lệnh giúp thấy JDK/JRE và Maven đang dùng. Tuy nhiên, Maven toolchain hoặc cấu hình test fork có thể dùng một JDK khác, nên cần đọc log plugin và cấu hình fork để xác định JVM thực thi test.

### 14.2. Maven Toolchains

Khi dự án hỗ trợ nhiều JDK, Maven Toolchains có thể tách JDK chạy Maven khỏi JDK được một số plugin sử dụng. Không phải mọi plugin hoặc mọi cấu hình đều mặc nhiên tuân theo toolchain giống nhau.

Nếu CI nói “test Java 11”, cần xác minh:

- JDK nào chạy Maven.
- JDK nào được compiler plugin chọn.
- JDK nào được Surefire/Failsafe dùng cho test JVM.
- JDK nào được container hoặc process do integration test khởi động.
- JDK nào chạy application dưới test.

### 14.3. Ma trận build gợi ý

Ví dụ sản phẩm hỗ trợ Java 11, 17 và 21:

| Stage | JDK | Hoạt động | Điều kiện đạt |
| --- | --- | --- | --- |
| Baseline | JDK 11 | Compile và unit tests theo Java baseline | Không dùng API ngoài release hỗ trợ; đủ test. |
| Compatibility | JDK 17 | Unit và integration tests | Engine, mocking, reflection và data flow đều đúng. |
| Target | JDK 21 | Full verify, coverage, kiểm thử feature chính | Không bỏ sót test, tool hỗ trợ class file/JDK, không lỗi runtime. |

Nếu chỉ phân phối sản phẩm cho Java 17+, có thể thay đổi matrix theo cam kết. Đừng tự chọn mọi JDK chỉ vì chúng tồn tại: mỗi CI job phải có mục tiêu rõ.

### 14.4. Testcontainers và dịch vụ ngoài

Integration test có thể phụ thuộc vào Docker, database, queue, port, timezone, locale và TLS. Khi đổi JDK hoặc CI base image, các yếu tố môi trường này cũng có thể thay đổi.

Để phân biệt lỗi test infrastructure với lỗi ứng dụng:

- Ghi phiên bản image, service và config.
- Thiết lập readiness/healthcheck.
- Tránh dùng sleep cố định làm điều kiện duy nhất.
- Quản lý cleanup sau test.
- Thu thập log của service thất bại.
- Lưu kết quả của cả Surefire và Failsafe.

## 15. Quy trình chẩn đoán khi test không chạy hoặc thất bại

### Bước 1: Chụp baseline trước migration

Ghi JDK, Maven/Gradle, Surefire/Failsafe, JUnit Platform/Jupiter/Vintage, test runtime dependencies, số lượng test theo module và report mẫu.

### Bước 2: Xác định loại test hiện có

Tìm source import:

```text
org.junit.Test                  (JUnit 4)
org.junit.jupiter.api.Test      (Jupiter)
org.junit.jupiter.params.*      (Parameterized Jupiter)
org.junit.runner.RunWith        (JUnit 4 runner)
org.junit.jupiter.api.extension (Jupiter extension)
```

Chú ý các framework tích hợp và test engine bổ sung. Một codebase có thể có nhiều hơn hai loại test.

### Bước 3: Xác minh test class có được biên dịch

Đảm bảo `src/test/java` hoặc source set thực tế được compile. Kiểm tra compile errors, excludes, generated test sources và output test classes.

### Bước 4: Xác minh engine trên test runtime classpath

Với Maven:

```bash
mvn dependency:tree -Dscope=test
```

Với Gradle:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
```

Tìm JUnit Jupiter engine, Vintage nếu cần, Platform Launcher và các phiên bản xung đột.

### Bước 5: Xem Surefire/Failsafe version và cấu hình

Kiểm tra includes/excludes, providers, test selection, tags, engine filters, fork settings, `argLine`, `useModulePath`, toolchain và profiles.

Không chỉ dựa vào version khai báo ở parent POM nếu module con có override.

### Bước 6: Chạy phạm vi nhỏ nhưng có xác nhận số test

Ví dụ:

```bash
mvn -Dtest=CalculatorTest test
```

Trong Gradle:

```bash
./gradlew test --tests com.example.CalculatorTest
```

Chọn test có tên và framework rõ. Nếu test chạy đơn lẻ nhưng biến mất trong full suite, xem filters/includes, engine configuration hoặc tương tác giữa các module.

### Bước 7: Kiểm tra test JVM và lỗi bytecode/reflection

Nếu lỗi `UnsupportedClassVersionError`, xác định version class và Java runtime. Nếu lỗi `InaccessibleObjectException`, tìm module/package cần open và framework thực hiện reflection. Nếu engine discovery lỗi, đọc cause trong stack trace thay vì thêm tùy chọn JVM tùy ý.

### Bước 8: Chạy `verify`, kiểm tra report và coverage

Với Maven dự án đã bind Failsafe:

```bash
mvn clean verify
```

Kiểm tra báo cáo Surefire, Failsafe, coverage và logs integration services. Một build thành công không đủ nếu số test giảm không rõ lý do.

### Bước 9: Khóa phiên bản và cập nhật CI

Chốt plugin/dependency versions, toolchain, source/target release, test runtime, report kiểm chứng và lịch xem xét lại các workaround `--add-opens`.

## 16. Bảng lỗi thường gặp khi nâng JDK và test tooling

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `Tests run: 0` | Test không khớp includes, thiếu engine, skip/filter hoặc sai source set. | Kiểm tra names, testRuntimeClasspath, filters và reports. |
| Jupiter test compile nhưng không chạy | JUnit Platform provider/engine không đúng hoặc không có. | Bổ sung engine/launcher phù hợp, nâng plugin và xác minh discovery. |
| JUnit 4 tests biến mất sau khi bật Jupiter | Thiếu Vintage hoặc runner JUnit 4. | Dùng Vintage trong giai đoạn chuyển tiếp hoặc chuyển test sang Jupiter. |
| `UnsupportedClassVersionError` | Test engine/dependency/class được build cho JDK cao hơn test JVM. | Kiểm tra Java baseline của từng artifact và runtime. |
| `NoSuchMethodError` trong JUnit Platform | Mismatch giữa các thành phần Platform/Jupiter/plugin. | Đồng bộ version, kiểm tra dependency mediation. |
| `NoClassDefFoundError` | Test runtime thiếu dependency hoặc class phiên bản khác. | Kiểm tra test scope và classpath/module path. |
| `ServiceConfigurationError` | Engine/provider metadata lỗi hoặc bị mất khi shading. | Kiểm tra `META-INF/services`, artifact và provider discovery. |
| `InaccessibleObjectException` | Framework reflection vào package chưa open. | Nâng framework; mở package tối thiểu nếu cần. |
| Mockito/mock lỗi trên JDK mới | Byte Buddy/agent/Mockito chưa hỗ trợ JDK/class file. | Nâng dependency và xác minh test JVM. |
| JaCoCo lỗi/instrumentation không chạy | Agent quá cũ hoặc `argLine` bị ghi đè. | Nâng JaCoCo, kiểm tra agent args và report. |
| Unit tests pass, IT không chạy | Failsafe chưa bind hoặc CI chỉ chạy `mvn test`. | Cấu hình Failsafe rồi chạy `mvn verify`. |
| IT chạy nhưng CI không fail dù có lỗi | Chưa thực hiện Failsafe verify hoặc xử lý results sai. | Chạy lifecycle đến `verify` và kiểm tra XML. |
| Test pass IDE nhưng fail Maven | IDE dùng runner/JDK/classpath khác. | Đồng bộ JVM, dependency, engine, module path và filters. |
| Lỗi chỉ ở CI | Toolchain, locale, Docker, service hoặc environment khác. | Ghi môi trường và tái hiện đúng JVM/service runtime. |

## 17. Chính sách phiên bản và dependency management

### 17.1. Dùng một hệ phiên bản JUnit nhất quán

Các thành phần Jupiter, Vintage và Platform cần tương thích theo cấu trúc phiên bản của thế hệ JUnit đó. Đặc biệt với JUnit 5, version của Jupiter/Vintage và Platform thuộc những dãy version khác nhau nhưng phải được căn chỉnh hợp lý.

Một lựa chọn phổ biến là sử dụng **JUnit BOM** phù hợp với release đã chọn hoặc dependency management do framework như Spring Boot công bố, thay vì pin thủ công một số artifact rồi để artifact khác được resolve ở phiên bản bất kỳ.

Không sửa dependency version riêng lẻ theo một lỗi `ClassNotFoundException` mà chưa kiểm tra toàn bộ graph.

### 17.2. Pin Maven Surefire và Failsafe cùng bộ được xác minh

Surefire và Failsafe có thể được khai báo trong parent POM/pluginManagement. Nên chọn các phiên bản đã kiểm tra hỗ trợ JDK mục tiêu và tránh chuyện module A dùng Surefire phiên bản cũ trong khi module B đã nâng.

Một số tổ chức pin cùng phiên bản cho Surefire và Failsafe để dễ quản lý provider và hành vi runtime. Đây là thực hành hợp lý nhưng vẫn cần thử nghiệm các cấu hình thực tế.

### 17.3. Pin test tooling khác

Không quên:

- Mockito và Byte Buddy.
- JaCoCo và các agent khác.
- Spring Test và framework integration.
- Testcontainers/client libraries.
- ASM hoặc bytecode tool được kéo bắc cầu.
- Compiler plugin, Kotlin/Scala/Groovy compiler nếu có.
- Maven/Gradle wrapper và JDK toolchain.

Khi nâng JDK, mỗi thành phần có thể là nguồn gốc lỗi riêng. Bản ghi migration nên nêu phiên bản trước/sau và lý do nâng.

## 18. Mini-lab: phát hiện test suite bị bỏ sót

### 18.1. Bài toán

Một dự án có:

```text
src/test/java/com/example/LegacyAccountTest.java
src/test/java/com/example/NewOrderTest.java
src/test/java/com/example/InventoryIT.java
```

- `LegacyAccountTest` dùng `org.junit.Test`.
- `NewOrderTest` dùng `org.junit.jupiter.api.Test`.
- `InventoryIT` dùng Jupiter và cần database test.

Dự án vừa nâng từ JDK 8 lên JDK 17 và chuyển sang JUnit Platform. Lệnh `mvn test` hiển thị BUILD SUCCESS nhưng chỉ chạy `NewOrderTest`.

### 18.2. Phân tích

Nếu không có Vintage engine hoặc runner phù hợp, `LegacyAccountTest` có thể biến mất khỏi quá trình khám phá. `InventoryIT` có tên mặc định thuộc Failsafe, nên thường không nằm trong nhóm Surefire chạy ở `mvn test`.

Tức là chỉ thấy `NewOrderTest` không nhất thiết vì hai file còn lại lỗi source:

- Legacy test cần Vintage hoặc được chuyển sang Jupiter.
- Integration test cần Failsafe được cấu hình và chạy đến `verify`.

### 18.3. Hướng sửa

1. Thêm Vintage engine tương thích để giữ test JUnit 4 trong giai đoạn migration, hoặc chuyển `LegacyAccountTest` sang Jupiter.
2. Bind Failsafe `integration-test` và `verify`, kiểm tra `InventoryIT` được chọn đúng.
3. Chạy `mvn clean verify` trên JDK 17.
4. Đọc Surefire/Failsafe XML và xác nhận **cả ba nhóm test** đã chạy.
5. Chỉ bỏ Vintage sau khi mọi JUnit 4 test trong phạm vi đã có đường chạy thay thế.

### 18.4. Tiêu chí hoàn tất mini-lab

Kết quả mong đợi không chỉ là BUILD SUCCESS. Báo cáo phải chỉ ra:

- JDK và version plugin/engine đã dùng.
- Test nào chạy dưới Jupiter và test nào dưới Vintage (nếu còn).
- Số lượng test ở Surefire và Failsafe.
- Trạng thái integration environment.
- Không có bài test biến mất do cấu hình hoặc filter ngoài ý muốn.

## 19. Checklist trước khi chốt migration test tooling

- [ ] Đã ghi JDK thực thi Maven/Gradle, JDK compile và JDK test JVM.
- [ ] Đã xác định Java baseline của JUnit, plugins, engine và test dependencies.
- [ ] Đã phân loại test JUnit 4, Jupiter, parameterized, dynamic và integration test.
- [ ] Đã có Jupiter engine/Platform Launcher phù hợp trong test runtime khi dùng Jupiter.
- [ ] Đã giữ Vintage hoặc runner JUnit 4 trong thời gian còn legacy tests.
- [ ] Đã kiểm tra `org.junit.Test` và `org.junit.jupiter.api.Test` không bị nhầm lẫn.
- [ ] Đã thống nhất plugin/dependency versions trong các module.
- [ ] Đã xác minh includes/excludes, tags, engine filters và test source sets.
- [ ] Đã cấu hình Surefire cho unit tests và Failsafe cho integration tests nếu dùng Maven.
- [ ] Đã chạy lifecycle đến `verify` để kiểm tra Failsafe result.
- [ ] Đã đọc XML reports, test count và skipped count trước/sau migration.
- [ ] Đã kiểm tra `failIfNoTests` hoặc quality gate phù hợp cho module bắt buộc có test.
- [ ] Đã nâng Mockito/Byte Buddy/ASM/JaCoCo theo JDK đích.
- [ ] Đã xác định các `--add-opens`/`argLine` cần thiết, không mở quyền vô điều kiện.
- [ ] Đã kiểm tra JPMS/module path nếu ứng dụng thực sự chạy modular.
- [ ] Đã xác minh CI matrix và các external services của integration test.
- [ ] Đã ghi lý do cho test bị xóa, disabled hoặc tạm thời không chạy.
- [ ] Đã lưu baseline và tài liệu rollback nếu thay đổi build/test infrastructure cần hoàn tác.

## 20. Kết luận

**JUnit** cung cấp mô hình viết test và các **test engine**; **JUnit Platform** kết nối engine với launcher; **Maven Surefire** và **Maven Failsafe** quyết định những bài kiểm thử nào được chạy trong các pha Maven khác nhau. Vì vậy, nâng JDK phải kiểm tra đồng thời JUnit API, engine, build plugin, test JVM, mocking/coverage dependencies và cấu hình phát hiện test.

Trong Java Advance Compatibility Migration, chỉ số quan trọng không phải đơn giản là “build xanh”, mà là **đúng tập test đã được khám phá, thực thi bởi engine phù hợp, trên JDK mục tiêu, với report và integration environment đáng tin cậy**. Khi số lượng test, phiên bản công cụ, Java toolchain và kết quả runtime được kiểm soát rõ ràng, test suite mới thực sự là bằng chứng cho khả năng tương thích sau nâng cấp.
