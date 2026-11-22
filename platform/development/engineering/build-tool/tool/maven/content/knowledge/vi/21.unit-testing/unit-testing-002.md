# JUnit Platform, test engine và các phụ thuộc kiểm thử cần thiết

## 1. Từ một annotation đến một bài test thực sự được chạy

Một dự án Java dùng Maven có thể biên dịch được tệp test chứa `@Test` nhưng vẫn không chạy bài kiểm thử nào. Nguyên nhân là **viết test**, **phát hiện test** và **thực thi test** không phải một công việc duy nhất.

Với JUnit 5, có ba vai trò cần hiểu rõ:

- **JUnit Jupiter API**: cung cấp `@Test`, `@ParameterizedTest`, `assertEquals`, `assertThrows` và nhiều API khác để lập trình viên viết test.
- **JUnit Platform + TestEngine**: nền tảng tổ chức quá trình discovery/execution. Một **TestEngine implementation** như Jupiter Engine biết cách nhận diện và thực thi mô hình kiểm thử tương ứng.
- **Maven Surefire Plugin**: tích hợp vào Maven lifecycle và điều phối việc chạy unit tests, thông qua provider hỗ trợ JUnit Platform.

Một dependency API đúng **chưa tự chứng minh** rằng engine và runner hoạt động đúng. Ngược lại, engine có mặt nhưng Surefire không quét lớp test hoặc test bị filter thì số test thực thi có thể vẫn là 0.

```text
src/test/java/dev/lesson/InvoiceTest.java
         |
         | import JUnit Jupiter API / Params
         v
Maven Compiler Plugin: test-compile
         |
         v
target/test-classes/*.class
         |
         v
Maven Surefire Plugin: test phase
         |
         | Surefire provider (cầu nối)
         v
JUnit Platform Launcher
         |
         | discover/select/filter
         v
JUnit TestEngine implementations
         |
         +-- Jupiter Engine --> Jupiter @Test / @ParameterizedTest
         +-- Vintage Engine --> JUnit 3/4 khi cấu hình migration
         +-- Suite Engine   --> declarative suites khi cần
         |
         v
Test results: tests / failures / errors / skipped
         |
         v
target/surefire-reports
```

Bài học tập trung vào **JUnit Platform, test engine và bộ dependencies tối thiểu nhưng đủ dùng**. Ta sẽ dùng một POM Java 17 chạy được, phân biệt API/engine/launcher/provider, dùng JUnit BOM để đồng bộ versions, xem reports và thực hành sửa các lỗi “0 tests”, “thiếu engine” hoặc “Maven không thấy test”.

## 2. JUnit Platform, Jupiter và Vintage là ba khái niệm khác nhau

**JUnit Platform** là nền tảng chuẩn hóa cách các công cụ như IDE, Maven, Gradle và Console Launcher tìm, chạy, thu thập kết quả kiểm thử. Nó định nghĩa các API như `TestEngine`, discovery selectors/filters, test descriptors, `Launcher` và listeners.

**JUnit Jupiter** là mô hình lập trình JUnit hiện đại. Nó có:

- `junit-jupiter-api`: annotations, assertions, lifecycle callbacks và extension API.
- `junit-jupiter-params`: parameterized tests và argument sources.
- `junit-jupiter-engine`: **TestEngine implementation** để chạy những bài test viết theo Jupiter.
- `junit-jupiter`: artifact aggregator kéo các thành phần trên theo metadata Maven.

**JUnit Vintage** cung cấp một TestEngine cho những bài JUnit cũ khi muốn chạy chúng qua JUnit Platform. Dự án mới chỉ dùng Jupiter không cần thêm Vintage.

**JUnit Platform Suite** có API/engine dành cho việc định nghĩa bộ test theo suite; không phải thứ bắt buộc để chạy một lớp `InvoiceTest` thông thường.

| Khái niệm | Đối tượng | Trả lời câu hỏi |
| --- | --- | --- |
| Jupiter API | Code test Java | Tôi viết test và assertions bằng gì? |
| Jupiter Engine | Test runtime | Ai hiểu và chạy `@Test` của Jupiter? |
| JUnit Platform | Hạ tầng discovery/execution | Nền tảng quản lý engine và test plan là gì? |
| Platform Launcher | Tooling/runner integration | Công cụ gửi yêu cầu discovery/execution qua API nào? |
| Maven Surefire | Maven plugin | Ai chạy unit tests ở phase `test`? |
| Vintage Engine | Test migration | Ai chạy JUnit 4/3 qua Platform khi cần? |
| JUnit BOM | Dependency management | Làm sao đồng bộ versions của các module JUnit? |

Đừng nhầm `org.junit.jupiter.api.Test` với `org.junit.Test`. Hai annotation có tên đơn giản giống nhau nhưng thuộc hai programming models khác nhau.

## 3. TestEngine là gì?

`org.junit.platform.engine.TestEngine` là **SPI** (Service Provider Interface) do JUnit Platform định nghĩa. Một implementation có thể:

1. Cung cấp engine ID riêng để nền tảng phân biệt các engines.
2. Nhận một yêu cầu discovery để tìm test containers/test cases phù hợp.
3. Xây dựng descriptors/test plan.
4. Thực thi các test và báo trạng thái qua listener/events.

Ví dụ:

| Artifact implementation | Engine ID thường dùng | Kiểu test |
| --- | --- | --- |
| `junit-jupiter-engine` | `junit-jupiter` | JUnit Jupiter |
| `junit-vintage-engine` | `junit-vintage` | JUnit 3/4 qua Vintage |
| `junit-platform-suite-engine` | `junit-platform-suite` | Declarative suites |

**Lưu ý quan trọng:** `junit-platform-engine` là artifact **chứa API của TestEngine**, không đồng nghĩa với việc đã có một engine cụ thể chạy Jupiter tests. Cần một implementation, chẳng hạn `junit-jupiter-engine`.

Với các JAR JUnit phát hành chính thức, cơ chế service registration phục vụ discovery được đóng gói cùng artifact. Trong dự án Maven thông thường, bạn chỉ cần khai báo dependencies đúng; không phải tự viết lớp `TestEngine` hoặc cấu hình `META-INF/services` bằng tay.

## 4. Các artifact cần thiết: tránh vừa thiếu vừa khai báo thừa

Dùng họ version **JUnit Jupiter 5.11.4 và JUnit Platform 1.11.4** làm ví dụ cố định để học; đây không phải tuyên bố phiên bản mới nhất.

| Artifact Maven | Tác dụng | Cần khai báo tường minh? |
| --- | --- | --- |
| `org.junit.jupiter:junit-jupiter-api` | `@Test`, assertions, Jupiter lifecycle API | Khi khai báo tách thành phần |
| `org.junit.jupiter:junit-jupiter-params` | `@ParameterizedTest`, `@CsvSource`, `@ValueSource` | Khi dùng parameterized tests và không dùng aggregator |
| `org.junit.jupiter:junit-jupiter-engine` | Engine thực thi Jupiter test | Phải có trên test runtime, trực tiếp hoặc transitively |
| `org.junit.jupiter:junit-jupiter` | Aggregator API + Params + Engine | **Cách đơn giản nhất** cho đa số dự án mới |
| `org.junit.platform:junit-platform-engine` | API dành cho engine | Thường tự kéo qua transitive dependencies |
| `org.junit.platform:junit-platform-launcher` | Launcher API cho IDE/build tool hoặc tool tự viết | Tùy nhu cầu tích hợp; **không thay thế engine** |
| `org.junit.platform:junit-platform-commons` | Common helpers | Thường transitive |
| `org.junit.vintage:junit-vintage-engine` | Engine cho JUnit cũ | Chỉ khi migration |
| `org.junit:junit-bom` | BOM quản lý phiên bản module JUnit | Khuyến nghị khi dùng nhiều module JUnit |
| `org.opentest4j:opentest4j` | API báo lỗi assertion/test | Thường transitive |
| `org.apiguardian:apiguardian-api` | Thông tin mức độ ổn định API | Thường transitive |

Maven dùng metadata của artifact để giải quyết graph. Không nên thêm mọi JAR trong bảng vào POM chỉ vì chúng xuất hiện trong tài liệu.

### 4.1. Cách A: khai báo một aggregator

```xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.11.4</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Artifact `junit-jupiter` 5.11.4 có các dependencies tới `junit-jupiter-api`, `junit-jupiter-params` và `junit-jupiter-engine`. Nhờ vậy chỉ một khai báo dễ hiểu là đủ để viết `@Test` và `@ParameterizedTest` rồi chạy qua một Surefire tương thích.

### 4.2. Cách B: tách API, Params và Engine

```xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter-api</artifactId>
        <version>5.11.4</version>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter-params</artifactId>
        <version>5.11.4</version>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter-engine</artifactId>
        <version>5.11.4</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Đây là **một lựa chọn thay cho aggregator**, không cần khai báo cả hai cấu hình cùng lúc. Cách này làm rõ trách nhiệm mỗi module nhưng phải quản lý version đồng nhất.

### 4.3. Vì sao API-only không phải một cấu hình đủ tin cậy?

POM chỉ có:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter-api</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>
```

có thể cho mã `import org.junit.jupiter.api.Test` **biên dịch**. Nhưng POM không chủ động bảo đảm runtime có một TestEngine implementation. Một số versions/configurations của Surefire có cơ chế tự giải quyết engine thích hợp; **không nên dựa vào điều đó để phát biểu rằng API và Engine là một**. Sử dụng aggregator hoặc khai báo engine rõ ràng làm hành vi minh bạch và dễ debug.

## 5. Provider của Surefire khác TestEngine ra sao?

Maven Surefire Plugin thuộc khu vực `<build><plugins>` của POM. Nó chịu trách nhiệm điều phối kiểm thử trong Maven default lifecycle, thường ở phase `test`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.2</version>
</plugin>
```

Khi Surefire chạy JUnit Platform, **Surefire provider** tích hợp Maven plugin với JUnit Platform Launcher, và Platform chuyển discovery/execution cho TestEngine phù hợp.

- `surefire-junit-platform`: một provider thuộc hệ thống Surefire.
- `junit-jupiter-engine`: implementation của JUnit Platform `TestEngine`.
- `junit-platform-launcher`: API cho khởi động test plan và nhận kết quả.

**Ba thứ không thay thế lẫn nhau.**

Với Surefire 3.5.2, JUnit Platform đã được hỗ trợ. Khi dự án khai báo một engine phù hợp, Surefire có thể dùng provider thích hợp mà bạn không cần đặt trực tiếp `surefire-junit-platform` vào project `<dependencies>`.

Lưu ý các phiên bản Surefire **3.6.0 trở lên** có cơ chế thống nhất JUnit Platform cho nhiều framework theo tài liệu mới. Bài học này sử dụng Surefire **3.5.2** được ghim cụ thể, nên không gán mọi hành vi mặc định của bản 3.6.x cho bản 3.5.x.

### 5.1. Test execution thực tế gồm những bước nào?

```text
mvn test
   |
   v
compiler:testCompile
   |
   v
target/test-classes
   |
   v
surefire:test
   |
   +--> scan class names (patterns / include / exclude)
   +--> chọn provider và test runtime classpath
   +--> JUnit Platform Launcher
   +--> discover qua Jupiter Engine
   +--> execute và thu thập sự kiện
   |
   v
target/surefire-reports/*.txt, *.xml
```

Một lỗi ở bước scan có thể làm số test bằng 0 **dù TestEngine đã có**. Ngược lại, tên class hợp lệ không đảm bảo engine được cung cấp. Cần tìm lỗi ở đúng tầng.

## 6. Scope test và classpath đúng

JUnit dependencies phục vụ mã trong `src/test/java`, vì thế scope thường dùng là `test`:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>
```

Bảng phạm vi rút gọn:

| Phạm vi | Main compile classpath | Main runtime classpath | Test compile/runtime |
| --- | --- | --- | --- |
| `compile` (mặc định) | Có | Có | Có |
| `runtime` | Không trực tiếp | Có | Có |
| `provided` | Có | Không được Maven tự đưa vào runtime thông thường | Có |
| `test` | Không | Không | **Có** |

Đặt JUnit ở `compile` chỉ để “test chạy được” thường làm thư viện kiểm thử xuất hiện không cần thiết trong dependency graph của consumer. Đúng giải pháp là đặt test code ở `src/test/java` và JUnit dependencies ở scope `test`.

Lớp ứng dụng thông thường không nên import `org.junit.jupiter.api.*`. Nếu main code cần một API phục vụ logic nghiệp vụ, đó là thiết kế khác với framework để kiểm thử.

## 7. JUnit BOM giúp tránh version mismatch

JUnit Jupiter và JUnit Platform **không có chuỗi version giống nhau**:

```text
JUnit Jupiter:  5.11.4
JUnit Platform: 1.11.4
JUnit Vintage:  5.11.4
JUnit BOM:      5.11.4
```

Đây là version family tương thích của JUnit 5.11.4, không phải lỗi version lệch. Bạn không nên đặt version `5.11.4` cho `junit-platform-launcher` (nhóm Platform phát hành ở version `1.11.4` tương ứng).

Cách quản lý trong POM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit</groupId>
            <artifactId>junit-bom</artifactId>
            <version>5.11.4</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Trong `<dependencies>`, sau đó có thể bỏ version của các JUnit artifacts BOM quản lý:

```xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.junit.platform</groupId>
        <artifactId>junit-platform-launcher</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

BOM là dependency management, **không tự thêm** JUnit Jupiter, Jupiter Engine hoặc Launcher vào classpath. Trong một dự án có parent/framework quản lý JUnit sẵn (ví dụ một số cấu hình Spring Boot), cần đối chiếu effective POM trước khi import thêm BOM trùng.

## 8. Dự án thực hành Java 17: 5 lượt test được Jupiter Engine thực thi

Ta sẽ tạo một dự án nhỏ tính tổng tiền. Mã Java sản phẩm độc lập JUnit; bộ test có hai phương thức `@Test` và một `@ParameterizedTest` với ba bộ dữ liệu. Khi JUnit Platform/Engine và Surefire cấu hình chính xác, nó tạo **5 lượt kiểm thử**.

### 8.1. Cấu trúc

```text
junit-platform-demo/
├── pom.xml
└── src/
    ├── main/java/dev/lesson/
    │   ├── Invoice.java
    │   └── App.java
    └── test/java/dev/lesson/
        └── InvoiceTest.java
```

Điều kiện: JDK 17+, Maven tương thích như Maven 3.9.x, repository có thể tải các artifact nếu local cache chưa có. Các version ghim trong POM phục vụ ví dụ ổn định, không phải tuyên bố phiên bản mới nhất hiện tại.

### 8.2. POM đầy đủ

Tạo `junit-platform-demo/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>junit-platform-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit</groupId>
                <artifactId>junit-bom</artifactId>
                <version>5.11.4</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <!-- API + Params + Engine -->
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>

        <!-- Tường minh hóa Launcher; BOM quản lý version Platform -->
        <dependency>
            <groupId>org.junit.platform</groupId>
            <artifactId>junit-platform-launcher</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Điểm cần chú ý:

1. JUnit BOM quản lý versions của các artifact JUnit, **không tự thêm dependency**.
2. `junit-jupiter` aggregator giúp test code nhìn thấy API/Params và test runner tìm thấy Jupiter Engine.
3. `junit-platform-launcher` ở scope test minh họa dependency phục vụ tooling. Các versions Surefire hỗ trợ hiện đại có thể tự cấp Launcher; dependency trực tiếp này **không bắt buộc cho mọi POM**.
4. Surefire ở `build/plugins`, không nằm trong `dependencies` của project.
5. `failIfNoTests=true` là một guardrail: khi không có test nào được Surefire tìm thấy, build phải báo lỗi thay vì âm thầm coi đó là thành công. Nó không tự tăng test coverage.

### 8.3. Mã chính

Tạo `src/main/java/dev/lesson/Invoice.java`:

```java
package dev.lesson;

public final class Invoice {
    private Invoice() {
    }

    public static int totalCents(int unitCents, int quantity) {
        if (unitCents < 0 || quantity < 0) {
            throw new IllegalArgumentException(
                    "Giá và số lượng phải không âm");
        }
        return Math.multiplyExact(unitCents, quantity);
    }

    public static String formatTotal(int cents) {
        return "Thành tiền: " + cents + " xu";
    }
}
```

Tạo `src/main/java/dev/lesson/App.java`:

```java
package dev.lesson;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        int total = Invoice.totalCents(250, 3);
        System.out.println(Invoice.formatTotal(total));
    }
}
```

Hàm `Math.multiplyExact` là Java API tiêu chuẩn; nó không trả kết quả tràn số nguyên im lặng. Chương trình sản phẩm không import bất kỳ lớp nào thuộc JUnit.

### 8.4. Test code dùng Jupiter API và Params

Tạo `src/test/java/dev/lesson/InvoiceTest.java`:

```java
package dev.lesson;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class InvoiceTest {
    @Test
    void calculatesInvoice() {
        assertEquals(750, Invoice.totalCents(250, 3));
    }

    @Test
    void rejectsNegativeQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> Invoice.totalCents(250, -1));
    }

    @ParameterizedTest(name = "{index}: {0} x {1} = {2}")
    @CsvSource({
            "100, 0, 0",
            "125, 2, 250",
            "199, 3, 597"
    })
    void totalFromTable(int unitCents, int quantity, int expected) {
        assertEquals(expected, Invoice.totalCents(unitCents, quantity));
    }
}
```

Có **3 phương thức kiểm thử** nhưng **5 lượt thực thi**:

- `calculatesInvoice`: một lượt.
- `rejectsNegativeQuantity`: một lượt.
- `totalFromTable`: ba lượt từ ba dòng `@CsvSource`.

Không cần khai báo class/method là `public` khi dùng Jupiter đúng cách. Test runner phát hiện class top-level `InvoiceTest` theo quy ước tên Surefire, còn Jupiter Engine nhận diện annotations và tạo các invocations tương ứng.

### 8.5. Lệnh chạy và kết quả

Trong thư mục chứa `pom.xml`:

```bash
mvn -version
mvn clean verify
java -cp target/classes dev.lesson.App
```

Nếu Maven và JDK tương thích, dependencies/plugins tải được và nguồn được lưu đúng UTF-8, Surefire chạy 5 lượt tests. Những **số liệu cần đối chiếu** thường hiển thị ở dạng:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là đoạn đại diện cho kết quả mong đợi, **không phải bản chép nguyên văn toàn bộ log**; Maven có thể thêm prefix/timing và các thông tin plugin khác.

Ứng dụng in chính xác một dòng stdout:

```text
Thành tiền: 750 xu
```

Các file đầu ra điển hình:

```text
target/classes/dev/lesson/Invoice.class
target/classes/dev/lesson/App.class
target/test-classes/dev/lesson/InvoiceTest.class
target/surefire-reports/
target/junit-platform-demo-1.0.0-SNAPSHOT.jar
```

JAR chuẩn không tự kèm test classes hoặc JUnit dependencies. POM ví dụ không khai báo `Main-Class` trong manifest, vì thế không dùng `java -jar target/junit-platform-demo-1.0.0-SNAPSHOT.jar` rồi kỳ vọng đó là executable JAR; lệnh chạy đúng đã nêu là `java -cp target/classes dev.lesson.App`.

### 8.6. Biên dịch trực tiếp mã chính, không chạy test

Vì mã chính chỉ dùng Java Standard Library, có thể minh họa bằng lệnh thủ công trên Bash:

```bash
mkdir -p target/manual-main
javac -encoding UTF-8 --release 17 -d target/manual-main \
  src/main/java/dev/lesson/Invoice.java \
  src/main/java/dev/lesson/App.java
java -cp target/manual-main dev.lesson.App
```

PowerShell:

```powershell
New-Item -ItemType Directory -Force target/manual-main | Out-Null
javac -encoding UTF-8 --release 17 -d target/manual-main src/main/java/dev/lesson/Invoice.java src/main/java/dev/lesson/App.java
java -cp target/manual-main dev.lesson.App
```

Dòng stdout vẫn là `Thành tiền: 750 xu`. Lệnh trên **không compile hoặc chạy InvoiceTest**; để chạy unit tests cần test classpath, provider/Launcher và engine phù hợp. Đừng lấy thành công của lệnh `javac` này thay cho kết quả `mvn test`.

## 9. Xem engine và API thực tế trong dependency tree

Chạy:

```bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.junit.jupiter
mvn dependency:tree -Dincludes=org.junit.platform
```

Trong dependency graph của demo, bạn sẽ tìm thấy những artifact như:

```text
org.junit.jupiter:junit-jupiter:jar:5.11.4:test
org.junit.jupiter:junit-jupiter-api:jar:5.11.4:test
org.junit.jupiter:junit-jupiter-params:jar:5.11.4:test
org.junit.jupiter:junit-jupiter-engine:jar:5.11.4:test
org.junit.platform:junit-platform-launcher:jar:1.11.4:test
```

Đây là **danh sách rút gọn các thành phần cần quan sát**, không phải output đầy đủ; thực tế sẽ có các dependencies bắc cầu khác như JUnit Platform Commons, Engine API, OpenTest4J, API Guardian.

Một lệnh lọc engine:

```bash
mvn dependency:tree -Dincludes=org.junit.jupiter:junit-jupiter-engine
```

Nếu engine không nằm trong test runtime graph do dependency bị loại hoặc version thay đổi, hãy xem POM và dependencyManagement. Nếu engine có mặt nhưng số test vẫn bằng 0, kiểm tra Surefire class patterns, imports, filters và skip flags; **không tự kết luận là thiếu engine**.

### 9.1. Launcher không phải TestEngine

`junit-platform-launcher` cung cấp API để công cụ điều phối discovery và execution. Nó có thể được Surefire/IDE sử dụng, nhưng **không tự quyết định cách chạy Jupiter @Test**. Vai trò đó là của `junit-jupiter-engine`.

Ngược lại, `junit-platform-engine` chứa API dành cho engine writers, cũng không phải một engine implementation đủ để chạy Jupiter tests. Kiểm tra artifact ID khi debug vì ba tên này rất dễ nhầm.

## 10. Maven nhận diện tên lớp test thế nào?

Maven Surefire Plugin mặc định quét các test classes phù hợp mẫu tên như:

```text
**/Test*.java
**/*Test.java
**/*Tests.java
**/*TestCase.java
```

Ví dụ:

| Tên lớp/tệp | Mặc định thường được Surefire xét? |
| --- | --- |
| `InvoiceTest.java` | Có |
| `TestInvoice.java` | Có |
| `InvoiceTests.java` | Có |
| `InvoiceTestCase.java` | Có |
| `InvoiceSpec.java` | Không, nếu không cấu hình includes |
| `InvoiceIT.java` | Thường dành cho Failsafe, không theo pattern unit-test mặc định |

**Quét class ở Surefire khác với discovery method trong Jupiter Engine.** Surefire có thể chọn `InvoiceTest` theo tên, sau đó Jupiter engine tìm các test descriptors bên trong class đó.

Một lớp được biên dịch nhưng không khớp include patterns có thể khiến `Tests run: 0` mà không có lỗi thiếu API. Nếu muốn dùng hậu tố `Spec`, cần đổi tên hoặc cấu hình Surefire includes:

```xml
<configuration>
    <includes>
        <include>**/*Test.java</include>
        <include>**/*Spec.java</include>
    </includes>
    <failIfNoTests>true</failIfNoTests>
</configuration>
```

Đây là **đoạn thay thế configuration của Surefire Plugin**, không phải POM hoàn chỉnh. Nếu dự án có thêm những quy ước tên khác, hãy giữ các patterns cần thiết khi tùy biến thay vì vô tình loại chúng.

Nested tests của Jupiter nằm trong class top-level đã được tìm thấy có thể vẫn được engine xử lý. Việc Surefire không quét trực tiếp mọi nested class không có nghĩa JUnit Jupiter `@Nested` không dùng được.

## 11. Cấu hình test runner: failIfNoTests và chọn test

Trong POM demo:

```xml
<configuration>
    <failIfNoTests>true</failIfNoTests>
</configuration>
```

Tham số này ngăn trường hợp **không có test nào được Surefire tìm thấy** mà vẫn báo build xanh. Nó không đảm bảo kiểm thử đầy đủ hoặc không có test nào bị filter khi vẫn còn test khác.

Chạy riêng lớp:

```bash
mvn -Dtest=InvoiceTest test
```

Chạy một phương thức:

```bash
mvn -Dtest=InvoiceTest#calculatesInvoice test
```

Khi chọn đúng phương thức `calculatesInvoice`, kỳ vọng là **1** lượt test, không phải 5.

Với Windows PowerShell, có thể quote đối số để tránh tác động của ký tự đặc biệt:

```powershell
mvn '-Dtest=InvoiceTest#calculatesInvoice' test
```

Nếu dùng `-Dtest=NonExistentTest`, Surefire có thể thất bại bởi chế độ kiểm tra test được chỉ định riêng (tham số `failIfNoSpecifiedTests`). Đó là cơ chế khác với `failIfNoTests` cho trường hợp không có test tổng quát.

## 12. Lọc theo @Tag và engine

JUnit Jupiter hỗ trợ gắn nhãn qua `@Tag`:

```java
package dev.lesson;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class SmokeInvoiceTest {
    @Test
    @Tag("smoke")
    void quickCheck() {
        assertEquals(250, Invoice.totalCents(125, 2));
    }
}
```

**Đây là một lớp test bổ sung**, không phải phần của ví dụ 5 lượt test. Nếu thêm vào `src/test/java/dev/lesson/` với cấu hình demo ban đầu, full test suite sẽ có thêm một test (tổng 6).

Với Surefire hỗ trợ JUnit Platform, tag filter thường được cấu hình bằng:

```xml
<configuration>
    <groups>smoke</groups>
</configuration>
```

Hoặc trong cấu hình phù hợp dùng property:

```bash
mvn -Dgroups=smoke test
```

Chỉ những test phù hợp filter mới được xét chạy. Đừng đổi filters rồi cho rằng số test của full suite vẫn phải là 5; phải xác định rõ bài nào đang được chọn.

JUnit Platform còn cho phép engine filters (chọn `junit-jupiter`, `junit-vintage`...). Trước khi dùng, hãy xác nhận engine ID và plugin version hỗ trợ đúng cấu hình. Một engine filter sai có thể làm test của mô hình khác biến mất khỏi báo cáo.

## 13. JUnit 4 và Vintage: migration có chủ đích

JUnit 4 dùng API khác Jupiter, ví dụ:

```java
import org.junit.Test;
import static org.junit.Assert.assertEquals;
```

Khi muốn chạy những test cũ qua JUnit Platform, thường cần JUnit 4 API và Vintage Engine ở scope `test`.

**Đoạn XML bổ sung** cho POM đã import JUnit BOM:

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
    <scope>test</scope>
</dependency>
```

JUnit BOM quản lý `junit-vintage-engine`, nhưng version của artifact JUnit 4 `junit:junit:4.13.2` được khai báo rõ.

Một class JUnit 4 dành cho nhánh migration:

```java
package dev.lesson;

import org.junit.Test;
import static org.junit.Assert.assertEquals;

public class LegacyInvoiceTest {
    @Test
    public void oldTotal() {
        assertEquals(500, Invoice.totalCents(250, 2));
    }
}
```

Đây **không phải phần của dự án demo 5 tests**. Nếu thêm class này và cấu hình Vintage hoạt động cùng Jupiter, số test của full suite tăng lên, và phải kiểm tra cả provider/filters/report.

Không thêm Vintage trong dự án chỉ có Jupiter tests. Với migration, trước/sau khi bỏ Vintage phải so sánh test count, bởi những test JUnit 4 chưa được viết lại có thể không còn chạy.

## 14. Surefire và Failsafe cùng dùng engine nhưng phục vụ giai đoạn khác nhau

Maven Surefire Plugin thường chạy **unit tests** ở phase `test`. Maven Failsafe Plugin được cấu hình để chạy **integration tests** ở phase `integration-test` và đánh giá kết quả ở `verify`.

| Nội dung | Surefire | Failsafe |
| --- | --- | --- |
| Mục đích thông dụng | Unit tests | Integration tests |
| Phase | `test` | `integration-test` + `verify` |
| Mẫu tên | `*Test`, `Test*`, `*Tests`, `*TestCase` | `*IT`, `IT*`, `*ITCase` |
| Report | `target/surefire-reports` | `target/failsafe-reports` |
| TestEngine | Có thể dùng Jupiter Engine | Cũng có thể dùng Jupiter Engine |

Ví dụ cấu hình Failsafe **chỉ dành cho dự án thật sự có integration tests**:

```xml
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
```

POM demo mục 8 **không cấu hình Failsafe**. Vì vậy không nói rằng `mvn clean verify` của demo tự chạy integration tests; nó dùng Surefire để chạy các unit tests đang có.

Goal `verify` của Failsafe có vai trò kiểm tra kết quả sau giai đoạn integration-test và các hoạt động liên quan, tránh dừng quá sớm trước khi thực hiện những bước teardown đã cấu hình.

## 15. Cấu hình JUnit Platform qua file resource

Trong dự án có nhu cầu, tạo:

```text
src/test/resources/junit-platform.properties
```

Ví dụ tùy chọn:

```properties
junit.jupiter.testinstance.lifecycle.default = per_method
junit.jupiter.execution.parallel.enabled = false
```

Đây là **file tùy chọn**; không cần để chạy POM demo. Maven đưa `src/test/resources` vào test runtime classpath, và JUnit Platform/Jupiter đọc các configuration parameters phù hợp.

**File này không thay thế engine dependency.** Nó không tự thêm `junit-jupiter-engine`, không sửa Maven Surefire plugin version và không bảo đảm các test classes phù hợp patterns đã được chọn.

Các dự án có thể cấu hình parameters qua Surefire `configurationParameters` hoặc system properties, nhưng nên quản lý một nguồn cấu hình rõ ràng. Nếu nhiều nơi đặt giá trị mâu thuẫn, hãy xem nguyên tắc ưu tiên theo JUnit Platform và đối chiếu hiệu lực thực tế.

## 16. Phân biệt 0 test, test bị skip và test bị filter

Khi CI có ít test hơn mong đợi, hãy phân loại:

- **Không được phát hiện**: Surefire không chọn class, không có annotations phù hợp hoặc engine không phát hiện test case.
- **Filter loại bỏ**: chỉ chạy một tag, method, class hoặc engine; những test khác không được chọn cho lượt này.
- **Disabled**: Jupiter `@Disabled` báo skip theo cơ chế Jupiter, thường góp vào skipped statistics.
- **Skip Maven**: `-DskipTests` thường bỏ thực thi test; `-Dmaven.test.skip=true` có thể bỏ biên dịch và chạy test với các plugin hỗ trợ.
- **Test thất bại**: assertion sai dẫn tới failure; exception không dự đoán hoặc lỗi khởi tạo có thể là error.
- **Test không có trong module đang build**: chạy sai thư mục hoặc chỉ chọn `-pl` một module khác.

Hai lệnh minh họa:

```bash
mvn -DskipTests clean package
mvn -Dmaven.test.skip=true clean package
```

Chúng không phải quy trình QA bình thường. Một build có `BUILD SUCCESS` khi test bị bỏ qua **không chứng minh kiểm thử đã pass**.

Tương tự, khi có test khác vẫn chạy, `failIfNoTests=true` không bắt buộc phát hiện mọi test vô tình bị loại; cần so sánh test count và reports với kỳ vọng của dự án.

## 17. Vì sao cùng một POM nhưng IDE chạy được, Maven không chạy?

IDE và Maven có thể dùng:

- JDK và test runner khác.
- Classpath do IDE tạo gồm engine/launcher mà Maven chưa có.
- Phương thức phát hiện test không giống Surefire naming patterns.
- Profile Maven, dependencyManagement hoặc module context khác.
- Version JUnit Platform/Jupiter đã được IDE bundle hoặc tải riêng.
- Flags filter, parallel execution hoặc skip khác.

Lệnh điều tra:

```bash
mvn -version
mvn help:effective-pom
mvn dependency:tree
mvn clean test
```

Nếu Maven build thất bại do lỗi tải artifact, trước hết cần xử lý repository/mirror/settings; đừng coi đó là lỗi `@Test`. Nếu API có nhưng engine thiếu hoặc không tương thích, xem dependency graph. Nếu test source compile xong nhưng không được chạy, xem Surefire scan patterns và reports.

**Ưu tiên kết quả Maven CLI của đúng module khi đánh giá CI**, không chỉ nút Run Test trong IDE.

## 18. Những lỗi và hướng xử lý phổ biến

| Triệu chứng | Khả năng chính | Cách xử lý |
| --- | --- | --- |
| `package org.junit.jupiter.api does not exist` | Chưa có Jupiter API trên test compile classpath | Thêm aggregator/API đúng scope test, kiểm tra GAV |
| `package org.junit.jupiter.params does not exist` | Thiếu Params hoặc aggregator | Thêm `junit-jupiter-params` hoặc `junit-jupiter` |
| `No TestEngine available` hoặc lỗi launcher | Engine runtime thiếu hoặc version xung đột | Xem `dependency:tree`, thêm engine, align BOM |
| `Tests run: 0` | Surefire patterns, filters, skip, module hoặc engine | Kiểm tra `InvoiceTest`, reports, plugin config |
| Test JUnit 4 không chạy | Dùng annotation cũ nhưng thiếu Vintage/provider phù hợp | Thêm JUnit 4 + Vintage cho migration |
| Test Java class chạy được bằng IDE nhưng Maven không | Chênh dependency/runner hoặc naming | Kiểm tra Maven CLI và effective POM |
| `NoSuchMethodError` trong JUnit Platform | Module JUnit bị lệch versions | Import BOM, bỏ overrides, kiểm tra graph |
| Maven báo missing version | BOM không được import đúng hoặc không quản lý artifact | Kiểm tra `dependencyManagement`, groupId/artifactId |
| Mất parameterized tests | Thiếu `junit-jupiter-params` hoặc filter | Kiểm tra imports, graph và report |
| Không thấy Surefire reports | Chưa chạy phase test, skip hoặc plugin fail sớm | Chạy `mvn clean test`, đọc log |
| 0 tests nhưng `BUILD SUCCESS` | Không bật guardrail, hoặc test phase không chạy | Xem `failIfNoTests` và số test thực tế |
| Failsafe không chạy IT | Chưa cấu hình executions | Bind goals `integration-test` và `verify` |
| JUnit có mặt trong production dependencies | Dùng scope `compile` không cần thiết | Chuyển JUnit test dependencies về scope `test` |
| ConsoleLauncher dùng version không khớp | Chạy JAR/launcher riêng không đồng nhất | Chọn phiên bản Platform tương thích và classpath chính xác |
| Test bị chạy hai lần | Trùng runner/provider/config hoặc gọi nhiều goals | Kiểm tra execution plan và reports |

Không sửa bằng cách sao chép thêm nhiều JUnit JAR không rõ version vào `lib/` hoặc toàn bộ Maven local repository. Điều đó có thể che xung đột và làm CI không tái lập.

## 19. Bài tập kiểm chứng

1. Viết lại bằng lời vai trò của JUnit Platform, Jupiter API, Jupiter Engine, Launcher và Maven Surefire provider. Thành phần nào **không phải** một TestEngine?
2. Tạo POM và ba file Java ở mục 8; chạy `mvn clean verify` và xác nhận **5 lượt kiểm thử**, không có failure/error/skip.
3. Chạy `java -cp target/classes dev.lesson.App` và đối chiếu stdout với `Thành tiền: 750 xu`. Vì sao không cần JUnit ở runtime?
4. Thay aggregator `junit-jupiter` bằng API, Params và Engine riêng. Số test thực thi có nên đổi không?
5. Bỏ `junit-jupiter-params` trong cấu hình tách riêng nhưng vẫn dùng `@CsvSource`; dự đoán lỗi compile.
6. Giữ API nhưng không khai báo engine tường minh, thử với Surefire 3.5.2 và xem graph. Vì sao không nên suy luận mọi runner tự tải engine?
7. Đổi tên test class thành `InvoiceSpec`, giữ source nhưng không sửa Surefire includes. Vì sao nó có thể compile mà không được chạy?
8. Dùng `-Dtest=InvoiceTest#calculatesInvoice` chạy riêng một method; so sánh với full suite năm lượt.
9. Import BOM và xem version Launcher. Vì sao Platform 1.11.4 tương thích với Jupiter 5.11.4?
10. Thêm test JUnit 4 vào nhánh thử nghiệm, rồi cấu hình Vintage; so sánh số test được Surefire chạy.
11. Thêm `SmokeInvoiceTest` từ mục 12, dùng filter `smoke` và giải thích sự thay đổi số lượng test.
12. So sánh `@Disabled`, `skipTests` và tag filter; tình huống nào cho thấy test bị skipped so với không được chọn?
13. Nêu khác biệt giữa Surefire và Failsafe về phase, tên test và báo cáo.
14. Một CI report nói `BUILD SUCCESS` nhưng số tests giảm một nửa sau khi nâng JUnit. Liệt kê các bằng chứng cần kiểm tra trước khi chấp nhận build.
15. Vì sao `junit-platform-engine` không thể thay `junit-jupiter-engine` để chạy Jupiter annotations?

## 20. Checklist cấu hình đáng tin

- [ ] Tên test class đúng conventions Surefire và nằm trong `src/test/java`.
- [ ] Jupiter API và Params (nếu dùng) có mặt ở test compile classpath.
- [ ] Jupiter Engine có mặt ở test runtime, trực tiếp hoặc qua aggregator.
- [ ] Surefire Plugin có version hỗ trợ Platform và được ghim trong POM.
- [ ] Nếu khai báo Launcher, version của nó cùng family Platform được BOM quản lý.
- [ ] Không trộn JUnit Jupiter API/Engine/Platform ở version không tương thích.
- [ ] Không dùng Vintage nếu không cần chạy test cũ; nếu có JUnit 4 thì kiểm chứng migration.
- [ ] Không có skip hoặc class/tag/engine filters ngoài ý muốn.
- [ ] Dự án thực sự chạy full tests trên Maven CLI của đúng module.
- [ ] Số tests, failures, errors, skipped được kiểm tra từ báo cáo.
- [ ] Nếu module phải có test, bật guardrail như `failIfNoTests`.
- [ ] JUnit dependencies chỉ nằm ở scope `test` khi phục vụ kiểm thử.
- [ ] Khi nâng JUnit/Surefire, review changelog và chạy lại full suite trong CI.

## 21. Kết luận

Để JUnit tests chạy được trong Maven, **không chỉ cần `@Test`**. Bạn cần API thích hợp để viết và compile, một **TestEngine** phù hợp trên test runtime classpath, và một công cụ thực thi như Maven Surefire sử dụng JUnit Platform thông qua provider/launcher.

Với JUnit 5.11.4, cách dễ bảo trì là dùng `org.junit:junit-bom` để quản lý version, `org.junit.jupiter:junit-jupiter` scope test để có API/Params/Engine, và một Maven Surefire Plugin tương thích được ghim version. Có thể thêm `junit-platform-launcher` scope test khi cần đồng bộ tooling; **Launcher không phải Engine**.

Cấu hình đúng phải được kiểm chứng bằng **kết quả chạy thực tế**, không chỉ đọc POM: dự án mẫu có 3 phương thức test nhưng 5 lượt thực thi, `mvn clean verify` đạt thành công và báo cáo cho biết số tests. Khi có lỗi, xác định đúng tầng API, engine, provider, discovery hoặc filter thay vì thay đổi dependencies tùy tiện.

## 22. Nguồn tài liệu

- [JUnit 5.11.4 User Guide — Maven support](https://docs.junit.org/5.11.4/user-guide/#running-tests-build-maven)
- [JUnit 5.11.4 User Guide — Test engines](https://docs.junit.org/5.11.4/user-guide/#advanced-topics-test-engines)
- [JUnit 5.11.4 API overview](https://docs.junit.org/5.11.4/api/)
- [Maven Surefire Plugin — Using JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Maven Surefire Plugin — Include/Exclude Tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html)
- [Maven Surefire Plugin — Running Single Test](https://maven.apache.org/surefire/maven-surefire-plugin/examples/single-test.html)
- [Maven Failsafe Plugin — Usage](https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html)
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
