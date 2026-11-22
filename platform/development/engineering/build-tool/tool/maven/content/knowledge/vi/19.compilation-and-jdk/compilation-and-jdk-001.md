# Maven Compiler Plugin và các goal compile, testCompile

## 1. Hai goal làm hai việc khác nhau trong cùng một vòng đời Maven

Khi học Java với Maven, bạn thường dùng những lệnh như `mvn compile`, `mvn test` hoặc `mvn package`. Đằng sau các phase này, **Maven Compiler Plugin** thực hiện phần việc chuyển mã nguồn Java thành bytecode `.class`. Plugin có nhiều goal, nhưng hai goal cơ bản cần hiểu thật rõ là:

- **`compiler:compile`:** biên dịch **mã nguồn chính** của ứng dụng/thư viện.
- **`compiler:testCompile`:** biên dịch **mã nguồn kiểm thử** của dự án, có thể tham chiếu các class chính đã được biên dịch và những dependency chỉ dùng cho test.

Hai goal được Maven liên kết với **hai lifecycle phase khác nhau**: `compile` và `test-compile`. **`testCompile` chỉ biên dịch test; nó không tự chạy các test.** Để thực thi JUnit tests trong lifecycle `test`, Maven thường dùng **Maven Surefire Plugin**; integration tests thường do Failsafe Plugin đảm nhiệm khi được cấu hình.

Điều cần học không chỉ là tên goal mà còn là **nguồn vào, thư mục đầu ra, classpath, thứ tự chạy, cách cấu hình JDK/release**, và những khác biệt giữa cách gọi goal trực tiếp với cách gọi lifecycle phase. Các ví dụ dưới đây dùng Maven 3.9.x, Maven Compiler Plugin **3.13.0**, JDK **17+** và JUnit 5. Phiên bản plugin được ghim rõ để tránh một ví dụ thay đổi hành vi theo mặc định của từng môi trường.

### Mục tiêu của bài

Sau khi học, bạn có thể:
1. Chỉ ra sự khác biệt giữa `compile`, `test-compile` và `test` trong Maven lifecycle.
2. Phân biệt `compiler:compile` và `compiler:testCompile` theo source roots, classpath và output.
3. Biết chỗ nào khai báo `maven.compiler.release`, `testRelease`, version Compiler Plugin và test dependency.
4. Tạo một Maven project Java 17 có mã nguồn chính + JUnit 5 test, chạy từng phase rồi tự đối chiếu class files.
5. Hiểu vì sao `-DskipTests` khác `-Dmaven.test.skip=true`.
6. Chẩn đoán lỗi compiler/JDK, package, missing test dependency và khác biệt giữa chạy goal trực tiếp với lifecycle.

## 2. Plugin, goal và phase: không phải những tên gọi thay thế cho nhau

### 2.1. Plugin là một artifact, goal là một tác vụ

Plugin được phân phối dưới tọa độ Maven:

```text
org.apache.maven.plugins:maven-compiler-plugin:3.13.0
```

Trong đó:
- `groupId` = `org.apache.maven.plugins`;
- `artifactId` = `maven-compiler-plugin`;
- `version` = `3.13.0`.

Goal có tên không gian của plugin, ví dụ `compiler:compile` hoặc `compiler:testCompile`. Khi cần kiểm soát tuyệt đối phiên bản plugin, có thể gọi với tọa độ đầy đủ:

```bash
mvn org.apache.maven.plugins:maven-compiler-plugin:3.13.0:compile
mvn org.apache.maven.plugins:maven-compiler-plugin:3.13.0:testCompile
```

Đây là **gọi trực tiếp từng goal**, không phải yêu cầu Maven thực hiện toàn bộ vòng đời đến một phase.

### 2.2. Phase là mốc trong Maven lifecycle

`compile` là **phase** của default lifecycle; `compiler:compile` là **goal**. Phase quyết định Maven sẽ chạy những goal được gắn vào nó, sau khi chạy các phase đứng trước. Với dự án `packaging=jar` thông thường:

```text
Maven default lifecycle (phần liên quan)
    validate
       |
    generate-sources
       |
    process-sources / generate-resources / process-resources
       |
    compile                 -> compiler:compile
       |
    process-classes / generate-test-sources / process-test-sources
       |
    generate-test-resources / process-test-resources
       |
    test-compile            -> compiler:testCompile
       |
    test                    -> surefire:test
       |
    package                 -> jar:jar
       |
    verify / install / deploy
```

Đây là **sơ đồ các mốc**, không liệt kê tất cả phase trung gian. Mapping goal phụ thuộc packaging, POM executions và plugin versions; ví dụ thể hiện mapping thông dụng cho Maven 3 với `packaging=jar`.

Bởi vậy:
- `mvn compile`: chạy các phase từ đầu default lifecycle đến `compile`, gồm goal compiler tương ứng.
- `mvn test-compile`: chạy đến `test-compile`, tức **có biên dịch mã chính trước, rồi biên dịch mã test**, nhưng chưa đến phase `test`.
- `mvn test`: chạy đến `test`, **biên dịch cả hai nhóm rồi chạy test** khi Surefire được gắn và có test thích hợp.
- `mvn package`: chạy đến `package`, bao gồm test theo lifecycle thông dụng, rồi tạo artifact.
- `mvn compiler:testCompile`: gọi goal trực tiếp, **không tự đảm bảo** các phase `process-resources`, `compile` hay `process-test-resources` đã chạy. Với build phức tạp, nên dùng `mvn test-compile` để có trạng thái đầu vào đúng.

**Lưu ý tên:** phase là `test-compile` có dấu gạch nối và chữ thường; goal là `testCompile` với chữ C viết hoa. Hai chuỗi **không đồng nhất**.

## 3. Bảng so sánh chính xác compile và testCompile

| Tiêu chí | `compiler:compile` | `compiler:testCompile` |
| --- | --- | --- |
| Vai trò | Biên dịch ứng dụng/thư viện | Biên dịch mã kiểm thử |
| Phase mặc định | `compile` | `test-compile` |
| Source root mặc định | `src/main/java` | `src/test/java` |
| Property nội bộ về source roots | `project.compileSourceRoots` | `project.testCompileSourceRoots` |
| Output bytecode mặc định | `target/classes` | `target/test-classes` |
| Metadata output directory | `project.build.outputDirectory` | `project.build.testOutputDirectory` |
| Scope dependency cần phân giải | **compile** | **test** |
| Thấy dependency `test`? | Không trên main compile classpath | Có trên test compile classpath |
| Thấy compiled main classes? | Tự tạo | Có thể tham chiếu qua test compile classpath |
| Có thực thi JUnit test? | Không | **Không** |
| Có đưa test classes vào JAR chính mặc định? | Không áp dụng; class chính được đóng gói | **Không**, test classes tách riêng |
| Yêu cầu Maven project? | Có | Có |
| Thread-safe theo plugin descriptor | Có | Có |

**Hai điểm mấu chốt:**

1. **`compile` không được phép dựa vào thư viện khai báo `scope=test`.** Nếu bạn import JUnit trong `src/main/java` nhưng chỉ khai báo JUnit là test dependency, main compilation sẽ báo không tìm thấy package/class.
2. **`testCompile` thường dựa vào các class do `compile` tạo trước đó** và dùng classpath cho test, bao gồm JUnit hay Mockito khi các thư viện ấy được khai báo test scope. Vì vậy test source có thể gọi public API của class chính mà không cần sao chép code.

Thông tin về goal requirements được ghi rõ trong tài liệu Maven Compiler Plugin 3.13.0:
- `compiler:compile` yêu cầu dependency resolution scope `compile`.
- `compiler:testCompile` yêu cầu dependency resolution scope `test`.

Đây là **scope mà goal yêu cầu để phân giải project dependencies**, không có nghĩa bản thân Compiler Plugin trở thành một compile/test dependency của ứng dụng. Plugin dependencies và project dependencies là hai graph khác nhau.

## 4. Maven thực sự tìm mã Java ở đâu?

### 4.1. Layout chuẩn, không cần cấu hình source roots thủ công

Với một dự án JAR Maven thông thường:

```text
my-project/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/       <-- source code ứng dụng
│   │   └── resources/  <-- resources ứng dụng
│   └── test/
│       ├── java/       <-- source code test
│       └── resources/  <-- resources dành cho test
└── target/
    ├── classes/       <-- output compile của main
    ├── test-classes/  <-- output testCompile
    └── surefire-reports/  <-- báo cáo sau khi test chạy
```

Những thư mục `target` chỉ xuất hiện sau các bước build tương ứng (và có thể không tồn tại khi mới tạo project). `src/main/resources` do **Maven Resources Plugin** xử lý ở phase `process-resources`; `src/test/resources` được xử lý ở `process-test-resources`. Compiler Plugin không phải plugin chịu trách nhiệm copy resources.

Nếu muốn dùng layout không chuẩn, có thể cấu hình `<build><sourceDirectory>` và `<testSourceDirectory>`, nhưng với người mới học nên giữ mặc định: cấu hình tùy biến source roots dễ gây vấn đề khi dùng IDE, plugin khác hoặc CI.

### 4.2. Class files có thể giữ lại giữa các lần build

Sau `mvn compile`, thường có:

```text
target/classes/com/example/demo/App.class
```

Sau `mvn test-compile`, thường có thêm:

```text
target/test-classes/com/example/demo/AppTest.class
```

Nhưng nếu trước đó bạn đã chạy `mvn test` rồi chạy lại `mvn compile` mà không `clean`, thư mục `target/test-classes` **có thể vẫn còn từ lần trước**. **Sự tồn tại của file cũ không chứng minh lệnh mới vừa biên dịch test**. Khi kiểm tra hành vi từng phase, nên bắt đầu bằng `mvn clean ...`.

### 4.3. Test dependency không tự biến thành dependency sản xuất

POM:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>
```

Khai báo này nói JUnit Jupiter được dùng cho **test classpath**, không phải compile classpath của main hay runtime dependency mặc định của JAR sản phẩm.

Nếu cùng library được khai báo `compile` thì cả application compile classpath cũng có thể nhìn thấy nó; nhưng đó không phải cách khuyến nghị đối với một test framework chỉ dùng trong `src/test/java`.

Maven Plugin có thể có dependency riêng và classloader riêng; đừng nhầm việc JUnit được testCompile nhìn thấy với việc Surefire plugin “trở thành dependency của app”. JUnit được khai báo trong **project dependencies**, còn Surefire là **build plugin**.

## 5. Cấu hình Java version: release, source, target và JDK

### 5.1. Ưu tiên `maven.compiler.release`

Khi dùng JDK 9+, javac hỗ trợ `--release N` để áp dụng đồng thời:
- quy tắc ngôn ngữ phù hợp với Java release N;
- version class file tương ứng;
- tập **Java SE API** công khai của release N.

Cấu hình POM gọn:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Với Maven Compiler Plugin 3.13.0 và JDK 17+, cách này là lựa chọn rõ ràng cho cả main source và cấu hình mặc định của test khi không override riêng.

Bạn cũng có thể cấu hình trực tiếp trong plugin:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
    </configuration>
</plugin>
```

Đây là **đoạn plugin bên trong `<build><plugins>`**, không phải POM hoàn chỉnh. Ví dụ runnable ở mục 8 sẽ dùng **property** và chỉ ghi plugin version một lần; không cố ý khai báo hai giá trị release mâu thuẫn nhau.

### 5.2. Tại sao chỉ source/target có thể chưa đủ?

Hai thuộc tính cũ:

```xml
<properties>
    <maven.compiler.source>17</maven.compiler.source>
    <maven.compiler.target>17</maven.compiler.target>
</properties>
```

có ý nghĩa:
- `source`: điều khiển phiên bản cú pháp Java được chấp nhận.
- `target`: điều khiển version bytecode đầu ra.

Nhưng chỉ đặt source/target **không nhất thiết giới hạn việc bạn gọi API của JDK mới hơn**. Ví dụ nếu build trên JDK 21 mà muốn target 17, source/target 17 vẫn có nguy cơ sử dụng API chỉ có ở 21, dẫn đến lỗi runtime trên Java 17. `--release 17` giúp compiler kiểm tra API tương ứng Java 17.

Vì vậy với project Java hiện đại, **ưu tiên `release`** và test thực tế trên runtime được hỗ trợ. Không tự động thiết lập cả `release` và cặp `source/target` thành những giá trị mâu thuẫn, trừ trường hợp có yêu cầu riêng đã kiểm chứng.

### 5.3. JDK chạy Maven, JDK biên dịch và Java runtime

Lệnh:

```bash
mvn -version
java -version
javac -version
```

giúp phát hiện Maven đang dùng JDK nào và lệnh `java`/`javac` ở terminal trỏ về đâu. **Maven Compiler Plugin mặc định sử dụng compiler của JDK chạy Maven**, nhưng có thể dùng **Toolchains** hoặc tùy chọn compiler/fork để chuyển sang JDK khác.

Ví dụ bạn dùng `maven.compiler.release=17` nhưng `mvn -version` cho thấy Java 11: compiler Java 11 không thể target release 17 nếu không có toolchain/compiler khác hỗ trợ. Khi đó Maven có thể báo:

```text
error: release version 17 not supported
```

Thông điệp lỗi chính xác tùy JDK/plugin, nhưng nguyên nhân phổ biến là **JDK được chọn quá cũ so với release yêu cầu**. Cách xử lý: chọn JDK 17+ cho Maven hoặc cấu hình Toolchains để compiler dùng JDK phù hợp.

**Không hiểu `release=17` là “Maven tự tải JDK 17”.** Property này chỉ điều khiển target compilation, không cài đặt Java runtime hoặc thiết lập Java home.

### 5.4. Tùy chọn testRelease để cấu hình test riêng

Compiler Plugin có các tham số dành riêng cho test compilation:

| Parameter | User property liên quan | Ý nghĩa |
| --- | --- | --- |
| `release` | `maven.compiler.release` | Release chung/main compiler |
| `testRelease` | `maven.compiler.testRelease` | Override release dành cho test compiler |
| `source` | `maven.compiler.source` | Java source level chung |
| `target` | `maven.compiler.target` | Java bytecode target level chung |
| `testSource` | `maven.compiler.testSource` | Override source level cho test |
| `testTarget` | `maven.compiler.testTarget` | Override target level cho test |

Ví dụ **chỉ mang tính minh họa**, khi JDK/compiler hỗ trợ Java 21 và team thực sự muốn test code sử dụng cú pháp mới hơn main:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <maven.compiler.testRelease>21</maven.compiler.testRelease>
</properties>
```

Đoạn trên **không chạy được trên môi trường chỉ có JDK 17** nếu test yêu cầu release 21. Nó làm test bytecode có thể không chạy trên runtime Java 17; nếu dùng, phải thiết kế test JVM/toolchain tương ứng. Ví dụ runnable ở mục 8 **không thiết lập testRelease riêng**, giữ cả main/test trên JDK 17 cho đơn giản và ổn định.

### 5.5. Không phụ thuộc vào default source/target không chủ đích

Compiler Plugin 3.13.0 có default `source` và `target` là `1.8` khi không được cấu hình. Điều đó có thể làm một người dùng JDK 17 tưởng mình biên dịch Java 17 nhưng compiler đang hạn chế ngôn ngữ/bytecode theo Java 8. Hãy **khai báo target release tường minh** theo dự án, nhất là CI.

Nếu dự án đang dùng Maven Compiler Plugin 4.x (dòng mới cho Maven 4), cần đọc lại docs của đúng phiên bản: cấu hình và cơ chế source roots mới có thể khác. Ví dụ này cố ý ghim dòng 3.x.

## 6. Hiểu classpath của main và test

### 6.1. Compile classpath

`compiler:compile` yêu cầu Maven phân giải project dependencies ở scope `compile`. Trong mô hình thông dụng, main compilation được cung cấp JDK và các dependencies thích hợp cho compile classpath (ví dụ dependencies `compile` và `provided` theo quy tắc Maven).

Main source không được nhìn thấy thư viện **chỉ ở scope test**. Nếu file `src/main/java/com/example/Foo.java` viết:

```java
import org.junit.jupiter.api.Test;
```

mà JUnit chỉ được khai báo `scope=test`, Maven có thể báo:

```text
package org.junit.jupiter.api does not exist
```

Đó không phải vì Compiler Plugin lỗi, mà vì bạn dùng thư viện test-only sai vị trí. Hãy đặt `@Test` và test assertions vào `src/test/java`.

### 6.2. Test compile classpath

`compiler:testCompile` yêu cầu dependency resolution scope `test`. Nó cần:
- class đã compile từ `src/main/java`;
- dependency cần thiết để compile test, như JUnit Jupiter API;
- các thư viện khác theo scope mà Maven cho phép trong test classpath.

Vì vậy test có thể viết `import com.example.compilerlab.Calculator;` và `import org.junit.jupiter.api.Test;`. Nếu bỏ JUnit dependency, file test vẫn nằm đúng `src/test/java` nhưng compilation thất bại vì thiếu symbol `Test`/`Assertions`.

### 6.3. Test biên dịch và test chạy ở hai giai đoạn khác nhau

Thứ tự quan sát:

```text
mvn clean compile
  -> compile source chính
  -> target/classes/Calculator.class

mvn clean test-compile
  -> compile source chính
  -> compile source test
  -> target/classes/Calculator.class
  -> target/test-classes/CalculatorTest.class
  -> chưa chạy test

mvn clean test
  -> compile source chính
  -> compile source test
  -> Surefire thực thi test
  -> target/surefire-reports/...
```

`target/test-classes` chứa **bytecode test**, không phải bằng chứng test đã PASS. Tương tự, `BUILD SUCCESS` sau `mvn test-compile` chỉ cho biết test source đã compile, chưa cho biết logic test đúng.

### 6.4. Test class không tự nằm trong JAR chính

`mvn package` với `packaging=jar` tạo JAR chính từ main build output. Nó **không mặc định nhét `target/test-classes` vào JAR sản phẩm**. Nếu cần phát hành test utilities riêng, Maven có cơ chế test JAR chuyên biệt, nhưng không phải mục tiêu của hai compiler goals.

Điều này giữ ranh giới giữa code phát hành và test framework/dependencies. Một ứng dụng không nên phụ thuộc vào class test chỉ vô tình xuất hiện ở local target folder.

## 7. Gọi goal trực tiếp hay chạy phase: trường hợp nào phù hợp?

### 7.1. Lifecycle là cách thông thường

Đối với build hàng ngày, dùng các phase:

```bash
mvn clean compile
mvn clean test-compile
mvn clean test
mvn clean verify
```

- `clean` thuộc clean lifecycle, xóa output build cũ; các phase theo sau thuộc default lifecycle.
- `compile` chạy cả các bước cần thiết trước main compilation theo lifecycle.
- `test-compile` chạy thêm test resource processing và test compilation.
- `test` chạy thêm test execution khi plugin phù hợp được cấu hình/gắn mặc định.
- `verify` thường dành để chạy các kiểm tra chất lượng liên quan và xác nhận gói build.

Không gọi nhiều phase liên tiếp như `mvn compile test-compile test` trừ khi hiểu vì sao cần: Maven đã tự chạy các phase trước khi bạn gọi một phase sau, nên thường chỉ cần `mvn test`.

### 7.2. Gọi goal trực tiếp hữu ích khi debug

Ví dụ:

```bash
mvn org.apache.maven.plugins:maven-compiler-plugin:3.13.0:compile
mvn org.apache.maven.plugins:maven-compiler-plugin:3.13.0:testCompile
```

Điều này buộc chạy goal cụ thể, hữu ích để chẩn đoán compiler parameters/goal descriptor. Nhưng:
- gọi trực tiếp `testCompile` **không có nghĩa Maven tự chạy trước `compile`**;
- generated source hoặc filtered resources từ các phase trước có thể chưa tồn tại;
- output có thể dựa vào trạng thái đã có trong `target` từ lần build trước.

Vì vậy nếu build từ sạch, hãy dùng `mvn clean test-compile` để kiểm tra toàn bộ pipeline đến test compilation. Nếu bạn chỉ muốn riêng goal testCompile sau khi đã chạy `mvn compile`, có thể dùng goal trực tiếp và hiểu rõ các đầu vào sẵn có.

### 7.3. Cách đọc metadata chính thức của hai goal

Dùng Maven Help Plugin:

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe "-Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.13.0" -Dgoal=compile -Ddetail=true
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe "-Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.13.0" -Dgoal=testCompile -Ddetail=true
```

Với `compile`, tìm default phase `compile`, resolution scope `compile` và outputDirectory theo `project.build.outputDirectory`. Với `testCompile`, tìm default phase `test-compile`, resolution scope `test` và outputDirectory theo `project.build.testOutputDirectory`.

**Help Plugin chỉ mô tả goal, không chạy goal được mô tả.** Đừng coi một dòng “goal is thread-safe” là chứng nhận tất cả plugin trong build đều an toàn khi chạy reactor song song.

## 8. Ví dụ chạy được: Maven 3.9 + Java 17 + JUnit 5

Bộ ví dụ này cố tình nhỏ để bạn kiểm tra **hai thư mục source**, **hai output directories**, các phase và hành vi chạy test. Dự án gồm một class chính và một JUnit 5 test class. Mọi tệp cần thiết đều được nêu đầy đủ.

### 8.1. Cấu trúc thư mục

```text
compiler-lab/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── com/example/compilerlab/Calculator.java
    └── test/
        └── java/
            └── com/example/compilerlab/CalculatorTest.java
```

Yêu cầu môi trường: Maven 3.9.x, JDK 17+, kết nối repository để tải plugin/JUnit ở lần chạy đầu. Nếu dự án dùng Maven Wrapper, thay `mvn` bằng `./mvnw` hoặc `mvnw.cmd` tùy môi trường.

### 8.2. Tệp `pom.xml` đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>compiler-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <junit.version>5.11.4</junit.version>
    </properties>

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
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Phân tích POM:

1. `packaging=jar` sử dụng Maven default lifecycle mapping để compile, testCompile, test và đóng gói.
2. `maven.compiler.release=17` quy định Java release mục tiêu cho compilation thông thường, tránh phụ thuộc default `source/target`.
3. `junit-jupiter:5.11.4` chỉ có `scope=test`: class Calculator không phụ thuộc JUnit, còn CalculatorTest có thể import JUnit.
4. `maven-compiler-plugin:3.13.0` được ghim version. **Không cần tự thêm `<execution>` để gắn compile/testCompile vào lifecycle JAR mặc định**.
5. `maven-surefire-plugin:3.5.2` được ghim để chạy các JUnit 5 tests khi đến phase `test`. Surefire là plugin khác với compiler; đừng gán việc chạy test cho goal testCompile.

### 8.3. Tệp `src/main/java/com/example/compilerlab/Calculator.java`

```java
package com.example.compilerlab;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int left, int right) {
        return left + right;
    }

    public static void main(String[] args) {
        System.out.println("2 + 3 = " + add(2, 3));
    }
}
```

Đây là **class Java hoàn chỉnh** có `main(String[] args)`. Sau compiler:compile, bytecode class nằm tại `target/classes/com/example/compilerlab/Calculator.class` theo layout mặc định.

### 8.4. Tệp `src/test/java/com/example/compilerlab/CalculatorTest.java`

```java
package com.example.compilerlab;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

final class CalculatorTest {
    @Test
    void addsPositiveNumbers() {
        assertEquals(5, Calculator.add(2, 3));
    }

    @Test
    void supportsNegativeNumbers() {
        assertEquals(1, Calculator.add(4, -3));
    }
}
```

Test class này:
- nằm ở `src/test/java` để `compiler:testCompile` biên dịch;
- dùng JUnit Jupiter `@Test` và `assertEquals` từ dependency test scope;
- gọi `Calculator.add` từ mã chính;
- có hai test methods độc lập, đều đúng với implementation `add`;
- tên `CalculatorTest` khớp mẫu kiểm thử thông dụng của Surefire; JUnit Jupiter có thể chạy các test methods package-private.

Không có method `main()` trong CalculatorTest vì test runner điều khiển việc gọi `@Test`. **JUnit `@Test` là metadata để chạy test, không phải lệnh Java tự thực thi khi biên dịch.**

### 8.5. Bước 1: kiểm tra JDK và Maven

Mở terminal trong thư mục `compiler-lab`:

```bash
mvn -version
java -version
javac -version
```

Cần Java 17+ để Compiler Plugin có thể tạo mã `--release 17`, trừ khi bạn chủ động dùng toolchain khác phù hợp. Nếu terminal dùng JDK 11, hãy chỉnh JDK chạy Maven hoặc toolchain trước khi kết luận POM có lỗi.

### 8.6. Bước 2: chỉ biên dịch mã chính

```bash
mvn clean compile
```

Sau khi `BUILD SUCCESS`, kỳ vọng có:

```text
target/classes/com/example/compilerlab/Calculator.class
```

Sau một lần `clean` thành công, `target/test-classes/com/example/compilerlab/CalculatorTest.class` **chưa được compiler:testCompile tạo ra**, vì lifecycle mới đến `compile`. Đây là cách trực tiếp quan sát ranh giới của goal `compiler:compile`.

Chạy chương trình đã biên dịch:

```bash
java -cp target/classes com.example.compilerlab.Calculator
```

Stdout **chính xác của lệnh Java cuối**:

```text
2 + 3 = 5
```

Không lấy Maven build log làm stdout cố định; log có thể thay đổi theo Maven/JDK/repository/cache.

### 8.7. Bước 3: biên dịch test, chưa chạy test

```bash
mvn clean test-compile
```

Sau khi thành công, có cả hai class files:

```text
target/classes/com/example/compilerlab/Calculator.class
target/test-classes/com/example/compilerlab/CalculatorTest.class
```

Lệnh `test-compile` chạy các phase trước, trong đó có `compiler:compile`, rồi đến `compiler:testCompile`. Nó cần test dependency JUnit để compile `CalculatorTest.java`.

**Nhưng hai test methods chưa được Surefire gọi**, vì lifecycle chưa đến phase `test`. Không diễn giải `BUILD SUCCESS` tại đây thành “2 tests passed”; nó chỉ xác nhận compilation và các phase trước đã thành công.

### 8.8. Bước 4: chạy unit tests

```bash
mvn clean test
```

Lệnh chạy đủ main compilation, test compilation và **Surefire execution** ở phase `test`. Với project mẫu này, kỳ vọng Surefire tìm được **2 tests**, cả hai thành công. Report thường nằm ở:

```text
target/surefire-reports/
```

Mẫu thông tin test report về số lượng (không phải toàn bộ Maven stdout chính xác):

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
```

Tùy version và chế độ hiển thị, console log có thể in thêm class name, plugin version, thời gian và thông tin môi trường. Nếu build fail ở đây, cần phân biệt **lỗi Java compilation**, **lỗi thiếu test dependency** và **assertion failure khi Surefire chạy**.

### 8.9. Bước 5: package JAR và chạy main class

```bash
mvn clean package
```

Sau thành công, JAR chính thông thường nằm ở:

```text
target/compiler-lab-1.0.0.jar
```

Do demo không có runtime dependencies ngoài JDK, có thể dùng:

```bash
java -cp target/compiler-lab-1.0.0.jar com.example.compilerlab.Calculator
```

Stdout:

```text
2 + 3 = 5
```

**Không nhầm `java -cp jar mainClass` với `java -jar jar`.** Ví dụ chưa khai báo `Main-Class` trong manifest, nên `java -jar target/compiler-lab-1.0.0.jar` có thể báo không có main manifest attribute; đó không phải lỗi compiler:compile hay compiler:testCompile.

**JUnit test class mặc định không được đóng vào JAR chính.** Để kiểm tra nội dung JAR có thể dùng:

```bash
jar tf target/compiler-lab-1.0.0.jar
```

Bạn sẽ thấy class chính, metadata và manifest nhưng không kỳ vọng thấy `CalculatorTest.class`. Nếu muốn JAR có thể chạy bằng `java -jar`, cần cấu hình jar plugin/manifest riêng, ngoài phạm vi Compiler Plugin.

## 9. Khi skip tests: hai cờ hoàn toàn khác nhau

Nhiều người nhầm `-DskipTests` với `-Dmaven.test.skip=true`. Hai cờ này gây hành vi khác nhau trong lifecycle thông dụng:

### 9.1. `-DskipTests`: không chạy test, vẫn có thể compile test

```bash
mvn -DskipTests clean package
```

Với cấu hình mẫu và Surefire 3.5.2:
- `compiler:compile` vẫn biên dịch main source.
- `compiler:testCompile` vẫn biên dịch test source.
- Surefire **bỏ qua việc chạy** các test.
- JAR sản phẩm vẫn được đóng gói.

Vì vậy sau một lần `clean` thành công, bạn vẫn có thể thấy `CalculatorTest.class` trong `target/test-classes`, nhưng không có bằng chứng hai assertions đã được thực thi ở lần build này.

### 9.2. `-Dmaven.test.skip=true`: bỏ qua cả biên dịch test

```bash
mvn -Dmaven.test.skip=true clean package
```

Property `maven.test.skip` được **Maven Compiler Plugin, Surefire và Failsafe** công nhận theo tài liệu Maven. Trong ví dụ:
- main code vẫn được compile;
- **test compilation được bỏ qua**;
- test execution cũng không diễn ra;
- sau `clean`, `CalculatorTest.class` thường không được tạo trong `target/test-classes`.

Vì thế hai cờ không tương đương. `-Dmaven.test.skip=true` có thể che khuất lỗi compile trong test sources; chỉ dùng khi bạn chủ động chấp nhận bỏ qua việc kiểm tra code test.

### 9.3. Bảng quyết định

| Lệnh | Compile main | Compile test | Chạy test |
| --- | --- | --- | --- |
| `mvn clean compile` | Có | Không | Không |
| `mvn clean test-compile` | Có | Có | Không |
| `mvn clean test` | Có | Có | Có |
| `mvn -DskipTests clean package` | Có | Có | Không |
| `mvn -Dmaven.test.skip=true clean package` | Có | Không | Không |

Bảng áp dụng cho **Maven 3 project JAR thông thường** với compiler/Surefire mặc định như ví dụ. Nếu POM có plugin executions tùy biến hoặc các plugin khác cùng thực hiện test, cần kiểm tra effective POM để xác định tất cả các bước thật sự bị skip.

## 10. Compiler configuration và những trường hợp nâng cao

### 10.1. Cấu hình chung và cấu hình riêng cho execution

Khi cần thiết, bạn có thể cấu hình plugin một lần:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
                <showWarnings>true</showWarnings>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Đây là **đoạn POM minh họa**, không phải tệp độc lập. Nó áp dụng cấu hình cấp plugin tới những goal/executions phù hợp. `showWarnings` có tác dụng hiển thị compiler warnings, không tự biến warnings thành lỗi nếu chưa bật cơ chế fail-on-warning phù hợp.

Nếu cần main/test khác nhau, Compiler Plugin cho phép một số tham số `test...` như `testRelease` hoặc `testSource`, và `<configuration>` riêng theo execution. Nhưng **không cần tự thêm hai executions cho compile và testCompile** ở project JAR mặc định: lifecycle đã có bindings, thêm executions không đúng có thể khiến goal chạy lặp.

### 10.2. Annotation processing không phải Surefire

Maven Compiler Plugin có thể gọi annotation processors trong quá trình compile/testCompile, ví dụ các framework generate Java sources. Nhưng annotation processing:
- diễn ra trong **compilation**, không phải test execution;
- có cấu hình `annotationProcessorPaths` và các tham số liên quan;
- có thể tạo generated sources; không nên chép thủ công các file sinh ra vào `src/main/java` rồi sửa trực tiếp;
- phụ thuộc JDK/plugin version và chính sách processor discovery.

Khi gặp `cannot find symbol` cho một class dự kiến được annotation processor tạo, ngoài dependencies hãy kiểm tra compiler annotation processing, generated-sources output, JDK version và module path. Một JDK mới có thể thay đổi default discovery/processing; nên cấu hình processor rõ ràng theo plugin docs.

### 10.3. Modular Java và module path

Với Java 9+, nếu dự án có `module-info.java`, Compiler Plugin có thể dùng **module path** thay cho classpath tùy điều kiện/configuration. Đó là một lớp phức tạp khác với việc chỉ phân biệt main/test goals. JUnit test compilation cho Java modules có thể yêu cầu cấu hình module patching/opens tùy trường hợp.

Bộ ví dụ ở mục 8 **không có `module-info.java`**, nên giữ bố cục Java cổ điển với classpath. Khi nâng lên JPMS, kiểm tra tài liệu Compiler/Surefire của đúng phiên bản thay vì mặc định ví dụ classpath áp dụng nguyên xi.

### 10.4. Incremental compilation và lý do vẫn cần clean khi nghi ngờ

Compiler Plugin 3.13.0 có cấu hình incremental compilation. Nó có thể dựa vào sự thay đổi của source/dependencies để quyết định compile lại. Điều này giúp build nhanh hơn nhưng gây khó hiểu khi bạn sửa cấu hình:
- class files còn trong `target` có thể là của lần build trước;
- dependency classpath thay đổi có thể khiến compiler quyết định compile lại;
- chỉ nhìn file tồn tại chưa chứng minh nguồn nào đã compile ở lần gọi hiện tại.

Khi chẩn đoán lỗi có tính lặp lại, chạy `mvn clean test-compile` hoặc `mvn clean test` để có trạng thái sạch. Không khuyến nghị tắt incremental compilation bừa bãi vì có nguy cơ để lại class references không đồng bộ khi source thay đổi.

### 10.5. Compiler Plugin và plugin khác: ranh giới trách nhiệm

| Nhiệm vụ | Plugin/goal thường đảm nhận | Không phải nhiệm vụ mặc định của Compiler Plugin |
| --- | --- | --- |
| Copy/filter main resources | Resources Plugin: `resources:resources` | Không |
| Copy/filter test resources | Resources Plugin: `resources:testResources` | Không |
| Compile main Java | Compiler Plugin: `compiler:compile` | Có |
| Compile test Java | Compiler Plugin: `compiler:testCompile` | Có |
| Chạy unit tests | Surefire Plugin: `surefire:test` | Không |
| Chạy integration tests | Failsafe Plugin (nếu được cấu hình) | Không |
| Tạo JAR | JAR Plugin: `jar:jar` | Không |
| Kiểm tra quality gates hoặc deploy | Các plugin tương ứng | Không |

**Không dùng `compiler:testCompile` như một cách chạy integration tests.** Goal này chỉ biên dịch Java test source. Integration test lifecycle, process startup/cleanup, Failsafe và verify là những cơ chế khác cần cấu hình riêng.

## 11. Lỗi thường gặp và hướng chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `release version 17 not supported` | Compiler/JDK quá cũ | Xem `mvn -version`, toolchain |
| `invalid target release: 17` | JDK biên dịch không hỗ trợ target | Chọn JDK 17+ hoặc toolchain phù hợp |
| `Source option 5 is no longer supported` | Plugin/default source level quá cũ hoặc chưa cấu hình | Ghim Compiler Plugin, đặt `maven.compiler.release` |
| `package org.junit.jupiter.api does not exist` ở `src/test/java` | Thiếu JUnit hoặc scope/dependency resolution sai | Kiểm tra JUnit test dependency và `dependency:tree` |
| Cùng lỗi JUnit nhưng ở `src/main/java` | Import JUnit test API sai thư mục | Đưa code test về `src/test/java` |
| `cannot find symbol Calculator` trong test | Chưa compile main, sai package/path, main compile fail | Dùng `mvn clean test-compile` và kiểm tra target/classes |
| `mvn test-compile` báo BUILD SUCCESS nhưng assertion sai vẫn chưa phát hiện | Test chưa chạy | Dùng `mvn test` |
| Surefire báo `Tests run: 0` dù có Java test class | Tên file/test discovery/JUnit engine sai, hoặc skip | Kiểm tra tên `*Test`, JUnit version, Surefire |
| `-DskipTests` nhưng `CalculatorTest.class` vẫn tồn tại | Đúng: chỉ bỏ chạy test | Dùng `-Dmaven.test.skip=true` nếu thật sự muốn bỏ cả test compilation |
| Compiler goal trực tiếp không thấy resource | Chưa chạy lifecycle phase tạo resource | Dùng `mvn compile` hoặc `mvn test-compile` |
| Class mới không xuất hiện sau chạy Maven | Source ở sai root, exclude filter, stale state | Kiểm tra path, `-X` khi cần, chạy clean |
| `java -jar` báo thiếu Main-Class | JAR chưa cấu hình manifest | Dùng `java -cp ... mainClass` hoặc cấu hình Jar Plugin |
| Java chạy class cũ dù source đã sửa | Đang dùng classpath/target sai hoặc artifact cũ | Clean, kiểm tra đúng module và path |
| Lỗi `UnsupportedClassVersionError` khi chạy | Runtime Java cũ hơn bytecode đã compile | Xem runtime `java -version`, `javap -verbose` |
| Main compile dùng dependency test | Khai báo source/dependency sai scope | Tách mã và thư viện theo main/test |
| `testCompile` dùng phiên bản JDK khác kỳ vọng | Maven Toolchains, fork/compilerId | Xem effective POM, toolchains, Maven log |
| Máy dev build được nhưng CI fail | Khác JDK, plugin version, profile, repository | Pin versions, so `mvn -version` và effective POM |

### 11.1. Quy trình kiểm tra theo thứ tự

1. **Xác định lệnh đang chạy:** `mvn compile`, `mvn test-compile`, `mvn test` hay gọi goal trực tiếp?
2. **Kiểm tra môi trường:** `mvn -version`, JDK/toolchain, `java -version` và `javac -version`.
3. **Kiểm tra POM hiệu lực:** dùng `mvn help:effective-pom` để xem Compiler Plugin version, `release`, source directories, plugin executions.
4. **Kiểm tra dependencies:** dùng `mvn dependency:tree` để xác nhận test libraries/versions có trong graph.
5. **Build sạch:** `mvn clean compile` hoặc `mvn clean test-compile`; tránh dùng bytecode cũ làm bằng chứng.
6. **Kiểm tra bytecode:** xác định file trong `target/classes` và `target/test-classes`, hoặc dùng `javap -verbose` để xem classfile major version (Java 17 là **61**).
7. **Chạy test thực sự:** `mvn test`; mở Surefire reports thay vì dựa vào việc test class đã biên dịch.
8. **Điều tra sâu khi cần:** dùng `-e` hoặc `-X`, đọc log/plugin descriptor đúng version và tránh chia sẻ token/credentials trong log.

### 11.2. Lệnh tự kiểm tra goal và compiler version

```bash
mvn -version
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe "-Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.13.0" -Dgoal=compile -Ddetail=true
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe "-Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.13.0" -Dgoal=testCompile -Ddetail=true
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Câu hỏi cần trả lời từ output:
- `compile` và `testCompile` có **default phase** nào?
- Khác nhau ở **requires dependency resolution scope** thế nào?
- OutputDirectory của từng goal được lấy từ Maven property nào?
- Có bất kỳ plugin execution nào làm goal chạy thêm một lần không?
- Version Compiler Plugin thực thi có đúng bản được mô tả không?

## 12. Bài tập tự đánh giá

**Bài 1 — dự đoán phase:** Dự án có `src/main/java` và `src/test/java`. Chạy `mvn clean compile` thì tạo bytecode của nhóm nào? Đáp án: **main**, không compile test trong lifecycle mặc định.

**Bài 2 — phân biệt biên dịch và chạy:** Chạy `mvn clean test-compile`; JUnit assertion sai nhưng Java test source vẫn hợp lệ. Lệnh có chắc fail không? **Không nhất thiết**; assertion chưa được gọi. Hãy chạy `mvn test` để thực thi test.

**Bài 3 — phạm vi dependencies:** Vì sao `src/test/java` có thể import JUnit nhưng `src/main/java` không thể, khi JUnit `scope=test`? Vì `compiler:testCompile` dùng **test classpath**, còn `compiler:compile` dùng **compile classpath**.

**Bài 4 — skip:** Lệnh nào thường vẫn biên dịch test nhưng không chạy chúng: `-DskipTests` hay `-Dmaven.test.skip=true`? Đáp án: **`-DskipTests`**.

**Bài 5 — source/target/release:** Nếu compile trên JDK 21 và phát hành cho Java 17, tại sao `--release 17` an toàn hơn chỉ `-source 17 -target 17`? Vì nó còn kiểm soát việc dùng **Java SE API của release 17**.

**Bài 6 — target cao hơn JDK:** Maven chạy với JDK 11 nhưng POM yêu cầu `release=17`. Có sửa được chỉ bằng đổi `maven.compiler.target=17` không? **Không**; cần compiler JDK 17+ (hoặc toolchain tương ứng).

**Bài 7 — bytecode:** Sau `mvn clean test-compile`, file main class mặc định ở đâu? **`target/classes`**. Test class? **`target/test-classes`**. Cả hai tự vào JAR chính? **Không**.

**Bài 8 — gọi goal:** `mvn compiler:testCompile` có mặc định chạy tất cả phase đến `test-compile` không? **Không**; đó là direct goal invocation. Dùng `mvn test-compile` nếu cần pipeline lifecycle đầy đủ.

**Bài 9 — test release riêng:** Vì sao `maven.compiler.testRelease=21` không phù hợp nếu toàn bộ CI chỉ có Java 17? Compiler không thể tạo test bytecode release 21, và test JVM Java 17 cũng không chạy được classfile Java 21.

**Bài 10 — thực hành:** Với mã ở mục 8, thay `assertEquals(5, Calculator.add(2, 3))` thành `assertEquals(6, Calculator.add(2, 3))` (chỉ trong bản thử nghiệm). So sánh kết quả `mvn clean test-compile` với `mvn test`, sau đó khôi phục assertion đúng. Bạn sẽ thấy **compile thành công không đồng nghĩa test logic đúng**.

## 13. Checklist trước khi đưa thay đổi compiler vào CI

- [ ] Có Compiler Plugin version ghim rõ trong POM hoặc parent/pluginManagement phù hợp.
- [ ] Java release mục tiêu được khai báo tường minh, ưu tiên `maven.compiler.release`.
- [ ] JDK/compiler và test JVM chạy CI phù hợp version bytecode được tạo.
- [ ] Source main và test nằm đúng `src/main/java`, `src/test/java` hoặc source roots được cấu hình có chủ đích.
- [ ] Test dependencies như JUnit có đúng `scope=test`.
- [ ] Hiểu `compile` khác `test-compile` và `test`.
- [ ] Không thêm plugin executions trùng với lifecycle defaults nếu không cần.
- [ ] CI chạy phase thực sự thực thi test, không dừng ở `test-compile` khi muốn quality gate.
- [ ] Không lạm dụng `-Dmaven.test.skip=true` để che lỗi test compilation.
- [ ] Đã kiểm tra generated resources/sources, annotation processing nếu dự án sử dụng.
- [ ] Đã dùng build sạch và xem Surefire reports khi debugging.
- [ ] Đã xác nhận artifact phát hành không vô tình chứa test classes/test-only dependencies.

**Kết luận:** `compiler:compile` biên dịch **mã nguồn chính** trong phase `compile`, còn `compiler:testCompile` biên dịch **mã nguồn kiểm thử** trong phase `test-compile` với test classpath. Cả hai cùng thuộc Maven Compiler Plugin nhưng khác nhiệm vụ, dependency resolution scope và output directories. **Muốn biết test có PASS hay không, phải chạy phase `test` với test runner phù hợp**, không chỉ biên dịch test.

### Tài liệu Apache Maven chính thức

- [Maven Compiler Plugin 3.13.0 — compiler:compile](https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.13.0/compile-mojo.html)
- [Maven Compiler Plugin 3.13.0 — compiler:testCompile](https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.13.0/testCompile-mojo.html)
- [Maven Compiler Plugin — Setting the --release of the Java Compiler](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Maven Compiler Plugin — Compiling Sources Using A Different JDK](https://maven.apache.org/plugins/maven-compiler-plugin/examples/compile-using-different-jdk.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven Surefire Plugin — Skipping Tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/skipping-tests.html)
- [Maven Help Plugin — help:describe](https://maven.apache.org/plugins/maven-help-plugin/describe-mojo.html)
- [Maven POM Reference — build/plugins/dependencies](https://maven.apache.org/pom.html)
