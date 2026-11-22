# Đọc log để phân biệt lỗi cấu hình build, biên dịch, kiểm thử và đóng gói

## 1. Mục tiêu: xác định đúng giai đoạn gây lỗi

Khi chạy một lệnh build Spring Boot, Maven hoặc Gradle có thể in hàng trăm dòng log. Dòng cuối thường chỉ ghi **BUILD FAILURE** hoặc **BUILD FAILED**. Nó xác nhận build không thành công, nhưng chưa chỉ ra nguyên nhân gốc.

Muốn xử lý nhanh, hãy xác định lỗi xuất hiện ở giai đoạn nào:

1. **Cấu hình build (configuration):** build tool đọc POM/build script, nạp plugin, profile, repository, toolchain và tạo mô hình/task graph.
2. **Biên dịch (compilation):** compiler xử lý source Java/Kotlin và tạo bytecode.
3. **Kiểm thử (testing):** test engine chạy unit/integration tests và báo assertion, exception hoặc lỗi khởi tạo test.
4. **Đóng gói (packaging):** build tool tạo JAR/WAR; Spring Boot plugin có thể repack archive thành executable JAR/WAR, thêm loader, dependencies và manifest.

Một lỗi có thể xuất hiện trước khi các phase/task bắt đầu, ví dụ Maven không đọc được parent POM hoặc Gradle không phân tích được build.gradle. Lỗi khác xuất hiện trong task cụ thể như compileJava, test, bootJar hoặc Maven repackage.

**Quy tắc đọc log:** tìm phase/goal/task đang chạy, đọc thông báo lỗi đầu tiên có ý nghĩa và lần theo nguyên nhân bên dưới nó. Dòng tổng kết cuối log thường chỉ là hậu quả.

### 1.1. Bản đồ nhận diện nhanh

| Giai đoạn | Maven thường thấy | Gradle thường thấy | Dấu hiệu tiêu biểu |
|---|---|---|---|
| Cấu hình | Model building, validate, plugin/dependency resolution, profile | Initialization/configuration, đọc settings/build script | POM/XML sai, plugin không resolve, method/property không tồn tại, repository/auth |
| Biên dịch | maven-compiler-plugin:compile hoặc testCompile | compileJava, compileTestJava | cannot find symbol, package does not exist, incompatible types, invalid source/release |
| Kiểm thử | maven-surefire-plugin:test, maven-failsafe-plugin | test, integrationTest nếu project tạo task | Failures, Errors, assertion mismatch, test engine/discovery, forked JVM |
| Đóng gói | maven-jar-plugin:jar, maven-war-plugin:war, spring-boot-maven-plugin:repackage | jar, war, bootJar, bootWar | archive không tạo được, main class/manifest sai, thiếu resource, nhầm plain JAR và executable JAR |

Tên phase/task thực tế phụ thuộc plugin và cấu hình dự án. Bảng trên là dấu hiệu định hướng, không phải chuỗi cố định cho mọi project.

## 2. Chuẩn bị log có thể chẩn đoán

Trước khi đọc từng dòng, ghi lại đúng lệnh đã thất bại và môi trường chạy. Hai máy có thể chạy cùng commit nhưng dùng JDK, Maven/Gradle, profile hoặc biến môi trường khác nhau.

### 2.1. Kiểm tra Java và build tool

Maven:

```bash
java -version
javac -version
mvn -version
```

Gradle:

```bash
java -version
javac -version
./gradlew --version
```

Trên Windows PowerShell, dùng `.\gradlew.bat --version`. Với Maven Wrapper, dùng `.\mvnw.cmd -version`.

Cần phân biệt:

- `java -version` hiển thị Java mà shell tìm thấy qua PATH.
- `mvn -version` cho biết Java đang chạy Maven.
- `gradlew --version` hiển thị phiên bản Gradle và JVM của launcher/daemon.
- Maven Toolchains hoặc Gradle Java Toolchains có thể chọn JDK khác cho compiler/test task.

Vì vậy JVM chạy build tool và JDK dùng để biên dịch không nhất thiết giống nhau. Nếu log báo source/release không tương thích, hãy kiểm tra cả build JVM lẫn compiler toolchain.

### 2.2. Maven: tăng chi tiết theo từng nấc

Bắt đầu bằng batch mode và stack trace:

```bash
mvn -B -Dstyle.color=never clean verify -e
```

- `-B`: batch mode, phù hợp CI.
- `-Dstyle.color=never`: giảm mã màu để log dễ lưu và so sánh.
- `-e`: in exception stack trace chi tiết hơn.

Khi đã biết goal nào thất bại nhưng vẫn chưa hiểu plugin xử lý gì, chạy lại với `-X`:

```bash
mvn -B -Dstyle.color=never clean verify -e -X
```

`-X` tạo log rất dài và có thể làm lộ URL repository nội bộ, property, đường dẫn, cấu hình hoặc credential tùy plugin. Không đưa nguyên debug log lên issue công khai; hãy rà soát và che thông tin nhạy cảm trước khi chia sẻ.

Lưu log trong Bash/Linux/macOS:

```bash
mvn -B -Dstyle.color=never clean verify -e > build.log 2>&1
```

Trong PowerShell:

```powershell
mvn -B -Dstyle.color=never clean verify -e *> build.log
```

### 2.3. Gradle: stacktrace, info và console plain

Bắt đầu bằng:

```bash
./gradlew clean build --stacktrace --info --console=plain
```

- `--stacktrace`: hiển thị stack trace của lỗi build, kể cả lỗi do người dùng như compile errors.
- `--info`: cho thêm thông tin về cấu hình và task execution.
- `--console=plain`: bỏ rich console/progress bar, giúp log CI dễ đọc.

Nếu cần chi tiết hơn:

```bash
./gradlew clean build --full-stacktrace --debug --console=plain
```

Gradle `--debug` có thể ghi environment variables, repository credentials và build cache credentials. Chỉ bật khi thực sự cần, giới hạn quyền truy cập log và kiểm tra nội dung trước khi gửi.

Lưu log:

```bash
./gradlew clean build --stacktrace --info --console=plain > build.log 2>&1
```

### 2.4. Không chỉ tìm chữ ERROR

Các dòng sau thường là dấu hiệu phân loại:

```text
[FATAL] Non-resolvable parent POM
[ERROR] Failed to execute goal ... maven-compiler-plugin ...:compile
[ERROR] COMPILATION ERROR
[ERROR] Tests run: 12, Failures: 1, Errors: 0, Skipped: 0
[ERROR] Failed to execute goal ... maven-surefire-plugin ...:test
[ERROR] Failed to execute goal ... spring-boot-maven-plugin ...:repackage
> Task :compileJava FAILED
> Task :test FAILED
> Task :bootJar FAILED
* What went wrong:
BUILD FAILURE
BUILD FAILED
```

Dòng `Failed to execute goal` hoặc `Execution failed for task` thường cho biết goal/task nào thất bại. Nguyên nhân chi tiết có thể nằm ngay phía trên, trong compiler output hoặc ở phần `Caused by` bên dưới.

**Không kết luận từ BUILD FAILURE một mình.** Hãy đọc tên goal/task và lỗi đầu tiên giải thích vì sao nó thất bại.

## 3. Hiểu thứ tự thực thi trước khi đọc log

### 3.1. Maven default lifecycle

Các phase quan trọng của Maven:

```text
validate
   |
compile
   |
test-compile
   |
test
   |
package
   |
integration-test
   |
verify
   |
install
   |
deploy
```

Maven thực thi các phase trước phase được yêu cầu. Ví dụ:

- `mvn compile` chạy các phase trước và tới compile; không chạy unit tests.
- `mvn test` chạy compile, test-compile và test.
- `mvn package` chạy các bước trước đó rồi tạo JAR/WAR.
- `mvn verify` đi qua package và chạy các kiểm tra được bind tới verify.
- `mvn install` còn cài artifact vào local Maven repository.
- `mvn deploy` tiếp tục publish artifact theo cấu hình repository.

Khi cần xác minh một bản build đầy đủ, `mvn verify` là lựa chọn tốt cho phần lớn dự án. Integration tests chỉ chạy nếu project đã cấu hình plugin tương ứng, chẳng hạn Maven Failsafe.

### 3.2. Gradle có configuration và task execution

Gradle có ba bước chính:

1. **Initialization:** xác định build và project tham gia.
2. **Configuration:** đọc settings/build scripts, áp plugin, cấu hình project và tạo task graph.
3. **Execution:** thực thi các task trong graph theo dependency/order.

Khác Maven, Gradle không có một chuỗi phase cố định tương ứng validate → compile → test → package. Task graph được tạo từ plugin và build scripts.

Một phép thử hữu ích là:

```bash
./gradlew help
```

Task help không chạy compile/test/package, nhưng Gradle vẫn phải cấu hình build scripts. Nếu **help cũng thất bại**, hãy điều tra settings.gradle, build.gradle, plugin resolution và configuration. Nếu help thành công nhưng build thất bại, tập trung vào task được báo lỗi.

## 4. Nhận diện lỗi cấu hình build

Lỗi cấu hình thường xuất hiện trước khi compiler hoặc test runner làm việc.

### 4.1. Maven: POM, parent, plugin và repository

| Dấu hiệu trong log | Ý nghĩa thường gặp | Kiểm tra |
|---|---|---|
| Non-parseable POM | XML sai cú pháp, tag đóng/mở không khớp hoặc cấu trúc POM sai | Dòng và cột trong POM |
| Non-resolvable parent POM | Maven không tìm thấy/tải được parent hoặc relativePath không đúng | groupId/artifactId/version, relativePath, repository |
| Could not resolve dependencies | Không tải được dependency hoặc metadata | Repository URL, proxy, credentials, version |
| Plugin not found / No plugin found for prefix | Plugin chưa khai báo, prefix không resolve hoặc repository không truy cập được | Plugin coordinates, pluginRepositories, mạng |
| Unknown lifecycle phase | Gõ sai phase hoặc đặt tham số/goal không đúng | Lệnh Maven đã chạy |
| Invalid POM / Missing artifactId or version | Thiếu trường bắt buộc hoặc property chưa được resolve | POM và effective POM |
| Failed to read artifact descriptor | Không đọc được POM/metadata của dependency | Repository, parent của dependency, network/auth |

Ví dụ log **minh họa**:

```text
[FATAL] Non-resolvable parent POM for com.example:diagnostic-log-lab:1.0.0
Could not transfer artifact org.springframework.boot:spring-boot-starter-parent:pom:3.5.16
from/to central (https://repo.maven.apache.org/maven2):
Connect timed out
```

Đây là lỗi resolve parent/repository, không phải lỗi Java source. Sửa code không giải quyết được timeout.

Một lỗi khác:

```text
[ERROR] Plugin org.springframework.boot:spring-boot-maven-plugin:... or one of its dependencies could not be resolved
```

Kiểm tra plugin version, repository cấu hình, proxy, credentials và khả năng truy cập repository. Nếu plugin được quản lý bởi Spring Boot parent, xác minh parent thực sự được kế thừa.

### 4.2. Kiểm tra cấu hình Maven sau khi kế thừa

```bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn help:active-profiles
mvn help:effective-settings -Doutput=target/effective-settings.xml
```

Các lệnh này giúp xác định:

- Parent/BOM và plugin version thực tế.
- Profile nào đang active.
- Property nào được kế thừa hoặc ghi đè.
- Repository và mirror nào được sử dụng.

**effective-settings.xml có thể chứa thông tin nhạy cảm hoặc nội bộ.** Không đăng file này công khai; chỉ trích phần cần thiết và che thông tin bảo mật.

Nếu cần chạy riêng một module trong Maven reactor:

```bash
mvn -pl service-api -am validate
```

`-pl` chọn module; `-am` build thêm các module mà nó phụ thuộc trong reactor. Dùng tên/path module đúng với project.

### 4.3. Gradle: lỗi configuration trước task

Ví dụ:

```text
FAILURE: Build failed with an exception.

* Where:
Build file '.../build.gradle' line: 18

* What went wrong:
Could not find method implementation() for arguments [...]
on object of type org.gradle.api.internal.artifacts.dsl.dependencies.DefaultDependencyHandler.
```

Đây là lỗi khi Gradle đọc build script. Nguyên nhân có thể là:

- Chưa áp dụng plugin Java/Java Library nhưng đã dùng configuration do plugin tạo.
- Dùng sai cú pháp Groovy/Kotlin DSL.
- Plugin version không tương thích Gradle wrapper.
- Gọi extension/task/property không tồn tại.
- Plugin không tải được từ plugin portal hoặc repository.

Dùng:

```bash
./gradlew help --stacktrace
./gradlew tasks --all
./gradlew help --task bootJar
```

Nếu help thất bại, giải quyết configuration trước. Nếu help thành công, kiểm tra task graph và task đang chạy khi lỗi xuất hiện.

### 4.4. Phân biệt lỗi cấu hình với lỗi resolve dependency trong task

Dependency có thể được resolve trong configuration phase hoặc khi task cần classpath. Vì vậy không nên chỉ nhìn thông báo “Could not resolve” rồi kết luận đó là lỗi POM/build script.

Hãy hỏi:

1. Lệnh help có chạy được không (Gradle)?
2. Maven đã đọc xong POM và bắt đầu goal/phase nào?
3. Log có tên plugin/task thất bại không?
4. Dependency đang được resolve cho plugin, compile classpath, test runtime hay packaging?
5. Lỗi là network/credentials, version không tồn tại hay conflict trong build logic?

Nếu log cho biết Maven đang tải compiler plugin hoặc Gradle đang resolve compileClasspath, đó là lỗi dependency resolution tại bước phục vụ task tương ứng.

## 5. Nhận diện lỗi biên dịch Java

Lỗi biên dịch xảy ra khi compiler không thể biến source code thành bytecode.

### 5.1. Các thông báo compiler phổ biến

| Thông báo | Ý nghĩa | Hướng xử lý |
|---|---|---|
| cannot find symbol | Không tìm thấy class, method, field hoặc biến | Kiểm tra tên, import, dependency, source set |
| package ... does not exist | Thiếu package/class trên compile classpath | Kiểm tra dependency, scope, import và version |
| incompatible types | Kiểu dữ liệu không tương thích | Sửa generic, method signature hoặc conversion |
| method ... cannot be applied | Không có overload phù hợp với arguments | So kiểu và số lượng tham số |
| invalid source release: 21 | JDK/compiler đang dùng không hỗ trợ source/release yêu cầu | Kiểm tra JDK chạy build và compiler toolchain |
| release version 17 not supported | Compiler/JDK được chọn quá cũ cho release target | Chọn JDK phù hợp |
| duplicate class | Cùng fully qualified class xuất hiện từ nhiều source/dependency | Kiểm tra source roots và dependency |
| unmappable character / illegal character | Encoding hoặc ký tự source không hợp lệ | Kiểm tra UTF-8, encoding và file nguồn |

Ví dụ Maven:

```text
[INFO] --- maven-compiler-plugin:...:compile (default-compile) @ diagnostic-log-lab ---
[ERROR] COMPILATION ERROR
[ERROR] .../GreetingService.java:[8,16] cannot find symbol
  symbol:   method greeting(java.lang.String)
  location: class GreetingService
[ERROR] Failed to execute goal ... maven-compiler-plugin:...:compile
```

Đây là lỗi compile main source. Maven có thể chưa chạy tới test hoặc package. Đọc file, dòng, cột và symbol mà compiler nêu trước khi thay đổi POM.

### 5.2. Lỗi biên dịch test source khác lỗi test fail

Maven có bước test-compile trước test. Nếu test code không compile được, log thường chỉ ra maven-compiler-plugin đang chạy `testCompile` hoặc đường dẫn dưới `src/test/java`.

Ví dụ:

```text
[ERROR] .../src/test/java/com/example/GreetingServiceTest.java:[14,9]
cannot find symbol
  symbol: method assertEquals(...)
```

Đây vẫn là **compile error**, chưa phải assertion failure. Kiểm tra test dependency, import JUnit và test source.

Gradle cũng có thể thất bại ở **compileTestJava** trước khi task **test** được thực thi.

### 5.3. Xác minh JDK và compiler target

Maven:

```bash
java -version
mvn -version
mvn help:effective-pom -Doutput=target/effective-pom.xml
```

Kiểm tra các thuộc tính như `java.version`, `maven.compiler.release`, maven-compiler-plugin và Maven Toolchains nếu project có cấu hình.

Ví dụ Spring Boot parent:

```xml
<properties>
    <java.version>17</java.version>
</properties>
```

Gradle Groovy DSL:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Kiểm tra Gradle JVM:

```bash
./gradlew --version
./gradlew -q javaToolchains
```

**Không chỉ kiểm tra Java trên terminal.** Maven/Gradle daemon có thể chạy với JDK khác, còn compiler toolchain có thể chọn JDK riêng.

### 5.4. Tách compile khỏi các bước sau

Maven:

```bash
mvn -pl service-api -am compile
mvn -pl service-api -am test-compile
```

Gradle:

```bash
./gradlew :service-api:compileJava
./gradlew :service-api:compileTestJava
```

Nếu compileJava/testCompile thất bại, chưa cần điều tra Spring Boot repackage hay Docker image. Sửa compiler error trước, rồi chạy lại full verify/build.

## 6. Nhận diện lỗi kiểm thử

Kiểm thử chỉ bắt đầu sau khi test source đã compile và test engine có thể khởi chạy.

### 6.1. Phân biệt Failure và Error

- **Failure:** test chạy được nhưng assertion không đúng với kết quả thực tế.
- **Error:** test gặp exception hoặc lỗi trong quá trình setup/teardown/execution, không phải assertion mismatch đơn giản.
- **Skipped:** test bị bỏ qua do annotation, assumption, cấu hình hoặc điều kiện chạy.
- **No tests found / No tests were executed:** test runner không phát hiện test phù hợp hoặc filter/provider cấu hình sai.

Ví dụ Maven:

```text
[INFO] Running com.example.diagnostic.GreetingServiceTest
[ERROR] Tests run: 2, Failures: 1, Errors: 0, Skipped: 0
[ERROR] greetReturnsGreeting -- expected: <Hello, An> but was: <Hi, An>
[ERROR] Failed to execute goal ... maven-surefire-plugin:...:test
There are test failures.
```

Ở đây compiler đã hoàn tất; Surefire đã chạy test; một assertion sai làm phase test thất bại. Không sửa compiler config hoặc Spring Boot packaging để xử lý lỗi này.

### 6.2. Test reports của Maven

Surefire mặc định lưu report tại:

```text
target/surefire-reports/
├── TEST-com.example.diagnostic.GreetingServiceTest.xml
└── com.example.diagnostic.GreetingServiceTest.txt
```

Mở file TXT để xem stack trace/console output và file XML để lấy dữ liệu có cấu trúc cho CI.

Chạy riêng một test class:

```bash
mvn -Dtest=GreetingServiceTest test
```

Chạy riêng một test method (nếu Surefire version/provider hỗ trợ cú pháp tương ứng):

```bash
mvn -Dtest=GreetingServiceTest#greetReturnsGreeting test
```

Nếu project dùng Maven Failsafe cho integration tests, xem thêm **target/failsafe-reports/**. Failsafe thường chạy ở integration-test và verify; chỉ tìm report ở surefire-reports có thể bỏ sót lỗi integration test.

### 6.3. Gradle test failure

Ví dụ:

```text
> Task :test FAILED

GreetingServiceTest > greetReturnsGreeting() FAILED
    org.opentest4j.AssertionFailedError:
    expected: <Hello, An> but was: <Hi, An>

FAILURE: Build failed with an exception.

* What went wrong:
Execution failed for task ':test'.
> There were failing tests.
```

Thông báo **Execution failed for task ':test'** xác định task thất bại; assertion và report mới cho biết test case nào sai.

Gradle Java testing mặc định tạo HTML report và XML results. Với project mặc định, kiểm tra:

```text
build/reports/tests/test/
build/test-results/test/
```

Chạy một test class:

```bash
./gradlew test --tests com.example.diagnostic.GreetingServiceTest
```

Chạy với thông tin test nhiều hơn:

```bash
./gradlew test --info --stacktrace --console=plain
```

### 6.4. Test failure hay test infrastructure failure?

Không phải mọi lỗi dưới Surefire/Gradle test đều là assertion failure.

| Dấu hiệu | Có thể là | Cần xem |
|---|---|---|
| expected ... but was ... | Assertion failure | Test case và dữ liệu thực tế |
| NullPointerException trong test | Test/setup/runtime error | Stack trace, fixture, dependency injection |
| No tests were executed | Discovery/filter/provider | Tên class, annotation, engine và include/exclude |
| NoClassDefFoundError lúc chạy test | Test runtime classpath | Scope test, dependency version, JUnit engine |
| Forked VM terminated without properly saying goodbye | JVM test process bị crash/kill | Heap, OOM, System.exit, CI timeout, dump file |
| Port already in use | Integration test cần port nhưng port đang bị chiếm | Test server/parallelism/port config |
| Connection refused / timeout | Service phụ thuộc chưa chạy hoặc không truy cập được | Testcontainers, database, service endpoint, network |
| Test skipped | Có cấu hình/điều kiện bỏ qua | Annotation, assumptions, skip property |

**Đọc report trước khi tăng log level.** Stack trace trong report thường đủ để biết lỗi nằm trong assertion, test fixture hay quá trình khởi tạo test runner.

### 6.5. Không dùng skip-tests để che lỗi

Maven có hai cờ dễ nhầm:

```bash
# Bỏ chạy test nhưng vẫn compile test sources:
mvn package -DskipTests

# Bỏ cả compile test sources và chạy test:
mvn package -Dmaven.test.skip=true
```

Đây là cách chẩn đoán tạm thời để xác định lỗi nằm ở test hay bước sau test. Nó **không sửa test** và không chứng minh bản build đạt quality gate. Không dùng cờ skip trong release pipeline nếu policy yêu cầu test.

Gradle có thể loại task test khỏi build:

```bash
./gradlew build -x test
```

Cũng chỉ dùng khi cần cô lập nguyên nhân; ghi rõ test đã bị bỏ qua. Build thành công với test bị loại khỏi task graph không có nghĩa test suite đã pass.

## 7. Nhận diện lỗi đóng gói JAR/WAR

Đóng gói biến bytecode/resources thành artifact phân phối. Với Spring Boot, cần phân biệt **JAR thường** và **executable Boot JAR**.

### 7.1. Maven package và Spring Boot repackage

Maven thường gọi maven-jar-plugin để tạo JAR ban đầu. Spring Boot Maven Plugin dùng goal **repackage** để biến JAR/WAR đó thành archive có loader, dependencies và manifest thích hợp để chạy bằng `java -jar`.

Với project dùng `spring-boot-starter-parent`, execution `repackage` được cấu hình sẵn; khi khai báo Spring Boot Maven Plugin, goal được chạy ở phase package theo cấu hình parent. Nếu không dùng parent, phải khai báo execution phù hợp trong POM.

Ví dụ plugin declaration:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

Nếu Maven báo lỗi trong goal `spring-boot-maven-plugin:repackage`, compile/test có thể đã pass nhưng archive chưa được repack thành executable. Đọc lỗi của goal đó, không suy ra lỗi Java compiler.

### 7.2. Dấu hiệu packaging failure

Ví dụ log minh họa:

```text
[INFO] --- maven-jar-plugin:...:jar (default-jar) @ diagnostic-log-lab ---
[INFO] Building jar: target/diagnostic-log-lab-1.0.0.jar

[INFO] --- spring-boot-maven-plugin:...:repackage (repackage) @ diagnostic-log-lab ---
[ERROR] Failed to execute goal ... spring-boot-maven-plugin:...:repackage
[ERROR] Unable to find a suitable main class
```

Đây là lỗi đóng gói executable Boot archive. Compiler/test có thể đã pass; plugin không tìm thấy entry point phù hợp hoặc cấu hình mainClass không đúng.

Kiểm tra:

- Có class main chứa `public static void main(String[] args)` không?
- Class đó có được compile vào output directory không?
- Có nhiều main class khiến plugin không tự chọn được không?
- Có cấu hình mainClass sai trong Spring Boot Maven Plugin không?
- Plugin repackage có thực sự được thực thi không?

Khi cần chỉ rõ main class, cấu hình trong **spring-boot-maven-plugin**, không đặt nhầm ở maven-jar-plugin:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>com.example.diagnostic.DiagnosticApplication</mainClass>
    </configuration>
</plugin>
```

### 7.3. Build thành công nhưng java -jar báo lỗi

Một trường hợp quan trọng: Maven/Gradle báo build thành công nhưng chạy:

```bash
java -jar target/diagnostic-log-lab-1.0.0.jar
```

lại nhận:

```text
no main manifest attribute, in target/diagnostic-log-lab-1.0.0.jar
```

Đây thường là dấu hiệu bạn đang chạy **JAR thường** không có manifest entry point phù hợp hoặc đã chọn nhầm artifact, ví dụ classifier/plain JAR. Nó không phải lỗi compile hay test.

Kiểm tra nội dung:

```bash
jar tf target/diagnostic-log-lab-1.0.0.jar
```

Executable Spring Boot JAR thường có:

```text
META-INF/MANIFEST.MF
org/springframework/boot/loader/...
BOOT-INF/classes/...
BOOT-INF/lib/...
```

Mở manifest để xem Main-Class và Start-Class; đối chiếu tên file được tạo bởi Maven. Với Spring Boot, Main-Class thường là launcher của Boot Loader và Start-Class là main class ứng dụng. Khi plugin được cấu hình classifier, có thể tồn tại cả artifact gốc và artifact executable có hậu tố classifier. Hãy chạy đúng file.

### 7.4. Maven original artifact và classifier

Spring Boot repackage mặc định thay artifact chính bằng executable archive và đổi file gốc thành hậu tố `.original`. Khi dùng classifier, plugin có thể tạo thêm artifact executable riêng và giữ nguyên JAR gốc.

Ví dụ có thể thấy:

```text
target/
├── diagnostic-log-lab-1.0.0.jar
└── diagnostic-log-lab-1.0.0.jar.original
```

Nếu cấu hình classifier `exec`, tên file có thể thành:

```text
target/
├── diagnostic-log-lab-1.0.0.jar
└── diagnostic-log-lab-1.0.0-exec.jar
```

Tên thật phụ thuộc finalName, classifier và packaging. Không giả định mọi project đều có file .original hoặc hậu tố -exec.

### 7.5. Gradle: jar khác bootJar

Trong Spring Boot Gradle project:

- **jar** là task của Java plugin để tạo JAR thông thường.
- **bootJar** do Spring Boot Gradle Plugin cung cấp để tạo executable Boot JAR.
- **bootWar** tạo executable WAR khi project cấu hình WAR packaging.

Chạy:

```bash
./gradlew clean bootJar
./gradlew tasks --all
```

Kiểm tra output tại **build/libs/**. Có thể tồn tại archive thường và executable archive, tên cụ thể phụ thuộc classifier/version/configuration. Nếu chạy nhầm plain JAR, `java -jar` có thể báo thiếu main manifest.

Nếu bootJar thất bại, đọc phần **What went wrong**, tên task và lỗi main class/resources. Nếu bootJar không xuất hiện trong tasks, kiểm tra Spring Boot Gradle Plugin đã được áp dụng chưa và plugin version có resolve thành công không.

### 7.6. Đóng gói WAR và provided dependencies

Với Spring Boot executable WAR, thư viện có thể nằm ở:

- `WEB-INF/lib/`
- `WEB-INF/lib-provided/`

Nếu deploy lên servlet container ngoài, cần hiểu dependency nào thuộc container và dependency nào được đóng vào WAR để chạy embedded. Một WAR build thành công không đồng nghĩa đã tương thích với mọi servlet container; kiểm tra manifest, layout và runtime deployment target.

## 8. Ví dụ thực hành Java 17: project nhỏ để tái hiện bốn giai đoạn

Ví dụ dùng Spring Boot 3.5.16 và Java 17. Mục tiêu là có project Maven đơn giản, có main class, service và JUnit test để phân biệt compile/test/package.

### 8.1. Cấu trúc thư mục

```text
diagnostic-log-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/diagnostic/
    │   ├── DiagnosticApplication.java
    │   └── GreetingService.java
    └── test/java/com/example/diagnostic/
        └── GreetingServiceTest.java
```

### 8.2. POM tối thiểu

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>diagnostic-log-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Parent quản lý plugin và dependency versions. Với project này, khai báo Spring Boot Maven Plugin sẽ dùng execution repackage được parent cấu hình sẵn trong lifecycle package.

### 8.3. Main class

`src/main/java/com/example/diagnostic/DiagnosticApplication.java`:

```java
package com.example.diagnostic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DiagnosticApplication {

    public static void main(String[] args) {
        SpringApplication.run(DiagnosticApplication.class, args);
    }
}
```

### 8.4. Service

`src/main/java/com/example/diagnostic/GreetingService.java`:

```java
package com.example.diagnostic;

public class GreetingService {

    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

### 8.5. JUnit test

`src/test/java/com/example/diagnostic/GreetingServiceTest.java`:

```java
package com.example.diagnostic;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingServiceTest {

    @Test
    void greetReturnsGreeting() {
        GreetingService service = new GreetingService();

        assertEquals("Hello, An", service.greet("An"));
    }
}
```

Test đúng sẽ pass. Để mô phỏng test failure, tạm đổi expected value thành `Hello, Binh`; compiler vẫn thành công nhưng assertion sẽ thất bại. Khôi phục expected value trước khi build release.

### 8.6. Chạy từng bước để biết lỗi nằm ở đâu

Từ project root:

```bash
# Kiểm tra môi trường và POM:
java -version
mvn -version
mvn validate

# Chỉ compile main source:
mvn compile

# Compile và chạy unit tests:
mvn test

# Đóng gói JAR/WAR:
mvn package

# Chạy các kiểm tra tới verify:
mvn verify
```

Khi một lệnh thất bại, dừng ở giai đoạn đó và đọc goal/plugin. Không cần điều tra repackage nếu compile chưa xong. Khi đã sửa, chạy lại phase thất bại rồi xác minh full verify.

### 8.7. Log thành công có dạng gì?

Log minh họa:

```text
[INFO] --- maven-compiler-plugin:...:compile (...) @ diagnostic-log-lab ---
[INFO] Compiling ... source files with javac [debug release 17]

[INFO] --- maven-compiler-plugin:...:testCompile (...) @ diagnostic-log-lab ---
[INFO] Compiling ... test source files

[INFO] --- maven-surefire-plugin:...:test (...) @ diagnostic-log-lab ---
[INFO] Running com.example.diagnostic.GreetingServiceTest
[INFO] Tests run: 1, Failures: 0, Errors: 0, Skipped: 0

[INFO] --- maven-jar-plugin:...:jar (...) @ diagnostic-log-lab ---
[INFO] Building jar: target/diagnostic-log-lab-1.0.0.jar

[INFO] --- spring-boot-maven-plugin:...:repackage (...) @ diagnostic-log-lab ---
[INFO] Replacing main artifact with repackaged archive

[INFO] BUILD SUCCESS
```

Version plugin, số file, thời gian và câu log chính xác phụ thuộc plugin versions. Điều cần nhận diện là chuỗi compile → testCompile → test → jar → repackage và kết quả cuối.

### 8.8. Kiểm tra artifact

```bash
jar tf target/diagnostic-log-lab-1.0.0.jar
java -jar target/diagnostic-log-lab-1.0.0.jar
```

JAR executable cần có Boot loader, application classes và dependencies. Ứng dụng ví dụ không có web server và không tự in greeting; mục tiêu của `java -jar` là xác minh manifest/loader và Spring Boot startup.

## 9. Gradle: các task cần đọc khi build Spring Boot

| Mục tiêu | Task thường dùng |
|---|---|
| Xem task có sẵn | tasks, tasks --all |
| Compile main Java | compileJava |
| Compile test Java | compileTestJava |
| Chạy unit tests | test |
| Kiểm tra quality tasks | check |
| Tạo JAR thường | jar |
| Tạo executable Spring Boot JAR | bootJar |
| Tạo executable WAR | bootWar |
| Build thông thường | build |

Chạy các task độc lập:

```bash
./gradlew help
./gradlew compileJava --stacktrace
./gradlew compileTestJava --stacktrace
./gradlew test --stacktrace --info
./gradlew bootJar --stacktrace --info
./gradlew build --stacktrace --info
```

Trong multi-project build, dùng task path đầy đủ:

```bash
./gradlew :service-api:compileJava
./gradlew :service-api:test
./gradlew :service-api:bootJar
```

Đọc prefix task trong log:

- `> Task :compileJava FAILED`: main source compile task.
- `> Task :compileTestJava FAILED`: test source compile task.
- `> Task :test FAILED`: test execution/reporting.
- `> Task :bootJar FAILED`: Spring Boot archive packaging.
- `BUILD FAILED`: kết quả tổng hợp.

Task có trạng thái **UP-TO-DATE**, **FROM-CACHE** hoặc **NO-SOURCE** không nhất thiết là lỗi. Chúng mô tả task được bỏ qua/tái sử dụng/không có input source trong lần chạy đó. Đọc trạng thái task cùng task graph và mục tiêu build.

## 10. Ma trận xử lý theo thông báo log

| Log/triệu chứng | Phân loại | Việc làm đầu tiên |
|---|---|---|
| Non-parseable POM | Cấu hình Maven | Sửa XML, kiểm tra line/column |
| Non-resolvable parent POM | Parent/repository | Kiểm tra coordinates, relativePath, mirror, credentials |
| Plugin could not be resolved | Plugin/repository | Kiểm tra plugin version, pluginRepositories và mạng |
| Could not find method/property trong build.gradle | Gradle configuration | Kiểm tra plugin, DSL và version |
| Invalid source release | Biên dịch/toolchain | So JDK build với compiler release/toolchain |
| cannot find symbol | Biên dịch | Đọc symbol/file/line và compile classpath |
| compileTestJava/testCompile failure | Biên dịch test source | Kiểm tra JUnit imports, test dependency và code test |
| Tests run, Failures > 0 | Kiểm thử assertion | Mở test report, xem expected/actual |
| Tests run, Errors > 0 | Kiểm thử runtime/setup | Xem stack trace, fixtures, test context |
| No tests found | Test discovery/config | Kiểm tra naming, annotations, filters, engine |
| Forked VM terminated | Test process/infrastructure | Xem OOM, JVM crash, timeout, fork logs |
| repackage cannot find main class | Spring Boot packaging | Kiểm tra main class và plugin mainClass |
| No main manifest attribute khi java -jar | Chọn sai artifact/packaging | Kiểm tra repackage/bootJar và manifest |
| Missing BOOT-INF/lib trong executable JAR | Packaging | Có thể chạy nhầm plain JAR hoặc plugin repackage không chạy |
| JAR/WAR được tạo nhưng thiếu resource | Packaging/resource processing | Kiểm tra resource directories, filtering và plugin config |
| BUILD SUCCESS nhưng ứng dụng không startup | Runtime/deployment | Đọc application exception sau khi đóng gói |

## 11. Những lỗi dễ bị phân loại nhầm

### 11.1. Build config và dependency resolution

Plugin không resolve được có thể xảy ra trước khi task compile. Nhưng dependency ứng dụng chỉ được resolve khi compile/test task cần classpath. Hãy dùng tên goal/task trong log để biết dependency đang phục vụ phần nào.

### 11.2. Test compile và test execution

Nếu compiler thất bại trong testCompile/compileTestJava, test runner chưa chạy. Nếu test report có Failure/Error, source đã compile và test runner đã thực thi ít nhất một phần.

### 11.3. Packaging và runtime startup

Nếu Maven/Gradle tạo archive thành công nhưng java -jar báo lỗi, build có thể đã hoàn tất theo task graph nhưng artifact không phải executable Boot archive hoặc gặp lỗi runtime. Kiểm tra:

1. Đúng file JAR/WAR chưa?
2. Có manifest phù hợp không?
3. Có Boot loader và nested dependencies không?
4. Main class có tồn tại không?
5. Lỗi xảy ra khi JVM nạp archive hay sau khi Spring ApplicationContext khởi động?

### 11.4. Warning không luôn là failure

Một số warning chỉ báo API deprecated, unchecked operations, plugin configuration sắp lỗi hoặc resource filtering. Chúng có thể chưa làm build fail. Tuy nhiên warning về version/JDK compatibility có thể dự báo lỗi khi nâng build tool. Gradle có `--warning-mode=all` để xem chi tiết; Maven dùng log và plugin report tương ứng.

Không bật fail-on-all-warnings chỉ để “sạch log” nếu dự án chưa có kế hoạch xử lý warning và không biết phạm vi ảnh hưởng.

## 12. Quy trình chẩn đoán chuẩn trong CI

1. **Ghi nhận lệnh:** Maven/Gradle command, module, profile, properties và commit SHA.
2. **Ghi nhận môi trường:** Java/JDK, Maven/Gradle Wrapper, OS và architecture.
3. **Lưu log đầy đủ:** ưu tiên stacktrace và plain console; chỉ bật debug khi cần.
4. **Tìm phase/goal/task thất bại:** cấu hình, compile, test hay package.
5. **Tách bước tái hiện:** chạy validate/help, compile, test, package/bootJar riêng.
6. **Mở report đúng chỗ:** Maven Surefire/Failsafe hoặc Gradle test report.
7. **Kiểm tra artifact:** tên file, kích thước, manifest, loader, dependencies và classifier.
8. **Sửa nguyên nhân:** build config, source, test hoặc packaging plugin đúng tầng.
9. **Chạy lại tầng lỗi:** xác minh thông báo lỗi đã biến mất.
10. **Chạy full verify/build:** bảo đảm các bước trước và sau vẫn pass.
11. **Lưu artifact/log:** giữ đúng file được tạo bởi commit và build đã xác minh.

### 12.1. Ví dụ lệnh CI Maven

```bash
mvn -B -Dstyle.color=never clean verify -e
```

Nếu thất bại, lưu build.log, target/surefire-reports/, target/failsafe-reports/ (nếu có), target/*.jar hoặc target/*.war nếu package đã tạo artifact và effective-pom.xml khi nghi ngờ cấu hình kế thừa.

### 12.2. Ví dụ lệnh CI Gradle

```bash
./gradlew clean build --stacktrace --info --console=plain
```

Lưu build.log, build/reports/tests/, build/test-results/, build/reports/problems-report.html nếu Gradle tạo, và build/libs/*.jar hoặc *.war nếu task packaging đã hoàn thành.

Không đưa debug logs chứa credential lên CI artifact công khai. Giữ log và report cùng build ID/commit để tránh đọc nhầm kết quả từ một lần chạy cũ.

## 13. Checklist đọc log trong 60 giây

- [ ] Xác định đúng lệnh và module thất bại.
- [ ] Kiểm tra Java, Maven/Gradle version.
- [ ] Tìm goal/task cuối cùng bắt đầu chạy.
- [ ] Phân loại lỗi là configuration, compile, test hay package.
- [ ] Đọc lỗi đầu tiên có ý nghĩa và phần Caused by.
- [ ] Nếu là compile, mở đúng source file và line/column.
- [ ] Nếu là test, mở report Surefire/Failsafe hoặc Gradle HTML/XML.
- [ ] Nếu là package, xác định JAR/WAR/plain/boot archive nào được tạo.
- [ ] Nếu java -jar lỗi, kiểm tra manifest và Boot loader.
- [ ] Chỉ bật debug khi stacktrace/info chưa đủ và có thể bảo vệ log.
- [ ] Sau khi sửa, chạy lại phase/task lỗi rồi chạy full verify/build.
- [ ] Lưu log và artifact của đúng commit đã kiểm chứng.

**Kết luận:** Log build cho biết lỗi nằm ở đâu nếu đọc theo thứ tự thực thi. Maven cho thấy phase và plugin goal; Gradle cho thấy configuration và task. Lỗi POM/build script xảy ra trước compile; compiler errors xuất hiện ở compile/testCompile; assertion hoặc exception xuất hiện trong test runner; còn lỗi executable JAR/WAR thường gắn với jar/war/repackage/bootJar và manifest. Khi phân loại đúng, bạn có thể chọn đúng lệnh để tái hiện, mở đúng report và sửa đúng phần cấu hình/source/test/packaging.

### Tài liệu chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Running Maven](https://maven.apache.org/ref/current/maven-embedder/cli.html)
- [Maven Surefire Plugin — Introduction and test reports](https://maven.apache.org/components/surefire/maven-surefire-plugin/)
- [Maven Failsafe Plugin — Integration tests](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Spring Boot Gradle Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html)
- [Gradle — Command-Line Interface and debugging options](https://docs.gradle.org/current/userguide/command_line_interface.html)
- [Gradle — Logging and Output](https://docs.gradle.org/current/userguide/logging.html)
- [Gradle — Troubleshooting Builds](https://docs.gradle.org/current/userguide/troubleshooting.html)
- [Gradle — Testing in Java & JVM projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
