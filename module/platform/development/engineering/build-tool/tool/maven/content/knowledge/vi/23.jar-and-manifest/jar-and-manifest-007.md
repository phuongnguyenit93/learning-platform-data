# Đính kèm test JAR hoặc artifact khác bằng classifier trong Maven

Trong Maven, một project thường tạo **artifact chính** theo tọa độ `groupId:artifactId:version` và packaging đã chọn. Ví dụ project `dev.training.artifacts:fixture-kit:1.0.0` với `<packaging>jar</packaging>` thường tạo:

```text
fixture-kit-1.0.0.jar
```

Nhưng cùng một project đôi khi cần phát hành **nhiều artifact khác nhau với cùng groupId, artifactId và version**: một JAR chứa class ứng dụng, một JAR chỉ chứa test helpers, một JAR dành cho khách hàng, một file schema JSON hoặc archive chứa tài liệu. Maven dùng **classifier** để phân biệt những biến thể này.

Ví dụ khi project đính kèm (*attach*) test JAR:

```text
fixture-kit-1.0.0.jar
fixture-kit-1.0.0-tests.jar
```

Hai file có cùng `groupId`, `artifactId`, `version` và phần mở rộng `jar`, nhưng file thứ hai mang **classifier `tests`**. Để Maven tạo nó, dùng goal `jar:test-jar` của **Maven JAR Plugin**. Trong project khác, muốn dùng các test helper classes từ artifact này, khai báo dependency chọn đúng **classifier/type** và thường là **scope `test`**.

**Ba ý quan trọng nhất:**
- **Classifier** là thuộc tính **định danh artifact**. Nó không phải Maven dependency scope, không phải packaging, không phải version và không nhất thiết được ghi trong JAR manifest.
- **Attached artifact** là một artifact phụ được plugin đăng ký với Maven project trong build. Khi chạy các phase `install` hoặc `deploy` thông thường, Maven có thể cài/phát hành cả artifact chính và các attached artifacts đủ điều kiện.
- **Test JAR không tự mang theo toàn bộ test dependencies dạng bắc cầu.** Khi dùng test JAR của project khác, bạn thường phải khai báo JUnit, AssertJ hoặc các thư viện test-scoped cần thiết ở phía consumer; với bộ test utilities dùng rộng rãi, tạo một Maven module riêng có thể dễ bảo trì hơn.

Bài này đi từ mô hình artifact → `maven-jar-plugin:test-jar` → ví dụ **Maven reactor hai module Java 17 chạy được** → dependency selection → các kiểu attached artifact khác → lỗi thường gặp, kiểm tra JAR, local repository và CI.

## 1. Mô hình tọa độ artifact: classifier đứng ở đâu?

Định danh Maven artifact thường gồm:

```text
groupId : artifactId : version : classifier : extension
```

Đây là **cách trình bày các thành phần khái niệm**, không phải một thứ tự tham số cố định cho mọi cú pháp Maven CLI. Trong POM dependency, bạn khai báo riêng từng trường bằng XML; khi hiển thị trên dependency tree hoặc trong các plugin, Maven có thể biểu diễn GAV/type/classifier bằng thứ tự khác.

Ví dụ cùng một project:

| Thành phần | Artifact chính | Artifact test JAR | Attached JAR tùy chỉnh |
| --- | --- | --- | --- |
| `groupId` | `dev.training.artifacts` | Giống | Giống |
| `artifactId` | `fixture-kit` | Giống | Giống |
| `version` | `1.0.0` | Giống | Giống |
| `classifier` | Không có | `tests` | `client` |
| Extension | `jar` | `jar` | `jar` |
| File điển hình | `fixture-kit-1.0.0.jar` | `fixture-kit-1.0.0-tests.jar` | `fixture-kit-1.0.0-client.jar` |
| Nguồn thường dùng | `target/classes` | `target/test-classes` | Một tập con được lọc từ `target/classes` |

Có thể có nhiều artifact phụ cùng version nếu classifier khác nhau. Nhưng một artifact ID cụ thể không thể chứa hai nội dung khác nhau mà lại dùng **cùng toàn bộ tọa độ artifact** trong repository như thể chúng là hai bản hợp lệ khác nhau.

### 1.1. Classifier khác packaging

`<packaging>jar</packaging>` trong project POM chọn **kiểu build/lifecycle** và artifact chính. Nó không có nghĩa chỉ được tạo đúng một JAR. Một plugin vẫn có thể attach các JAR phụ.

`<classifier>tests</classifier>` trong một **dependency** chọn biến thể của artifact. Nó không tự chuyển một dependency sang scope test hoặc khiến Maven chạy các tests bên trong JAR đó.

### 1.2. Classifier khác dependency scope

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Classifier | **Lấy biến thể artifact nào?** | `tests`, `client`, `sources` |
| Type | **Chọn artifact handler/extension nào?** | `jar`, `test-jar`, `zip` |
| Scope | **Dependency xuất hiện ở classpath và truyền bắc cầu ra sao?** | `compile`, `test`, `runtime` |
| Version | **Lấy phiên bản nào?** | `1.0.0` |
| Packaging | **Project tạo artifact chính và lifecycle kiểu gì?** | `jar`, `pom`, `war` |

Do đó:

```xml
<dependency>
    <groupId>dev.training.artifacts</groupId>
    <artifactId>fixture-kit</artifactId>
    <version>1.0.0</version>
    <classifier>tests</classifier>
    <type>test-jar</type>
    <scope>test</scope>
</dependency>
```

có ý nghĩa:
- Chọn artifact test JAR của `fixture-kit:1.0.0`.
- Chỉ dùng nó trong ngữ cảnh test của **consumer** theo `scope=test`.
- Không tự thay đổi packaging của project `fixture-kit`.
- Không tự chạy test methods từ JAR phụ như một test suite; tùy trường hợp cần `dependenciesToScan`.

## 2. Attached artifact có nghĩa gì trong Maven?

Trong quá trình build một Maven project, các plugin có thể:
1. Tạo một file mới dưới `target`.
2. Đăng ký file đó là **attached artifact** của Maven project với classifier/extension phù hợp.
3. Cho Maven biết artifact phụ nào cần được đưa vào bước install hoặc deploy thông thường.

Sơ đồ:

```text
Project: dev.training.artifacts:fixture-kit:1.0.0
       |
       +-- main classes
       |      |
       |      +-- jar:jar
       |             |
       |             +-- fixture-kit-1.0.0.jar
       |
       +-- test classes + test resources
              |
              +-- jar:test-jar
                     |
                     +-- fixture-kit-1.0.0-tests.jar
                            classifier = tests
                            attached artifact
       |
       +-- install / deploy (khi được gọi và thành công)
              |
              +-- POM + main artifact + attached artifacts
```

**Tạo file chưa đồng nghĩa attach.** Nếu một shell script tạo `target/fixture-kit-1.0.0-custom.jar` nhưng không plugin nào đăng ký nó với Maven project, lệnh `mvn install` hoặc `mvn deploy` thông thường không tự động phát hành file đó chỉ vì tên của nó giống convention.

Tương tự, không nên tự copy một file vào local repository rồi cho rằng Maven đã nắm đúng metadata, integrity checks và deployment workflow. Hãy dùng plugin có chức năng attach.

### 2.1. Main artifact không có classifier

Artifact chính của project JAR thường là:

```text
dev.training.artifacts:fixture-kit:1.0.0:jar
```

Theo cách ghi rút gọn `groupId:artifactId:version:extension` để minh họa. Artifact phụ được nhận diện thêm bởi classifier `tests` hoặc `client`. Trong Maven repository layout, hai file có thể cùng nằm dưới thư mục version:

```text
dev/training/artifacts/fixture-kit/1.0.0/
    fixture-kit-1.0.0.pom
    fixture-kit-1.0.0.jar
    fixture-kit-1.0.0-tests.jar
```

Đường dẫn là minh họa cho repository kiểu Maven 2. Một repository thực tế còn có metadata, checksum/signature và các file khác tùy công cụ.

## 3. Test JAR là gì, chứa gì và không chứa gì?

Maven JAR Plugin cung cấp **goal `jar:test-jar`** để đóng gói những file đã có dưới thư mục test output của project, mặc định:

```text
${project.build.testOutputDirectory} = target/test-classes
```

Nội dung có thể gồm:
- `.class` từ `src/test/java` (JUnit tests, helpers, builders, mock utilities).
- Các test resources từ `src/test/resources` được Maven đưa vào test output.
- Metadata archive do JAR packaging sinh.

Nội dung **không tự bao gồm**:
- Test **source** `.java` nguyên bản (đó là compiled classes, không phải source JAR).
- Tất cả các dependency JAR của JUnit hoặc thư viện test.
- Class production dưới `target/classes` nếu chúng không có trong test output.
- Manifest `Main-Class` cho chương trình thực thi, trừ khi cấu hình riêng.

Bản 3.4.2 của goal `jar:test-jar` có default phase `package` và **classifier mặc định `tests`**. Bạn có thể ghi đè classifier trong cấu hình goal khi có yêu cầu, nhưng cách phổ biến và tương thích convention là giữ `tests`.

### 3.1. Cấu hình nguồn để tạo test JAR

Ví dụ POM của producer có:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
            <executions>
                <execution>
                    <id>attach-tests</id>
                    <goals>
                        <goal>test-jar</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Đây là một **đoạn trong POM**, không phải XML project hoàn chỉnh. Vì goal đã có default phase `package`, execution không cần ghi `<phase>package</phase>` trong cấu hình đơn giản này.

Kết quả khi `package` thành công:

```text
target/fixture-kit-1.0.0.jar
target/fixture-kit-1.0.0-tests.jar
```

**Không nhầm với việc đổi `<packaging>test-jar</packaging>`:** cách thông thường là giữ packaging chính là `jar` và attach test JAR bằng goal `test-jar`.

### 3.2. Vì sao phải đến phase package?

Lifecycle của Maven `jar` thường:
- `compile` biên dịch main source.
- `test-compile` biên dịch test source.
- `test` chạy unit tests qua Surefire theo default binding.
- `package` tạo main JAR; execution `jar:test-jar` cũng được gọi để attach test JAR.

Do đó `mvn test` có thể tạo `target/test-classes` **nhưng chưa tạo attached test JAR**. Lệnh `mvn package` hoặc `mvn verify` bao gồm phase package, phù hợp hơn khi cần artifact có classifier.

### 3.3. Không cần có @Test trong mọi class của test JAR

Test JAR hữu ích để chia sẻ **test helpers**: sample data, builders, static assertions, fake objects, fixtures. Một class `SampleNames` có thể không có `@Test` nhưng vẫn được biên dịch từ `src/test/java` và xuất hiện trong JAR phụ.

Ngược lại, nếu test JAR còn chứa class `GreetingFormatterTest` có `@Test` thì consumer **không tự động chạy** test class đó chỉ vì nó có dependency `tests`. Surefire mặc định thường scan test output của chính consumer; để chạy tests nằm trong dependencies phải cấu hình scanning phù hợp.

## 4. Lab Java 17: hai Maven modules, hai artifact của một producer

Ta xây dựng Maven reactor:

- `fixture-kit` tạo **main JAR** chứa class `GreetingFormatter`, và **test JAR** chứa `SampleNames` cùng một test class.
- `console-app` dùng **main JAR** ở compile scope và **test JAR** ở test scope. Test của consumer lấy sample data từ `SampleNames` để gọi ứng dụng.

Bộ ví dụ:
- Java 17+
- Maven 3.x tương thích với Maven Compiler Plugin `3.14.1`, Maven JAR Plugin `3.4.2` và Maven Surefire Plugin `3.6.1`.
- JUnit Jupiter `5.11.4`.
- Không có database, HTTP server, tài khoản hay dịch vụ bên ngoài. Maven có thể cần kết nối Maven Central/mirror lần đầu để tải plugins/JUnit.

### 4.1. Sơ đồ artifact và dependency

```text
Maven reactor:
    classifier-lab (pom)
        |
        +-- fixture-kit (jar)
        |      |
        |      +-- fixture-kit-1.0.0.jar           [main]
        |      +-- fixture-kit-1.0.0-tests.jar     [classifier=tests]
        |
        +-- console-app (jar)
               |
               +-- dependency fixture-kit 1.0.0 [compile]
               |
               +-- dependency fixture-kit 1.0.0
               |       classifier=tests, type=test-jar, scope=test
               |
               +-- dependency junit-jupiter, scope=test
```

Việc hai Maven modules cùng nằm trong `<modules>` của root **không tự tạo dependency**. Consumer phải khai báo artifact chính và artifact test JAR riêng, vì chúng dùng hai bộ class khác nhau.

### 4.2. Cây thư mục đầy đủ

```text
classifier-lab/
├── pom.xml
├── fixture-kit/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/training/fixturekit/api/
│       │   └── GreetingFormatter.java
│       └── test/java/dev/training/fixturekit/
│           ├── testdata/SampleNames.java
│           └── api/GreetingFormatterTest.java
└── console-app/
    ├── pom.xml
    └── src/
        ├── main/java/dev/training/console/
        │   └── GreetingApp.java
        └── test/java/dev/training/console/
            └── GreetingAppTest.java
```

Hãy tạo đúng các file ở những mục sau. Tên Java package phải trùng với `package` trong code. Root chỉ là aggregator POM và không chứa `module-info.java`; bài này học **Maven artifacts/classifiers**, không phụ thuộc JPMS.

Linux/macOS:

```bash
mkdir -p classifier-lab/fixture-kit/src/main/java/dev/training/fixturekit/api
mkdir -p classifier-lab/fixture-kit/src/test/java/dev/training/fixturekit/testdata
mkdir -p classifier-lab/fixture-kit/src/test/java/dev/training/fixturekit/api
mkdir -p classifier-lab/console-app/src/main/java/dev/training/console
mkdir -p classifier-lab/console-app/src/test/java/dev/training/console
cd classifier-lab
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "classifier-lab/fixture-kit/src/main/java/dev/training/fixturekit/api" | Out-Null
New-Item -ItemType Directory -Force -Path "classifier-lab/fixture-kit/src/test/java/dev/training/fixturekit/testdata" | Out-Null
New-Item -ItemType Directory -Force -Path "classifier-lab/fixture-kit/src/test/java/dev/training/fixturekit/api" | Out-Null
New-Item -ItemType Directory -Force -Path "classifier-lab/console-app/src/main/java/dev/training/console" | Out-Null
New-Item -ItemType Directory -Force -Path "classifier-lab/console-app/src/test/java/dev/training/console" | Out-Null
Set-Location classifier-lab
```

Các lệnh Maven ở những mục tiếp theo giả định current directory là `classifier-lab`.

### 4.3. Parent aggregator POM: `classifier-lab/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.training.artifacts</groupId>
    <artifactId>classifier-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>fixture-kit</module>
        <module>console-app</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.version>5.11.4</junit.version>
    </properties>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.14.1</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.6.1</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
```

Giải thích:
- `packaging=pom`: root không đóng gói main JAR.
- `<modules>`: hai subprojects được reactor xử lý khi chạy từ root.
- `maven.compiler.release=17`: đảm bảo bytecode/API target Java 17 khi dùng compiler hỗ trợ.
- `pluginManagement`: ghim plugin versions cho các subprojects, **không tự tạo execution test-jar** trong producer.
- `junit.version`: cả hai modules có thể dùng cùng version JUnit Jupiter.
- `project.build.sourceEncoding=UTF-8`: tránh lệch encoding khi compile hoặc lọc resources.

### 4.4. POM producer: `fixture-kit/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.training.artifacts</groupId>
        <artifactId>classifier-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>fixture-kit</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <executions>
                    <execution>
                        <id>attach-tests</id>
                        <goals>
                            <goal>test-jar</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

`fixture-kit` tạo:
- Main JAR từ `target/classes` qua default `jar:jar` lifecycle binding.
- Attached test JAR từ `target/test-classes` qua custom execution `jar:test-jar`.

**Không thêm execution `jar:jar` thủ công cho main JAR** nếu packaging đã bind nó; producer chỉ cần khai báo goal phụ `test-jar`. Java code test vẫn có thể được biên dịch/chạy trong producer trước package.

### 4.5. Main Java class của producer: `GreetingFormatter.java`

Đường dẫn `fixture-kit/src/main/java/dev/training/fixturekit/api/GreetingFormatter.java`:

```java
package dev.training.fixturekit.api;

public final class GreetingFormatter {

    private GreetingFormatter() {
    }

    public static String hello(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Hello, " + name.strip() + "!";
    }
}
```

Class `GreetingFormatter` là **public production API**, nằm trong `src/main/java` và được đóng gói vào **main JAR** `fixture-kit-1.0.0.jar`. Không cần đưa JUnit dependency vào main scope.

### 4.6. Test helper của producer: `SampleNames.java`

Đường dẫn `fixture-kit/src/test/java/dev/training/fixturekit/testdata/SampleNames.java`:

```java
package dev.training.fixturekit.testdata;

public final class SampleNames {

    private SampleNames() {
    }

    public static String person() {
        return "Maven";
    }
}
```

Đây là một **test utility class**, không phải test case. Nó nằm trong `src/test/java` nên được đưa vào `target/test-classes`, và sau khi `jar:test-jar` chạy, được đóng gói vào **test JAR** `fixture-kit-1.0.0-tests.jar`. Nó **không có** trong main JAR nếu không chủ động thay đổi cấu trúc đóng gói.

Một ứng dụng production không nên phụ thuộc vào helper này; consumer chỉ sử dụng nó trong test sources với `scope=test`.

### 4.7. Unit test của producer: `GreetingFormatterTest.java`

Đường dẫn `fixture-kit/src/test/java/dev/training/fixturekit/api/GreetingFormatterTest.java`:

```java
package dev.training.fixturekit.api;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingFormatterTest {

    @Test
    void formatsGreeting() {
        assertEquals("Hello, Unit!", GreetingFormatter.hello("  Unit  "));
    }
}
```

Producer có **một JUnit Jupiter unit test**. Surefire chạy nó trong producer khi reactor đi đến phase `test`. Class biên dịch của test này cũng có thể nằm trong test JAR cùng `SampleNames`; điều đó **không có nghĩa consumer sẽ tự chạy lại nó**.

### 4.8. POM consumer: `console-app/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.training.artifacts</groupId>
        <artifactId>classifier-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>console-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <!-- Main production artifact -->
        <dependency>
            <groupId>dev.training.artifacts</groupId>
            <artifactId>fixture-kit</artifactId>
            <version>${project.version}</version>
        </dependency>

        <!-- Attached test artifact containing SampleNames -->
        <dependency>
            <groupId>dev.training.artifacts</groupId>
            <artifactId>fixture-kit</artifactId>
            <version>${project.version}</version>
            <classifier>tests</classifier>
            <type>test-jar</type>
            <scope>test</scope>
        </dependency>

        <!-- JUnit is declared explicitly in the consumer -->
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Phân tích từng dependency:
1. **Main JAR:** `fixture-kit` với scope mặc định `compile`, cung cấp `GreetingFormatter` cho mã ứng dụng.
2. **Test JAR:** cùng GAV nhưng thêm `classifier=tests` và `type=test-jar`, scope `test`, cung cấp `SampleNames` chỉ cho tests consumer.
3. **JUnit Jupiter:** khai báo riêng ở consumer vì consumer có `@Test`. Không trông chờ test-scoped dependencies ở producer tự truyền sang qua test JAR.

Hai dependencies `fixture-kit` khác nhau ở **classifier/type**; Maven không coi chúng là một file JAR duy nhất. Đưa test JAR vào `scope=compile` chỉ để code production sử dụng test helper là thiết kế không hợp lý trong ví dụ này.

### 4.9. Main Java của consumer: `GreetingApp.java`

Đường dẫn `console-app/src/main/java/dev/training/console/GreetingApp.java`:

```java
package dev.training.console;

import dev.training.fixturekit.api.GreetingFormatter;

public final class GreetingApp {

    private GreetingApp() {
    }

    public static String message(String name) {
        return GreetingFormatter.hello(name);
    }

    public static void main(String[] args) {
        System.out.println(message("Application"));
    }
}
```

Class ứng dụng **chỉ import production API** từ main JAR. Nếu vô tình import `SampleNames` trong main source, compiler sẽ không tìm thấy class đó trên compile classpath của consumer do test JAR có scope `test`. Đây là một **rào chắn scope có chủ đích**.

### 4.10. Unit test của consumer: `GreetingAppTest.java`

Đường dẫn `console-app/src/test/java/dev/training/console/GreetingAppTest.java`:

```java
package dev.training.console;

import dev.training.fixturekit.testdata.SampleNames;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingAppTest {

    @Test
    void usesSharedTestFixture() {
        assertEquals("Hello, Maven!", GreetingApp.message(SampleNames.person()));
    }
}
```

Trong `src/test/java` của consumer:
- Class `GreetingApp` có sẵn từ code production của consumer.
- `SampleNames` có sẵn nhờ **dependency test JAR đã attach**.
- `@Test` và `assertEquals` có sẵn nhờ `junit-jupiter` khai báo trực tiếp.

Đây là một test minh họa đơn giản để chứng minh **test classpath được kết hợp từ artifact chính, artifact có classifier và JUnit test dependency**.

## 5. Build và kiểm chứng lab end-to-end

Đứng tại `classifier-lab`, chạy:

```bash
mvn -version
mvn -B -ntp clean verify
```

Đây là lựa chọn thích hợp vì từng Maven module được reactor build qua `package`/`verify`, đủ để producer attach `tests` JAR trước khi consumer cần dependency đó.

Một lần build thành công dự kiến:
1. Maven đọc parent aggregator POM.
2. Resolver/reactor thấy consumer phụ thuộc producer `fixture-kit`.
3. Maven biên dịch `GreetingFormatter`, `SampleNames` và `GreetingFormatterTest`.
4. Surefire chạy **1 test** trong producer.
5. Maven JAR Plugin tạo `fixture-kit-1.0.0.jar` và execution `test-jar` tạo `fixture-kit-1.0.0-tests.jar`.
6. Reactor chuyển sang consumer; Compiler Plugin biên dịch `GreetingApp`.
7. Compiler Plugin biên dịch `GreetingAppTest` với test JAR có `SampleNames` trên test classpath.
8. Surefire chạy **1 test** trong consumer.
9. Maven đóng gói `console-app-1.0.0.jar` và hoàn tất build nếu không có lỗi khác.

**Hai kết quả test về nội dung thống kê được kỳ vọng:**

```text
fixture-kit: Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
console-app: Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
```

Đây là **bản diễn giải số test mong đợi**, không phải nguyên văn Maven stdout. Maven còn có logging prefixes, class display name, plugin headings, timings và reactor summary.

### 5.1. JAR files được tạo

Sau khi `mvn clean verify` thành công:

```text
fixture-kit/target/fixture-kit-1.0.0.jar
fixture-kit/target/fixture-kit-1.0.0-tests.jar
console-app/target/console-app-1.0.0.jar
```

Lệnh `mvn package` cũng đủ để tạo hai JAR producer nếu đi qua các phases cần thiết và dependencies đầy đủ. Nhưng dùng `verify` trong lab cho phép chạy hết kiểm tra lifecycle đến verify mà không cắt sớm.

### 5.2. Kiểm tra JAR bằng công cụ JDK

Từ root `classifier-lab`:

```bash
jar --list --file fixture-kit/target/fixture-kit-1.0.0.jar
jar --list --file fixture-kit/target/fixture-kit-1.0.0-tests.jar
```

Ở **main JAR**, tìm:

```text
dev/training/fixturekit/api/GreetingFormatter.class
```

Ở **test JAR**, tìm:

```text
dev/training/fixturekit/testdata/SampleNames.class
dev/training/fixturekit/api/GreetingFormatterTest.class
```

Đây là **những entries đặc trưng**, không phải toàn bộ danh sách của JAR. Cả hai JAR thường còn có `META-INF/MANIFEST.MF` và Maven metadata entries. Thứ tự output có thể thay đổi.

Bạn **không nên** tìm `SampleNames.class` trong main JAR hoặc kỳ vọng `GreetingFormatter.class` tự xuất hiện trong test JAR. Hai file đóng gói **hai thư mục đầu vào khác nhau** theo goal.

### 5.3. Chạy Java main class

Vì consumer sử dụng main JAR producer, khi chạy trực tiếp bằng Java launcher cần cấp cả **hai main classpath roots/JARs**.

Linux/macOS:

```bash
java -cp "console-app/target/classes:fixture-kit/target/fixture-kit-1.0.0.jar" dev.training.console.GreetingApp
```

Windows PowerShell:

```powershell
java -cp "console-app\target\classes;fixture-kit\target\fixture-kit-1.0.0.jar" dev.training.console.GreetingApp
```

**Stdout chính xác của `GreetingApp.main` là:**

```text
Hello, Application!
```

Không cần test JAR hoặc JUnit ở runtime classpath này vì `GreetingApp` chỉ dùng `GreetingFormatter` từ **main JAR**. Chạy `java -jar console-app/target/console-app-1.0.0.jar` có thể thất bại nếu JAR chưa khai báo `Main-Class` trong manifest hoặc thiếu runtime dependencies; lệnh `-cp` ở trên minh họa rõ các thành phần cần thiết.

### 5.4. Không đọc manifest để đoán classifier

Cả main JAR và test JAR có thể chứa `META-INF/MANIFEST.MF`, nhưng **classifier là metadata tọa độ artifact của Maven**, không phải một trường chuẩn bắt buộc như `Classifier: tests` trong manifest.

Cách xác nhận loại artifact đáng tin cậy là:
1. File name do Maven Jar Plugin tạo.
2. Execution POM đã tạo/attach artifact.
3. Dependency selection bằng classifier/type.
4. Artifact được ghi dưới local/remote Maven repository.
5. Nội dung JAR thực tế xác nhận mục đích đóng gói.

Manifest hữu ích cho `Main-Class`, `Class-Path`, Multi-Release flags và các attribute tùy chỉnh; nó **không thay** Maven coordinates.

## 6. Cách khai báo dependency chọn test JAR

Apache Maven hỗ trợ handler `type=test-jar` với extension `jar` và classifier mặc định `tests`. Cấu hình tường minh dễ đọc:

```xml
<dependency>
    <groupId>dev.training.artifacts</groupId>
    <artifactId>fixture-kit</artifactId>
    <version>1.0.0</version>
    <classifier>tests</classifier>
    <type>test-jar</type>
    <scope>test</scope>
</dependency>
```

Trong Maven 3 thông thường, một dependency chỉ ghi `<type>test-jar</type>` cũng có thể chọn đúng classifier `tests` nhờ type handler:

```xml
<dependency>
    <groupId>dev.training.artifacts</groupId>
    <artifactId>fixture-kit</artifactId>
    <version>1.0.0</version>
    <type>test-jar</type>
    <scope>test</scope>
</dependency>
```

Một dạng khác tương đương về artifact vật lý là ghi **classifier tests, type jar** (mặc định):

```xml
<dependency>
    <groupId>dev.training.artifacts</groupId>
    <artifactId>fixture-kit</artifactId>
    <version>1.0.0</version>
    <classifier>tests</classifier>
    <type>jar</type>
    <scope>test</scope>
</dependency>
```

Không cần khai báo cả ba biến thể ở consumer: chúng chọn **cùng artifact test JAR**, và khai báo lặp không làm test chạy “đầy đủ hơn”. Trong ví dụ lab đã chọn dạng **`type=test-jar` + `classifier=tests`** vì trực quan và khớp hướng dẫn attached-tests chính thức.

### 6.1. Type khác file extension

`<type>test-jar</type>` **không có nghĩa tên file kết thúc bằng `.test-jar`**. Artifact vẫn là JAR có extension `.jar`. Type được Maven artifact handler ánh xạ sang extension và classifier phù hợp.

Ví dụ:

```text
Dependency type:       test-jar
Effective classifier:  tests
Physical extension:    jar
Expected filename:     fixture-kit-1.0.0-tests.jar
```

Không tạo tên file `fixture-kit-1.0.0.test-jar` rồi kỳ vọng Maven tự nhận diện nó là test JAR.

### 6.2. Scope test không phải classifier tests

`<scope>test</scope>` điều khiển **khi nào** dependency xuất hiện trong consumer classpath. `<classifier>tests</classifier>` điều khiển **file nào** cần resolve.

Bạn có thể có classifier `tests` nhưng scope `compile`, dù đó thường là thiết kế sai cho test helpers. Ngược lại, dependency `scope=test` mà không có classifier chọn **main JAR** của producer cho test classpath, không phải test JAR.

## 7. Giới hạn quan trọng: test dependencies không tự đi theo test JAR

Đây là bẫy đã được Apache Maven ghi rõ trong hướng dẫn **Creating a JAR containing test classes**: attached test JAR của một project **không truyền toàn bộ dependencies ở `test` scope** của producer sang consumer theo cách nhiều người mong đợi.

Ví dụ producer có:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>
```

Consumer chỉ thêm:

```xml
<dependency>
    <groupId>dev.training.artifacts</groupId>
    <artifactId>fixture-kit</artifactId>
    <version>1.0.0</version>
    <classifier>tests</classifier>
    <type>test-jar</type>
    <scope>test</scope>
</dependency>
```

**Không được giả định consumer tự nhận `junit-jupiter`** do producer khai báo ở test scope. Nếu consumer code import `org.junit.jupiter.api.Test` hoặc dùng Jupiter Engine, nó vẫn cần JUnit dependency phù hợp trong POM của chính mình (hoặc dependencyManagement/parent áp dụng đúng).

### 7.1. Vì sao JAR file không mang theo dependency graph test riêng?

Test JAR là một **attached artifact** của cùng Maven project. Nó không tự tạo một POM độc lập chứa toàn bộ “test-classpath của producer”. Maven dependency mediation vẫn dựa vào POM metadata, type/classifier và scope rules. Với Maven 3, các test-scoped dependencies của producer không tự được chọn bắc cầu như điều kiện để dùng mọi class trong attached test JAR.

Điều này giải thích lỗi:
- Compile consumer test class import một helper trong test JAR thành công.
- Nhưng khi helper gọi thư viện bên thứ ba chỉ có trong producer's `test` scope, JVM consumer thiếu library đó và ném `NoClassDefFoundError`.
- Consumer phải khai báo các libraries cần thiết hoặc chuyển helper sang một module được thiết kế cho tái sử dụng.

### 7.2. Khi nào nên tạo test-fixtures module riêng?

Nếu nhiều modules cần reusable test utilities có nhiều dependencies, hãy tạo project riêng, ví dụ `test-support`:

```text
workspace/
    main-library/
    test-support/
        src/main/java/dev/training/testsupport/...
    service/
```

Trong POM của `test-support`, đưa **reusable helper code vào `src/main/java`**, và khai báo các dependency cần cho helper bằng scope phù hợp (thường `compile` nếu consumer cần để chạy helper). Consumer dùng:

```xml
<dependency>
    <groupId>dev.training.artifacts</groupId>
    <artifactId>test-support</artifactId>
    <version>1.0.0</version>
    <scope>test</scope>
</dependency>
```

Đây là **main JAR của một project chuyên dụng**, nhưng được consumer sử dụng ở test scope. Cách này làm **POM dependency graph của test utility rõ ràng**, tránh giới hạn attached test JAR có chung POM với artifact chính.

**Lựa chọn:** attached `tests` JAR tiện cho vài helpers đơn giản đã sống trong module hiện hữu; project `test-support` chuyên dụng phù hợp khi utilities trở thành API dùng chung với nhiều dependencies, versioning và compatibility cần quản lý riêng.

## 8. Test JAR chứa @Test có tự động được chạy ở consumer?

Không phải mặc định.

Lab producer có class `GreetingFormatterTest` trong test JAR. Consumer có dependency tới test JAR để import `SampleNames`, nhưng **Surefire mặc định không nhất thiết scan mọi JAR dependency để chạy test classes bên trong**.

Nếu bạn **muốn thực thi lại test classes từ attached test JAR** (khác mục tiêu tái sử dụng helper), Apache Maven có hướng dẫn cấu hình `dependenciesToScan` cho Surefire:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.6.1</version>
    <configuration>
        <dependenciesToScan>
            <dependency>dev.training.artifacts:fixture-kit:test-jar:tests</dependency>
        </dependenciesToScan>
    </configuration>
</plugin>
```

Đây là **đoạn cấu hình tùy chọn** để đặt trong `<build><plugins>` của consumer, **không có trong POM lab cơ bản**. Chỉ áp dụng khi thật sự muốn scan artifact test JAR; cần bảo đảm framework engine và mọi runtime test dependencies tương ứng có mặt.

Khi cấu hình scanning:
- Một số tests thuộc producer có thể cần resources/config không tồn tại trong consumer.
- Tests có thể chạy trùng trên producer và consumer, làm chi phí và side effects tăng.
- Test discovery có thể khác khi JUnit version/engine khác.
- Không nên coi việc chạy lại test của thư viện khác là thay thế unit tests/integration tests của consumer.

Trong bài thực hành, **chỉ chia sẻ `SampleNames`** và chạy test `GreetingAppTest` do consumer sở hữu; không cần `dependenciesToScan`.

## 9. Reactor Maven: vì sao `mvn test` có thể chưa đủ?

Một subtleness quan trọng trong multi-module builds: goal `jar:test-jar` mặc định chạy ở **phase `package`**. Nếu reactor dùng:

```bash
mvn -B -ntp clean test
```

Maven có thể biên dịch test helpers của `fixture-kit` ở `test-compile`, nhưng **chưa attach `fixture-kit-1.0.0-tests.jar`** vì `package` chưa chạy. Khi `console-app` cần dependency classifier `tests` để compile tests, Resolver có thể không tìm được attached artifact trong reactor hoặc local repository phù hợp.

Đó không phải do `SampleNames` thiếu `public`, mà do **giai đoạn tạo artifact chưa đến**.

### 9.1. Lệnh phù hợp cho lab

```bash
mvn -B -ntp clean verify
```

hoặc:

```bash
mvn -B -ntp clean package
```

vì các lệnh này đưa producer đến `package` và tạo/attach test JAR trước khi consumer cần nó theo reactor build order.

Nếu muốn chạy riêng consumer và dependencies upstream trong reactor:

```bash
mvn -B -ntp -pl :console-app -am clean verify
```

`-pl` chọn consumer, `-am` thêm upstream Maven reactor project cần thiết. Đảm bảo phiên bản Maven/plugin và reactor resolution phù hợp; không suy ra `-am` sẽ tự tạo artifact ở phase bị bỏ qua.

### 9.2. Khi nào cần install?

Nếu dùng consumer như **một build độc lập không có reactor producer**, nó cần resolve `fixture-kit:1.0.0:tests` từ local/remote repository.

Từ root sau khi đã kiểm tra tests:

```bash
mvn -B -ntp clean install
```

Điều này chạy lifecycle đến `install` và cài POM, main JAR, attached test JAR vào local Maven repository khi build thành công. Một project khác có thể sử dụng artifact test JAR từ repository cục bộ đó.

**Cài local không đồng nghĩa publish lên repository chung.** Trên CI/máy khác, cần deploy artifact lên repository được phép hoặc build producer cùng reactor. Không copy JAR thủ công vào `~/.m2/repository` rồi coi đó là quy trình phát hành đầy đủ.

### 9.3. Kiểm tra cấu trúc local repository

Nếu dùng local repository mặc định, ví dụ đường dẫn tương đối theo Maven repository layout:

```text
~/.m2/repository/dev/training/artifacts/fixture-kit/1.0.0/
    fixture-kit-1.0.0.pom
    fixture-kit-1.0.0.jar
    fixture-kit-1.0.0-tests.jar
```

Trên Windows, local Maven repository thường nằm ở `%USERPROFILE%\.m2\repository`, nhưng có thể được thay đổi bằng `settings.xml` hoặc `-Dmaven.repo.local=...`. Hãy kiểm tra đúng repository path mà Maven đang dùng, không cứng hóa đường dẫn từ một máy khác.

## 10. Đính kèm một JAR khác bằng classifier tùy chỉnh

Test JAR là một trường hợp đặc biệt. Bạn còn có thể attach **JAR phụ với classifier như `client`** chỉ chứa một tập class được lọc từ main build output.

Maven JAR Plugin có goal `jar:jar` và các options `classifier`, `includes`, `excludes`. Ví dụ **đoạn trong `<build><plugins>`** của producer:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <version>3.4.2</version>
    <executions>
        <execution>
            <id>attach-client-jar</id>
            <phase>package</phase>
            <goals>
                <goal>jar</goal>
            </goals>
            <configuration>
                <classifier>client</classifier>
                <includes>
                    <include>dev/training/fixturekit/api/**</include>
                </includes>
            </configuration>
        </execution>
    </executions>
</plugin>
```

**Đây là một cấu hình thay thế/bổ sung để học**, không chèn nguyên đoạn này như plugin thứ hai trùng `artifactId` vào cùng POM lab mà không hợp nhất executions.

Khi main jar goal đã chạy theo packaging, execution mới với classifier `client` có thể tạo:

```text
fixture-kit-1.0.0.jar
fixture-kit-1.0.0-client.jar
```

Nếu producer **đồng thời** giữ execution `test-jar`, và thêm đúng execution `attach-client-jar` vào cùng plugin, các artifact có thể là:

```text
fixture-kit-1.0.0.jar
fixture-kit-1.0.0-tests.jar
fixture-kit-1.0.0-client.jar
```

**Quy tắc từ hướng dẫn chính thức:** đặt goal `jar:jar` phụ trong **execution riêng** và cấp **classifier**. Nếu cấu hình sai khiến goal phụ không có classifier, nó có thể thay thế/xung đột với main artifact thay vì attach một artifact mới.

### 10.1. Classifier là lựa chọn artifact, không phải bộ lọc tự động

Tên `client` không khiến Maven tự biết package nào là API. Chính `<includes>` và `<excludes>` quyết định nội dung JAR. Nếu patterns không khớp compiled classes, bạn có thể tạo JAR rỗng hoặc thiếu classes.

Một JAR `client` chỉ có một phần public API có thể vẫn thiếu dependency của API đó. Phải kiểm tra class closure, runtime requirements, JPMS module descriptor (nếu có) và khả năng sử dụng thật; Maven không tự phân tích “client classes” chỉ vì classifier mang tên `client`.

### 10.2. Consumer chọn JAR client ra sao?

Ví dụ dependency trong một project khác:

```xml
<dependency>
    <groupId>dev.training.artifacts</groupId>
    <artifactId>fixture-kit</artifactId>
    <version>1.0.0</version>
    <classifier>client</classifier>
    <type>jar</type>
</dependency>
```

Dependency chọn `fixture-kit-1.0.0-client.jar` thay vì main JAR không classifier. Ở đây `type=jar` là bình thường, không phải `test-jar`, và scope mặc định là `compile` nếu không khai báo khác.

**Không thể dùng đồng thời hai biến thể của cùng class với classpath tùy tiện** mà không xem khả năng trùng class. Nếu đưa cả main JAR và client JAR chứa cùng package/classes vào runtime classpath, classloader order có thể gây behavior khó đoán. Thiết kế classifier phải có mục đích và cách tiêu thụ nhất quán.

## 11. Đính kèm artifact không phải JAR

Một số pipeline tạo file `.json`, `.zip`, `.tar.gz` hoặc tài liệu schema và muốn Maven install/deploy cùng artifact chính. Có thể dùng **MojoHaus Build Helper Maven Plugin** với goal `build-helper:attach-artifact`.

Ví dụ một project **đã tạo sẵn file** `target/reports/schema.json` trước phase package:

```xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>build-helper-maven-plugin</artifactId>
    <version>3.6.2</version>
    <executions>
        <execution>
            <id>attach-schema</id>
            <phase>package</phase>
            <goals>
                <goal>attach-artifact</goal>
            </goals>
            <configuration>
                <artifacts>
                    <artifact>
                        <file>${project.build.directory}/reports/schema.json</file>
                        <type>json</type>
                        <classifier>schema</classifier>
                    </artifact>
                </artifacts>
            </configuration>
        </execution>
    </executions>
</plugin>
```

**Đây là ví dụ cấu hình bổ sung, không phải một project runnable độc lập.** Plugin **không tạo `schema.json`**; build của bạn phải có một goal trước đó sinh file với nội dung đúng. Nếu file không tồn tại tại thời điểm attach, plugin có thể báo lỗi; không dùng `skipAttach` để che việc thiếu output đáng lẽ phải có.

Tọa độ/filename theo ý tưởng:

```text
dev.training.artifacts:fixture-kit:1.0.0
classifier: schema
type/extension: json
file: fixture-kit-1.0.0-schema.json
```

Lưu ý ở đây `type=json` xác định extension của artifact; nếu muốn khác, phải dùng cơ chế artifact handler/type phù hợp. Đừng truyền `<type>test-jar</type>` để attach JSON.

### 11.1. Khi nào dùng build-helper:attach-artifact?

- Attach một file schema do generator đã tạo.
- Attach archive/tài liệu phân phối đã được đóng gói.
- Attach một report mà repository policy cho phép publish dưới classifier.
- Đưa output từ Ant, assembly hoặc công cụ build khác vào vòng đời install/deploy của Maven.

**Đừng attach secrets, internal credentials, report chứa dữ liệu nhạy cảm hoặc file tạm thời vô nghĩa** chỉ vì Maven có thể publish. Artifact khi đã deploy có thể được cache và tồn tại lâu dài trong repository.

## 12. Sources JAR, Javadoc JAR và classifier

Hai classifier thường gặp trong Java ecosystem là:

```text
fixture-kit-1.0.0-sources.jar
fixture-kit-1.0.0-javadoc.jar
```

Thông thường:
- **Maven Source Plugin** có goals để tạo/attach source JAR.
- **Maven Javadoc Plugin** có goals để tạo/attach Javadoc JAR.
- Các files này giúp IDE, repository và người dùng xem source/doc của artifact.

**Khác test JAR:** `sources.jar` thường chứa file nguồn Java; `tests.jar` từ `jar:test-jar` thường chứa **compiled test classes/resources**. Đừng suy ra `-tests.jar` là test sources hoặc tài liệu kiểm thử.

Ví dụ **POM snippet riêng** để tạo sources artifact khi project có plugin Source Plugin được chọn đúng version:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-source-plugin</artifactId>
    <version>3.3.1</version>
    <executions>
        <execution>
            <id>attach-sources</id>
            <goals>
                <goal>jar-no-fork</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Đây là một **ví dụ bổ sung** cho Java project, không bắt buộc với lab classifier. Khi đã cấu hình plugin tại phase thích hợp và build thành công, nguồn Java có thể được attach dưới classifier `sources`.

**Không coi `-sources.jar`, `-javadoc.jar` và `-tests.jar` là cùng một artifact**. Mỗi classifier có mục đích riêng; dependencies thường chỉ chọn artifact cụ thể cần dùng. IDE có thể tự tải source/javadoc attached artifacts khi chúng được publish đúng convention.

## 13. Jar manifest và attached artifacts: những điều dễ nhầm

Tệp `META-INF/MANIFEST.MF` là một phần nội dung JAR. Nó có thể chứa:
- `Manifest-Version`.
- `Main-Class` nếu build cấu hình executable JAR.
- `Class-Path` manifest attribute theo thiết kế.
- `Multi-Release: true` khi xây multi-release JAR.
- Các thuộc tính khác do Maven Archiver hoặc plugin thêm.

**Classifier là thuộc Maven artifact coordinates và repository filename**, không phải manifest field bắt buộc.

| Hiện tượng | Ý nghĩa đúng |
| --- | --- |
| JAR có `Main-Class` | Java launcher có thể biết main entrypoint (nhưng vẫn cần dependencies). |
| File có hậu tố `-tests.jar` | Tên file gợi convention, cần xác minh artifact thực đã attach. |
| POM dependency có `classifier=tests` | Maven sẽ resolve biến thể tương ứng, không chạy tests chỉ vì tên. |
| JAR có `module-info.class` | Đây là explicit JPMS module metadata; không đồng nghĩa classifier. |
| JAR có `Automatic-Module-Name` | Gợi tên JPMS automatic module; độc lập với Maven classifier. |

Nếu bạn copy một JAR và tự đổi tên file thành `fixture-kit-1.0.0-tests.jar` mà không attach/deploy đúng coordinates, Maven consumer vẫn có thể không resolve được. Ngược lại, manifest có thể không chứa từ “tests” mà artifact vẫn là test JAR hợp lệ.

## 14. Maven reactor và dependency graph của artifact phụ

Reactor sắp xếp Maven projects dựa trên các dependency relationships và các quy tắc được Maven hỗ trợ. Trong lab:
- `console-app` phụ thuộc `fixture-kit`.
- Producer phải chạy các goals để tạo/attach artifacts trước thời điểm consumer cần.
- Với `mvn clean verify` tại root, toàn bộ producer được build qua package trước khi consumer đi đến test compilation.

**Không nhầm module Maven với artifact classifier.** Một Maven module có thể tạo nhiều attached artifacts; tạo classifier **không làm Maven sinh thêm một project reactor**.

### 14.1. Nếu chạy consumer riêng ngoài reactor

Lệnh:

```bash
mvn -B -ntp -f console-app/pom.xml test
```

có thể fail nếu `fixture-kit` chưa được cài/publish ở repository mà Maven đang dùng. Trên máy dev từng chạy `mvn install` của producer, lệnh có thể thành công; trên CI sạch lại fail. Đây là **khác biệt môi trường repository**, không nên giải quyết bằng cách bỏ dependency classifier.

### 14.2. Nếu chỉ chạy root đến phase test

Lệnh:

```bash
mvn -B -ntp clean test
```

có thể gặp lỗi không resolve được test JAR trong reactor mới vì producer chưa qua `package`. **Lệnh đúng cho lab mới sạch là `mvn clean verify`**, không ép Surefire bỏ test của consumer để tránh lỗi.

### 14.3. Dependency tree giúp kiểm tra gì?

Sau khi artifact đã có thể resolve, bạn có thể xem dependency graph của consumer bằng Maven Dependency Plugin:

```bash
mvn -pl :console-app dependency:tree
```

Tìm cả:
- `fixture-kit` dưới dạng main JAR/compile scope.
- `fixture-kit` dưới dạng classifier `tests`/test scope.

**Hình thức dòng output có thể thay đổi theo version Maven Dependency Plugin**. Không xem ký tự thứ tự trong CLI output như một chuẩn tọa độ artifact cố định; kiểm tra groupId, artifactId, version, type/classifier và scope tương ứng.

### 14.4. Version và classifier không thay thế nhau

Nếu JAR chính được cập nhật từ version `1.0.0` lên `1.1.0`, test JAR cùng classifier `tests` cũng thường được publish ở `1.1.0` khi cùng project. Consumer không nên trộn `fixture-kit:1.1.0` main JAR với `fixture-kit:1.0.0:tests` mà không có cơ sở tương thích.

Dùng `${project.version}` trong lab vì cả producer và consumer được quản lý chung version. Với hệ thống version độc lập, khai báo explicit version hoặc dependencyManagement đúng mục đích.

## 15. Các lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Không có `-tests.jar` sau build | Chưa bind `jar:test-jar`, chưa đến phase `package` hoặc test output thiếu. | Xem producer POM, goal logs, `target/test-classes` và `mvn package`. |
| Consumer báo không tìm thấy artifact `...:tests` | Producer chưa tạo/install/publish attached artifact hoặc dùng sai classifier. | Kiểm tra đúng file, GAV/classifier và reactor/repository. |
| Consumer test báo `cannot find symbol SampleNames` | Không có test JAR trong test classpath hoặc helper không public/sai package. | Kiểm tra `<classifier>tests</classifier>`, `<type>test-jar</type>`, test scope và `jar --list`. |
| Consumer main code không import được `SampleNames` | Test JAR khai báo scope `test` nên không có ở main compile classpath. | Đưa helper vào main module nếu nó là production API, không đổi scope chỉ để bypass. |
| Consumer chạy test nhưng thiếu JUnit | Test-scoped dependencies của producer không tự truyền theo attached test JAR. | Thêm JUnit dependency trực tiếp ở consumer hoặc tách utility module. |
| `NoClassDefFoundError` từ helper | Helper gọi library test-scope chỉ có ở producer. | Kiểm tra runtime test dependency tree và library cần thiết. |
| `jar:jar` chạy lại tạo artifact phụ nhưng xung đột | Thiếu classifier hoặc execution không được khai báo riêng. | Gán classifier và tạo execution riêng như tài liệu JAR Plugin. |
| File tự tạo không được Maven deploy | File chưa được attach bằng plugin. | Dùng plugin goal attach phù hợp và verify repository artifacts. |
| Consumer không tự chạy test class của producer | Surefire không scan test dependency JAR mặc định. | Dùng `dependenciesToScan` có chủ đích, không nhầm với helper reuse. |
| `mvn test` fail nhưng `mvn verify` pass | Test JAR attached chỉ ở phase package. | Build producer qua package hoặc install trước consumer; kiểm tra reactor. |
| Repository có `-tests.jar` nhưng code vẫn sai | Nội dung artifact có thể không khớp version/source. | Kiểm tra actual JAR contents, version, local cache và logs. |
| JAR có classifier nhưng thiếu class cần | `includes/excludes` không khớp compiled output. | Dùng `jar --list`, kiểm tra package paths và build output. |

### 15.1. “Could not resolve artifact ...:tests”

Đọc toàn bộ thông điệp lỗi: artifact type có thể hiển thị `test-jar` hoặc `jar` tùy Maven Resolver/type handler. Hãy kiểm tra:
1. Producer đã chạy `jar:test-jar` ở phase package chưa?
2. File `fixture-kit-1.0.0-tests.jar` có thật không?
3. Consumer dependency có đúng `groupId`, `artifactId`, `version`, classifier `tests`, type tương ứng?
4. Reactor có build producer cùng invocation đủ xa không?
5. Nếu consumer là build riêng, artifact đã được install/deploy vào repository có thể truy cập chưa?
6. Có mirror/proxy/repository settings chặn đúng artifact không?

**Không dùng `-DskipTests` như một “cách sửa” lâu dài cho artifact resolution**; flag đó điều khiển test execution và không đảm bảo test JAR đã tồn tại.

### 15.2. “No test jar produced”

Kiểm tra `jar:test-jar` đã bind trong plugin executions, có test classes/resources, compiler/testCompile có chạy, và lệnh đạt phase package. Maven JAR Plugin có các cờ như `skipIfEmpty` và `skip`; nếu bật thì test JAR có thể không tạo. Trong JAR Plugin 3.4.2, `maven.test.skip` liên quan việc bỏ qua test JAR, nên một pipeline bỏ qua test compilation/execution còn có thể bỏ luôn attached test artifact.

### 15.3. “Test runs locally but not on CI”

Máy phát triển có thể còn artifact classifier trong `~/.m2` từ build cũ. CI clean repository phát hiện thiếu test JAR ngay. Hãy dùng build từ reactor root qua `package/verify`, pin versions, công khai cơ chế publish và tránh reliance vào local cache cá nhân.

### 15.4. “Attachment exists but deploy only publishes main JAR”

Kiểm tra plugin thực sự **attach** artifact vào Maven project thay vì chỉ tạo file dưới `target`. Build Helper/plugin có cấu hình `attach`/`skipAttach`/lifecycle execution khác nhau theo version. Xem Maven deploy logs, repository target path và quyền publish; không giả định vì file tồn tại thì chắc chắn được deploy.

## 16. skipTests, maven.test.skip và ảnh hưởng đến test JAR

Với Maven Java project thông thường:

```bash
mvn package -DskipTests
```

thường **bỏ Surefire test execution** nhưng Maven Compiler Plugin vẫn biên dịch `src/test/java`; do đó `jar:test-jar` vẫn có thể đóng gói các compiled test classes.

Ngược lại:

```bash
mvn package -Dmaven.test.skip=true
```

thường **bỏ test compilation** và các plugin test runner liên quan. Maven JAR Plugin goal `test-jar` cũng có `skip` property `maven.test.skip`; vì vậy không nên kỳ vọng vẫn có đầy đủ attached test JAR trong build dùng flag này.

**Phân biệt:**
- `skipTests`: thường bỏ *chạy* tests, không có nghĩa bỏ tạo test helpers JAR.
- `maven.test.skip=true`: có thể bỏ cả test compilation/test-jar creation theo plugins chuẩn.
- `skipIfEmpty=true` của `jar:test-jar`: tránh tạo JAR rỗng, không phải cờ tương đương `skipTests`.
- `testFailureIgnore=true`: liên quan phản ứng khi tests fail, không phải cơ chế attach artifact.

Nếu consumer phụ thuộc vào test JAR, thiết kế pipeline để producer thật sự tạo/publish nó. Một job build producer bỏ test compilation mà job consumer vẫn yêu cầu `tests` JAR là mâu thuẫn workflow.

## 17. Attached artifact trong CI và repository

Quy trình gợi ý:
1. Build root reactor bằng `mvn -B -ntp clean verify` trên JDK version được kiểm soát.
2. Kiểm tra test results của cả producer và consumer.
3. Xác minh main JAR, test JAR có nội dung đúng.
4. Với pipeline publish, thực hiện `install`/`deploy` theo chính sách quyền phù hợp, không dùng shell copy vào repository.
5. Kiểm tra classifier artifact đã có ở repository cùng GAV/version.
6. Ở job consumer tách biệt, khai báo đúng dependency variant và test scope.
7. Thu thập XML reports để CI hiểu có bao nhiêu tests được chạy.
8. Không dùng test JAR làm đường đi để đưa test-only libraries vào runtime production.
9. Tránh publish thông tin nhạy cảm trong test fixtures, test resources hoặc diagnostic reports.
10. Giữ versioning và retention policy thống nhất giữa main artifact và attached classifiers.

### 17.1. Test resources có thể mang dữ liệu nhạy cảm

Vì `jar:test-jar` đóng gói `target/test-classes`, test resources đưa vào đó cũng có thể được publish. Nếu `src/test/resources` có:
- Credentials thật.
- File `.env` chứa token.
- Private fixtures với dữ liệu cá nhân.
- Internal endpoints/connection strings không công khai.
- Snapshots database có thông tin nhận diện.

thì **attached test JAR có thể phát tán chúng** đến repository và người có quyền download. Hãy kiểm tra nội dung JAR bằng `jar --list`, áp chính sách fixtures sạch, và cân nhắc includes/excludes. Đừng giả định “test-only” đồng nghĩa “private”.

### 17.2. Reproducibility và outputTimestamp

Maven JAR Plugin hỗ trợ `project.build.outputTimestamp` để hỗ trợ reproducible archive entries. Với build cần so sánh hash/version, cần cố định timestamps/nguồn dữ liệu theo chính sách reproducible builds. Classifier không tự bảo đảm byte-for-byte reproducibility.

Ví dụ parent POM có:

```xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
```

Đây là **đoạn XML minh họa**, không cần thêm cho lab cơ bản. Một build reproducible còn cần kiểm soát compiler/JDK/plugin versions, file ordering, encoding và generated inputs; không coi một property là đủ cho mọi project.

## 18. Khi nào chọn attached test JAR, khi nào chọn module riêng?

| Tiêu chí | Attached test JAR (`classifier=tests`) | Module `test-support` riêng |
| --- | --- | --- |
| Khởi tạo | Ít cấu hình, thêm `jar:test-jar`. | Cần project/POM riêng. |
| Vị trí source | `src/test/java` của producer hiện hữu. | `src/main/java` của utility module. |
| Test dependencies bắc cầu | Không tự nhận đầy đủ producer `test` scope. | Có thể quản lý rõ dependencies cần thiết theo scope thông thường của utility. |
| Versioning | Gắn với version producer. | Có thể version riêng hoặc theo reactor. |
| Phù hợp | Vài helper đơn giản chia sẻ giữa modules. | Fixture/toolkit lớn, API dùng chung, nhiều consumers và dependencies. |
| Rủi ro | Test code/resources được publish vô tình; runtime deps thiếu. | Thêm một artifact/lifecycle cần duy trì. |

**Nguyên tắc:** khi helper trở thành thư viện dùng chung có contract rõ ràng, nên xem nó như một library thật với POM/dependencies/semantic versioning rõ ràng, thay vì cố buộc attached `tests` JAR phục vụ mọi mục đích.

## 19. Checklist kiểm tra trước khi phát hành classifier artifact

- [ ] Biết rõ artifact chính và artifact phụ khác nhau về classifier, extension và nội dung.
- [ ] `maven-jar-plugin` version được ghim (lab `3.4.2`).
- [ ] `jar:test-jar` có execution bind vào lifecycle thích hợp; project giữ packaging `jar`.
- [ ] Maven đi đến `package` trước khi consumer cần attached test JAR.
- [ ] `target/test-classes` chứa đúng compiled classes/resources mong muốn.
- [ ] `jar --list` xác nhận JAR chính và test JAR chứa đúng nhóm classes.
- [ ] Consumer dependency có đúng GAV, classifier/type và scope.
- [ ] Không giả định JUnit hoặc test-scoped dependencies truyền qua test JAR.
- [ ] Nếu cần scan test class trong dependency JAR, cấu hình `dependenciesToScan` có chủ đích.
- [ ] Không dùng helper test-scoped trong code production.
- [ ] Không trùng classifier/type/version với attachment khác không mong muốn.
- [ ] Artifact phụ do plugin attach thật, không chỉ tạo file cùng tên.
- [ ] `install`/`deploy` phát hành artifact phụ theo đúng repository workflow.
- [ ] Không có secrets hoặc private datasets bị đóng gói trong test resources.
- [ ] Test/CI báo đúng số tests và artifact file versions.
- [ ] Đối với classifier tự tạo, `includes/excludes` đã được kiểm tra với compiled contents.
- [ ] Build trên CI sạch không phụ thuộc artifact cũ trong local repository.

## 20. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** Classifier có giống dependency scope không?

**Đáp án:** Không. Classifier chọn **biến thể artifact**; scope xác định **ngữ cảnh classpath/transitivity** của dependency.

**Câu 2.** Goal nào tạo JAR từ `target/test-classes`?

**Đáp án:** `jar:test-jar` của Maven JAR Plugin.

**Câu 3.** Classifier mặc định của `jar:test-jar` là gì?

**Đáp án:** `tests`.

**Câu 4.** Với producer `fixture-kit:1.0.0`, hai JAR output chính của lab tên gì?

**Đáp án:** `fixture-kit-1.0.0.jar` và `fixture-kit-1.0.0-tests.jar`.

**Câu 5.** Có cần thay producer `<packaging>jar</packaging>` bằng `test-jar` không?

**Đáp án:** Không. Dùng `jar` cho artifact chính và attach test JAR qua plugin execution.

**Câu 6.** `<type>test-jar</type>` có nghĩa file có extension `.test-jar` không?

**Đáp án:** Không. Maven type handler ánh xạ test-jar sang JAR extension với classifier `tests`.

**Câu 7.** Một consumer khai báo main dependency `fixture-kit` ở scope test có tự nhận test JAR không?

**Đáp án:** Không. Nếu không khai báo classifier/type phù hợp, dependency chọn main JAR.

**Câu 8.** Vì sao lab consumer có hai dependencies cùng GAV producer?

**Đáp án:** Một dependency lấy **main JAR** cho production code; dependency kia chọn **test JAR** cho test helper class.

**Câu 9.** Vì sao consumer còn phải khai báo `junit-jupiter` riêng?

**Đáp án:** Test-scoped dependencies ở producer không tự truyền đầy đủ qua attached test JAR; consumer cần JUnit để compile/execute tests của mình.

**Câu 10.** `GreetingFormatterTest` có nằm trong test JAR không, và consumer có tự chạy nó không?

**Đáp án:** Class test có thể nằm trong JAR vì đã biên dịch ở producer, nhưng consumer không tự chạy nó nếu không cấu hình scanning dependency tests phù hợp.

**Câu 11.** `mvn test` tại reactor root có bảo đảm tạo `-tests.jar` không?

**Đáp án:** Không. `jar:test-jar` mặc định bind phase `package`; chỉ chạy tới test có thể chưa attach JAR.

**Câu 12.** Vì sao `mvn clean verify` phù hợp cho lab?

**Đáp án:** Nó đưa producer qua `package` trước khi consumer cần test JAR và chạy các unit tests của hai modules.

**Câu 13.** Main class `GreetingApp` in ra gì khi chạy với đúng classpath?

**Đáp án:** Chính xác một dòng `Hello, Application!`.

**Câu 14.** Tên classifier `client` có tự lọc package API không?

**Đáp án:** Không. Nội dung phụ thuộc `includes/excludes` và cấu hình plugin, classifier chỉ là định danh biến thể.

**Câu 15.** Nếu một script tạo `target/custom.jar`, Maven deploy có tự lấy file đó không?

**Đáp án:** Không bảo đảm. Cần plugin attach artifact vào Maven project hoặc cơ chế publication tương đương.

**Câu 16.** Một file JSON có thể attach bằng classifier không?

**Đáp án:** Có, ví dụ Build Helper Maven Plugin `attach-artifact` với `<type>json</type>` và `<classifier>schema</classifier>`, miễn là file đã được tạo trước khi attach.

**Câu 17.** `sources.jar` và `tests.jar` khác nhau thế nào?

**Đáp án:** Sources JAR thường chứa nguồn Java; test JAR chứa compiled test classes/resources theo goal `jar:test-jar`.

**Câu 18.** Classifier có nằm bắt buộc trong `MANIFEST.MF` không?

**Đáp án:** Không. Nó là metadata artifact coordinates của Maven, không phải manifest attribute chuẩn bắt buộc.

**Câu 19.** `-DskipTests` có nhất thiết ngừng tạo test JAR không?

**Đáp án:** Không. Skip test execution thường vẫn compile test classes; `jar:test-jar` có thể tiếp tục đóng gói chúng nếu tới package.

**Câu 20.** Có nên publish test JAR chứa credentials thật trong test resources không?

**Đáp án:** Không. Test JAR có thể được install/deploy và tải về từ repository, nên fixtures phải sạch dữ liệu nhạy cảm.

**Câu 21.** Khi reusable test helper dùng nhiều thư viện test-scope và có nhiều consumer, nên cân nhắc giải pháp gì?

**Đáp án:** Tạo module/library `test-support` riêng với source ở `src/main/java` và khai báo dependencies cần thiết một cách rõ ràng.

## 21. Tài liệu chính thức để đối chiếu

- [Apache Maven JAR Plugin 3.4.2 – jar:test-jar](https://maven.apache.org/plugins-archives/maven-jar-plugin-3.4.2/test-jar-mojo.html): goal tạo JAR test classes; default phase `package`, classifier `tests`, thư mục đầu vào.
- [Apache Maven JAR Plugin 3.4.2 – Create Test JAR](https://maven.apache.org/plugins-archives/maven-jar-plugin-3.4.2/examples/create-test-jar.html): cấu hình execution, dependency type/test classifier và giới hạn test-scoped transitivity.
- [Apache Maven JAR Plugin – Additional Attached JAR](https://maven.apache.org/plugins/maven-jar-plugin/examples/attached-jar.html): execution phụ, `classifier` và `includes/excludes`.
- [Apache Maven – Guide to Using Attached Tests](https://maven.apache.org/guides/mini/guide-attached-tests.html): tái sử dụng test JAR và `dependenciesToScan`.
- [Apache Maven – Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): scope, type và classifier trong dependencies.
- [Apache Maven – Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): `test-compile`, `test`, `package`, `install` và `deploy`.
- [MojoHaus Build Helper – attach-artifact](https://www.mojohaus.org/build-helper-maven-plugin/attach-artifact-mojo.html): attach artifact khác vào Maven project.
- [MojoHaus Build Helper – Usage](https://www.mojohaus.org/build-helper-maven-plugin/usage.html): cấu hình artifact `file`, `type`, `classifier`.
- [Apache Maven Source Plugin – Introduction](https://maven.apache.org/plugins/maven-source-plugin/): tạo và attach source JAR.
- [Apache Maven JAR Plugin – Manifest Customization](https://maven.apache.org/plugins/maven-jar-plugin/examples/manifest-customization.html): cấu hình JAR manifest, độc lập với artifact classifier.
