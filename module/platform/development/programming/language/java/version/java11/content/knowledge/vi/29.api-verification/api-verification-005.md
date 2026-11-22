# Chạy kiểm thử trên đúng JDK dự kiến triển khai (Java 11+)

## 1. Tại sao biên dịch thành công chưa chứng minh API chạy được tại production?

Trong **Kiểm chứng API**, có một lỗi rất phổ biến: lập trình viên dùng **JDK 24** để phát triển, biên dịch mã ở mức Java 11 và chạy toàn bộ unit tests trên **JDK 24**, rồi kết luận rằng ứng dụng “đã được kiểm thử trên Java 11”. Kết luận ấy sai: JVM 11 chưa từng thực thi chương trình, và các API mới của JDK, dependencies, modules, truststore, native libraries hoặc flags có thể không giống môi trường thực tế.

**Quy tắc chính:** phải đồng thời kiểm tra **hợp đồng API lúc biên dịch** và **hành vi trên runtime mà sản phẩm sẽ được triển khai**.

| Cần chứng minh | Bằng chứng thực tế | Vì sao không được bỏ |
| --- | --- | --- |
| Mã nguồn/các API công khai phù hợp Java 11 | `javac --release 11` hoặc Maven/Gradle cấu hình tương đương | Chặn gọi API JDK mới hơn, không chỉ hạ bytecode |
| Classfile nhắm đúng Java 11 | `javap -verbose` báo **major version 55** | JVM 11 không nạp classfile của Java 17+ |
| **JVM chạy test** là JDK mục tiêu | `Runtime.version().feature()` **bên trong test process**, kết hợp version/vendor/build của Java executable | `java -version` ở shell hoặc `mvn -version` không nhất thiết là JDK của test forks |
| Package/runtime image đúng | Chạy chính artifact trong deployment image | Phát hiện thiếu module, JNI, native deps, file permissions và cấu hình |
| API hoạt động với dịch vụ phụ thuộc | Integration/contract tests với DB, TLS, HTTP, filesystem và message brokers | Compile/constructor smoke không kiểm tra mọi thao tác |
| Độ ổn định và SLO | Load/soak tests, GC logs, p99 latency, CPU/RSS | Hai JDK/vendor có thể khác hiệu năng và behavior |

Nếu **chỉ deploy JDK 11**, bắt buộc có phép thử thực sự trên **JDK 11**. Nếu artifact target Java 11 nhưng **deploy JDK 21**, tối thiểu phải test runtime 21; và nếu sản phẩm **cam kết hỗ trợ từ Java 11**, còn cần một job thử runtime 11. **API target** và **deployment target** không phải một khái niệm.

## 2. Ba phiên bản cần phân biệt: compiler, classfile, JVM chạy

```text
Mã nguồn Java
    |
    v
[javac JDK 24 --release 11]
    |
    |  Kiểm tra cú pháp + API theo Java 11
    v
[Classfile major 55]
    |
    +---------------------+
    |                     |
    v                     v
[JVM JDK 11]          [JVM JDK 24]
    |                     |
    v                     v
unit/integration tests thật trên từng runtime
    |
    v
deployment readiness theo version đã cam kết
```

Khi chạy trên một JDK mới hơn, ứng dụng có thể vô tình phụ thuộc môi trường mà JVM cũ không có. Hạ `target` không tự thay thế **system APIs** khi biên dịch với một compiler mới. Ngoài ra, JAR chứa nhiều class khác nhau; class chính có major 55 nhưng một dependency lại có major 61 vẫn có thể fail khi JVM 11 load dependency đó.

| Java version | Classfile major | Gợi ý khả năng chạy trên JVM 11 |
| --- | --- | --- |
| 8 | 52 | Có thể, nếu APIs/dependencies tương thích |
| **11** | **55** | Có thể, vẫn phải chạy test |
| 17 | 61 | JVM 11 không nạp được |
| 21 | 65 | JVM 11 không nạp được |
| 24 | 68 | JVM 11 không nạp được |
| 25 | 69 | JVM 11 không nạp được |

**“Có thể” không phải “chắc chắn”:** API runtime, dependency versions, module image và môi trường production vẫn cần kiểm tra. Với `UnsupportedClassVersionError`, cần kiểm tra **từng class/dependency thực sự được load**, không chỉ `Main.class`.

## 3. `--release 11` khác `-source 11 -target 11` như thế nào?

```bash
javac --release 11 App.java
```

`--release 11` làm ba việc: dùng **ngôn ngữ Java 11**, sinh **major 55**, và giới hạn việc tham chiếu **các API công khai được mô tả cho Java 11**. Đây là cấu hình đúng khi project phải duy trì API/bytecode Java 11 dù đang sử dụng compiler JDK mới hơn.

Trong khi đó:

```bash
javac -source 11 -target 11 App.java
```

chủ yếu hạn chế ngôn ngữ và bytecode, **không tự áp dụng bộ system APIs Java 11**. Trên JDK 24, compiler có thể nhìn thấy method mới hơn từ chính thư viện hệ thống của JDK 24.

### Negative API test để thấy khác biệt rõ

Tạo file **`NewApiTrap.java`**:

```java
public class NewApiTrap {
    public static void main(String[] args) {
        System.out.println("value=%s".formatted("ok"));
    }
}
```

`String.formatted` xuất hiện **sau Java 11** (JDK 15). Khi chạy trên JDK 24:

```bash
javac --release 11 NewApiTrap.java
```

**Kỳ vọng:** compile **FAIL** với lỗi không tìm thấy method `formatted`. Đây là **test âm tính có chủ đích**, không phải chương trình Java 11 chạy được.

Trên **JDK 24**, lệnh:

```bash
javac -source 11 -target 11 NewApiTrap.java
```

đã được kiểm thử **compile exit code 0** (với cảnh báo rằng system modules chưa được đặt theo target). Bytecode có thể mang major 55 mà vẫn gọi method không có ở JVM 11; khi chạy đường code đó trên JDK 11 sẽ lỗi liên kết như `NoSuchMethodError`.

**Cần làm:** dùng `--release 11`, sửa code dựa vào API sau Java 11 hoặc nâng hợp đồng minimum JDK một cách minh bạch. Không “sửa xanh” bằng cách bỏ `--release`, tắt test, hay gọi `jdk.internal.*` qua `--add-exports` khi chưa hiểu và chấp nhận rủi ro.

**Giới hạn của `--release`:** không tự quét mọi third-party class/JAR, reflection, dynamic loading, JNI/native libraries, hệ điều hành hoặc các module được đóng gói trong runtime image. Vì thế compiler PASS chỉ là một lớp trong chuỗi kiểm chứng.

## 4. Xác định đúng JDK chạy trong CI, IDE, Maven, Gradle và container

Một máy có thể cài đồng thời JDK 11, 17, 21, 24, 25. Shell, IDE, Gradle daemon, Maven process, test fork và runtime container **có thể dùng những Java binaries khác nhau**.

Trên Linux/macOS:

```bash
command -v java
command -v javac
java -version
javac -version
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
```

Trên Windows PowerShell:

```powershell
Get-Command java
Get-Command javac
java -version
javac -version
$env:JAVA_HOME
```

Trong Java 11, có thể đọc danh tính runtime trực tiếp:

```java
int feature = Runtime.version().feature();
String patch = System.getProperty("java.runtime.version");
String vendor = System.getProperty("java.vendor");
String vm = System.getProperty("java.vm.name");
String home = System.getProperty("java.home");
String os = System.getProperty("os.name");
String arch = System.getProperty("os.arch");
```

Đây là **đoạn minh họa** cần đặt trong một method Java. `feature` là major (11, 17, 21...), trong khi `java.runtime.version`/`java.vendor` giúp phân biệt patch và vendor. Khi muốn kiểm tra **chính xác một bản JDK đã được phê duyệt**, chỉ kiểm tra feature **chưa đủ**: phải thêm version/build/vendor/image digest theo chính sách triển khai.

**Đừng chỉ tin `JAVA_HOME`**: một script có thể gọi `java` ở `PATH` trước `JAVA_HOME/bin/java`; một build tool có thể chọn toolchain riêng; một container image có thể chứa Java khác hẳn build agent.

Đặc biệt với Kubernetes/container: ghi **image digest**, OS/architecture, CPU quota, memory/cgroup limits, JVM args, truststore, timezone, locale, native libraries và các modules trong image. Một bản JDK 11 của vendor A ở Linux x64 không tự chứng minh một binary khác trên ARM64/Windows có hành vi y hệt.

## 5. Ví dụ hoàn chỉnh: Java 11 API smoke test + fail-fast runtime gate

Chương trình sau **chỉ dùng Java 11 APIs**, không gọi Internet, không cần JUnit hay thư viện bên thứ ba. Nó:

1. Nhận **major JDK kỳ vọng** qua argument.
2. Đọc **major JVM thực sự chạy** bằng `Runtime.version().feature()`.
3. **Fail fast** nếu test chạy nhầm JDK.
4. Kiểm tra một số API Java 11: `String.isBlank`, `String.repeat`, `Optional.isEmpty`, `Files.writeString`/`readString` và `HttpClient`.
5. Ghi/đọc file UTF-8 trong temporary directory rồi tự xóa.
6. Không kết nối tới endpoint ngoài và không in đường dẫn/ngày giờ ngẫu nhiên.

Lưu thành **`DeploymentJdkSmokeTest.java`**:

```java
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;

public final class DeploymentJdkSmokeTest {
    private static void require(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: DeploymentJdkSmokeTest <expectedFeature>");
        }

        int expected = Integer.parseInt(args[0]);
        int actual = Runtime.version().feature();

        System.out.println("runtimeFeature=" + actual);
        System.out.println("expectedFeature=" + expected);
        require(actual == expected,
                "Wrong runtime JDK: expected " + expected
                + ", got " + actual
                + " (" + System.getProperty("java.runtime.version") + ")");
        System.out.println("featureMatch=true");

        require("  ".isBlank(), "String.isBlank unavailable/wrong");
        require("ab".repeat(2).equals("abab"), "String.repeat wrong");
        require(Optional.empty().isEmpty(), "Optional.isEmpty wrong");
        System.out.println("stringApisPassed=true");

        Path p = Files.createTempFile("jdk-api-smoke-", ".txt");
        boolean roundtrip;
        try {
            Files.writeString(p, "Java 11: kiem thu", StandardCharsets.UTF_8);
            roundtrip = Files.readString(p, StandardCharsets.UTF_8)
                    .equals("Java 11: kiem thu");
        } finally {
            Files.deleteIfExists(p);
        }
        require(roundtrip, "Files write/read failed");
        System.out.println("fileRoundtrip=true");

        require(HttpClient.newHttpClient() != null, "HTTP client unavailable");
        System.out.println("httpClientAvailable=true");
    }
}
```

Biên dịch và kiểm tra class file:

```bash
javac --release 11 DeploymentJdkSmokeTest.java
javap -verbose DeploymentJdkSmokeTest
```

Tìm **`major version: 55`** trong output `javap`. Bước này cho biết compiler đã tạo class file Java 11-compatible, **không chứng minh đã chạy trên JVM 11**.

### Chạy trên JDK 11 thực sự

Đảm bảo đường dẫn `JAVA_HOME` là thư mục JDK 11 triển khai rồi gọi:

```bash
"$JAVA_HOME/bin/java" DeploymentJdkSmokeTest 11
```

**Stdout kỳ vọng** khi dùng JDK 11 có các standard modules và quyền ghi temporary directory:

```text
runtimeFeature=11
expectedFeature=11
featureMatch=true
stringApisPassed=true
fileRoundtrip=true
httpClientAvailable=true
```

Không phụ thuộc compiler dùng để biên dịch, một JVM 11 đúng sẽ in `runtimeFeature=11`. Nếu runtime production là JDK 21/25, thay bằng binary runtime tương ứng và đối số expected major tương ứng.

### Kiểm thử đã thực hiện trên OpenJDK 24

Chính mã trên đã **biên dịch bằng `javac --release 11` và chạy thành công trên OpenJDK 24.0.2**:

```bash
javac --release 11 DeploymentJdkSmokeTest.java
java DeploymentJdkSmokeTest 24
```

**Stdout chính xác đã quan sát:**

```text
runtimeFeature=24
expectedFeature=24
featureMatch=true
stringApisPassed=true
fileRoundtrip=true
httpClientAvailable=true
```

`javap` xác nhận `major version: 55`. Điều này chứng minh **API contract được compiler JDK 24 kiểm tra cho Java 11** và smoke test **đã chạy trên JDK 24**. **Không được báo “đã kiểm thử runtime JDK 11”** từ kết quả này: để có kết luận đó, phải chạy trên JDK 11 thật.

### Negative test: sai JDK phải làm CI đỏ

Trên JDK 24, khi cố ý chạy:

```bash
java DeploymentJdkSmokeTest 11
```

hai dòng đầu là:

```text
runtimeFeature=24
expectedFeature=11
```

Sau đó chương trình ném `AssertionError` về runtime mismatch và kết thúc bằng **exit code 1** trong phép thử đã thực hiện. Đây là **hành vi đúng**, không phải vấn đề cần che. Với CI bắt buộc Java 11, không bao giờ thay expected bằng 24 chỉ để làm xanh job.

### Các giới hạn của smoke test này

- `HttpClient.newHttpClient()` không gửi request; **không** chứng minh TLS/truststore, proxy, DNS hoặc HTTP/2 interoperability ở production.
- Không kiểm tra database driver, framework, serialization, JNI, service loaders hay optional modules trong custom runtime.
- `Runtime.version().feature()` chỉ xác minh **major**, không khẳng định đúng patch, vendor, image hoặc security policy.
- Chương trình chỉ chạy một lượt, không là performance/GC/soak test.
- Nó giúp phát hiện **nhầm runtime**; cần thêm integration tests ứng với business API thực tế.

## 6. Khóa JDK trong Maven: compiler khác JVM chạy Surefire

Maven chạy trong một JVM, còn Maven Compiler và Surefire/Failsafe có thể dùng **JDK toolchains khác**. `mvn -version` chỉ phản ánh JVM chạy Maven, không nhất thiết JDK của forked test.

Ví dụ **đoạn cấu hình** trong `pom.xml` hiện có:

```xml
<properties>
    <maven.compiler.release>11</maven.compiler.release>
</properties>
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.15.0</version>
      <configuration>
        <release>11</release>
      </configuration>
    </plugin>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <version>3.6.0</version>
      <configuration>
        <jdkToolchain>
          <version>11</version>
        </jdkToolchain>
      </configuration>
    </plugin>
  </plugins>
</build>
```

Đây **không phải POM độc lập**, cần đặt trong `<project>` có model/dependencies/test framework hợp lệ. Version plugin chỉ là ví dụ, nên dùng version đã được kiểm chứng trong dự án.

**Ý nghĩa từng thành phần:**

- `maven.compiler.release=11` và `<release>11</release>` giới hạn source/API/classfile khi compiler tương thích; không tự chạy tất cả tests bằng JDK 11.
- `maven-surefire-plugin` `<jdkToolchain><version>11` chọn một **test JVM** phù hợp thông qua Maven Toolchains. JDK 11 phải **được phát hiện/khai báo thực sự** (ví dụ `~/.m2/toolchains.xml`).
- Nếu không có JDK 11 toolchain hợp lệ, CI nên **thất bại có nguyên nhân**, không âm thầm chạy tests trên bản JDK khác.
- Với integration tests do **Failsafe** điều khiển, cần chọn tương ứng test JDK và xác minh runtime thực. Một số plugin hoặc build scripts có thể thực thi code ngay trong Maven process, nên vẫn cần phân biệt nơi chạy.

Ví dụ tối giản **`~/.m2/toolchains.xml`** trên hệ thống Unix (thay đường dẫn JDK thật):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>11</version>
    </provides>
    <configuration>
      <jdkHome>/opt/jdks/temurin-11</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
```

Đây là **file cấu hình trên máy/CI**, không phải một file được Maven tự tải chắc chắn theo đường dẫn mẫu. Có thể dùng Maven Toolchains Plugin để discover/select JDK phù hợp theo phiên bản plugin; luôn kiểm tra selection thực tế.

### Assertion trong unit test JUnit (mã minh họa)

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class DeploymentRuntimeTest {
    @Test
    void testJvmIsTheDeployJdk() {
        assertEquals(11, Runtime.version().feature(),
                     "Tests are not running on JDK 11");
    }
}
```

Đây **không phải ví dụ Java SE độc lập**: cần dependency JUnit Jupiter/test engine **còn hỗ trợ JDK 11** và test runner cấu hình đúng. Khi chạy matrix JDK 11/21/25, lấy expected major từ job/config thay vì hardcode 11 cho mọi job.

**Kiểm thử thật:** chạy `mvn test` rồi xác minh Surefire fork dùng executable/toolchain 11 và assertion major bằng 11. Đừng chỉ nhìn “BUILD SUCCESS” khi test plugin bị `skipTests` hoặc test detection sai.

## 7. Khóa Java compiler và test launcher trong Gradle

Gradle có **Java toolchains**, tách JVM chạy build tool khỏi JVM dùng cho compilation và test tasks.

Ví dụ **`build.gradle.kts`** (Kotlin DSL, cần project Java/Gradle cấu hình đầy đủ):

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(11)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(11)
}

tasks.withType<Test>().configureEach {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(11)
    })
}
```

- **Toolchain languageVersion 11** chọn compiler/launcher của Java 11 khi có sẵn/provisioned.
- **`options.release.set(11)`** ngăn dùng APIs mới hơn Java 11.
- **`Test.javaLauncher`** chọn JVM thực sự chạy test workers. Nếu dùng custom `JavaExec` tasks, cần chỉ định launcher tương ứng.
- Gradle toolchains không chứng minh deployment container có cùng runtime; bước image smoke vẫn cần.
- Toolchain resolution phải là một dependency của CI: không tìm được JDK 11 thì **fail** thay vì tự xóa yêu cầu.

**Một chi tiết còn áp dụng ở Gradle 9:** Gradle daemon phải chạy trên **JDK 17+**, nhưng Java toolchains **vẫn dùng JDK 11 để compile và chạy tests**. Không cố ép Gradle 9 daemon chạy JDK 11 để chứng minh Java 11 app compatible — đó là hai JVM khác nhau.

Chạy:

```bash
./gradlew --info test
```

Trên Windows dùng `gradlew.bat --info test`. Kiểm tra logs/launcher đã chọn và thêm assertion `Runtime.version().feature()==11` **bên trong test process**.

### Test thêm trên một JDK khác

Nếu thư viện tuyên bố hỗ trợ Java 11 và Java 21, có thể tạo task riêng để kiểm tra cùng artifact dưới JDK 21 (mã minh họa):

```kotlin
tasks.register<Test>("testOn21") {
    description = "Runs the test suite on JDK 21"
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    })
    testClassesDirs = sourceSets.test.get().output.classesDirs
    classpath = sourceSets.test.get().runtimeClasspath
}
```

Task cần test framework/dependencies và JDK 21 toolchain khả dụng. **Không bỏ `test` chạy JDK 11** chỉ vì task Java 21 xanh: thư viện vẫn cam kết Java 11 minimum.

## 8. Chạy artifact thật trong Docker/container image triển khai

Unit tests có thể chạy trong JDK 11 local nhưng container production thiếu modules, native libraries, CA root, writable directory hoặc quyền network. Vì vậy, kiểm thử nên có **container smoke/integration job** trên **chính runtime image**.

Ví dụ **Dockerfile** đơn giản:

```dockerfile
FROM eclipse-temurin:11-jre
WORKDIR /app
COPY app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Đây là ví dụ cần `app.jar` có thật. Image tag cần xác minh nguồn cung cấp, security updates và hỗ trợ vendor; **production nên pin image digest**, lưu lại digest đã test và deploy đúng digest đó. Đừng suy đoán image tag không đổi sau nhiều tuần.

Ví dụ **lệnh kiểm tra**:

```bash
docker run --rm --entrypoint java your-app-image:tested -version
docker run --rm your-app-image:tested
```

Đây là lệnh minh họa: thay tên image và sử dụng startup/health checks thích hợp với service thực. Nếu ứng dụng là server chạy dài, lệnh thứ hai không tự kết thúc; cần readiness test thay vì chờ mãi.

**Đối chiếu thêm**: OS architecture (`amd64`/`arm64`), timezone, locale, default charset, cgroup CPU/memory, DNS, proxy, JVM args, file permissions, truststore, `-D` properties, environment và TLS/HTTP behavior. Một test trên Windows laptop không chứng minh JNI/.so trong Linux container hoạt động.

### Custom `jlink` images

Một application **compile với `--release 11`** và dùng `java.net.http.HttpClient` có thể fail trên một runtime `jlink` bị **loại module `java.net.http`**. Cũng có thể thiếu `java.sql`, `java.naming`, `jdk.jfr` hoặc security providers tùy yêu cầu.

Dùng `jdeps` để phân tích static module dependencies và dựng image đủ modules, nhưng **vẫn chạy startup và integration tests bằng image cuối**. Reflection, `ServiceLoader`, JNI, class names trong config và frameworks có thể tạo dependencies không thấy rõ trong static analysis. Thành công của `jlink` **không phải** kết luận API runtime PASS.

## 9. Kiểm chứng dependency và multi-release JAR

Một JAR được biên dịch target Java 11 vẫn có thể phụ thuộc một library chỉ hỗ trợ Java 17. Cần kiểm tra **transitive dependencies, test framework, build plugins, agent và optional modules**.

Những trường hợp hay gặp:

| Lỗi | Nguyên nhân điển hình |
| --- | --- |
| `UnsupportedClassVersionError` | Một class thuộc main/dependency có major mới hơn JVM đích |
| `NoSuchMethodError`, `NoSuchFieldError` | API method/field không tồn tại tại runtime hoặc xung đột version library |
| `ClassNotFoundException` | Thiếu JAR, module, classpath hoặc reflection target |
| `NoClassDefFoundError` | Class không thể load/initialize do dependency thiếu hoặc lỗi liên kết trước đó |
| `InaccessibleObjectException` | Reflection vào JDK internals không được module system cho phép |
| `ServiceConfigurationError` | `ServiceLoader` provider/module metadata sai hoặc dependency thiếu |
| `UnsatisfiedLinkError` | JNI/native library không khớp OS/CPU/ABI hoặc không có |
| TLS/SSL handshake/cert errors | Khác truststore, provider, cipher/proxy hoặc network |
| Runtime exit khác 0 khi JVM flags được truyền | Flag lỗi thời/không hỗ trợ trong JDK đích |

**Multi-release JAR** có thể chứa các implementations trong `META-INF/versions/*` để JVM chọn theo version. Cùng một JAR chạy trên Java 11 và Java 24 **có thể tải các class variants khác nhau**. Do đó test trên Java 24 không bảo đảm nhánh class mà Java 11 thực sự chọn.

Các công cụ hỗ trợ:

```bash
jdeps --multi-release 11 --print-module-deps app.jar
jdeps --jdk-internals app.jar
```

Đây là mẫu lệnh trên một JAR có thật. `jdeps` có ích để xem dependencies và tham chiếu tới API nội bộ, nhưng **không đảm bảo phát hiện mọi reflection, JNI hoặc ServiceLoader**. Nếu một dependency dùng Java 17 APIs qua reflection chỉ ở một code path ít chạy, cần integration tests tương ứng.

## 10. Những nhóm kiểm thử bắt buộc tùy ứng dụng

**API compile smoke** kiểm tra có dùng method/classes phù hợp release. **Runtime tests** còn phải thực thi những đường code thật sự nhạy với JDK:

- **HTTP/TLS:** TLS version, truststore/CA roots, proxy, hostname verification, cipher suites, HTTP/2 negotiation; không tắt certificate validation chỉ để test pass.
- **Database/JDBC:** Driver còn hỗ trợ Java 11, network auth, pool behavior, TLS settings và đúng schema DB.
- **Reflection/JPMS:** Module opens/exports cần thiết, frameworks mapping/serialization, dynamic proxies và annotation processing.
- **Files/OS:** UTF-8 và default encoding, permissions, paths/case-sensitivity, temp directories, file watchers, symlinks và filesystem limits.
- **Native/JNI:** Architecture, ABI, shared libraries và native transports trên runtime image.
- **Concurrency/time:** Scheduling, virtual time tests, time zones/DST, clocks, executor/thread behavior; không assert thời gian chính xác tuyệt đối khi JVM scheduling khác.
- **Observability:** JFR/GC events, log flags, metrics và exit/status behavior theo JDK đang triển khai.
- **Security:** JDK patch updates, providers, truststore/certificates, license/policy và quyền truy cập.
- **Performance:** p95/p99 latency, GC pauses, CPU, RSS/heap, throughput, memory pressure và stability dưới tải.

**Không kéo theo mã legacy để “cứu” test.** Ví dụ CMS `UseConcMarkSweepGC` đã bị loại trên JDK hiện đại; finalizer, private JDK internals và các module hacks không phải phương án mới được khuyến nghị. Chỉ đưa những APIs/flags còn áp dụng ở phiên bản đang dùng vào cấu hình thật.

## 11. CI matrix: kiểm thử JDK tối thiểu và JDK sẽ deploy

Một test matrix tốt đi theo **hợp đồng hỗ trợ**, không phải theo danh sách JDK sẵn có tình cờ trên máy.

| Trường hợp | Test bắt buộc | Test bổ sung |
| --- | --- | --- |
| App deploy **chỉ JDK 11** | `--release 11` + full tests trên đúng JDK 11 image/vendor/patch | Preview compatibility trên JDK mới trước upgrade |
| Library tuyên bố hỗ trợ **Java 11+** | Compile target11, test JVM11 | JVM 17/21/25 và các version khách hàng sử dụng |
| App compile target11 nhưng deploy **JDK 21** | Test thực trên JDK21 deployment image | Thử JVM11 nếu còn cam kết runtime minimum11 |
| App chỉ hỗ trợ **JDK 21+** | Compile target21 và chạy test JDK21 | Thử các JDK mới phù hợp chính sách hỗ trợ |

Một pipeline mẫu (pseudo-workflow, không phải cú pháp của hệ thống CI cụ thể):

```text
1. source/API gate:
   javac --release 11
   verify major version 55 and dependency compatibility

2. minimum-runtime gate:
   run unit/integration tests on JDK 11
   assert Runtime.version().feature() == 11

3. deployed-runtime gate:
   start packaged artifact in the actual deployment image
   run health/API/TLS/DB/permission tests

4. compatibility matrix:
   test the same artifact on other promised JDK versions

5. release:
   report exact artifact checksum, JDK vendor/patch/build/image digest
   fail if a mandatory gate is missing or FAIL
```

**“NOT TESTED” không phải PASS.** Nếu CI chỉ có JDK 24, đúng ra phải báo “Java 11 source/API target PASS; runtime JDK24 PASS; runtime JDK11 NOT TESTED”. Không được chuyển trạng thái đó thành “Java 11 runtime PASS” cho tới khi job JVM 11 thực chạy thành công.

Nếu test trên patch khác với runtime sẽ deploy, cân nhắc thêm smoke test cho binary/image digest mới, nhất là khi cập nhật CA roots, security providers, OS libraries hoặc container image. Major version giống nhau không bảo đảm patch-level behavior giống hoàn toàn.

## 12. Cách đọc kết quả kiểm thử đúng ngữ nghĩa

Giả sử có ba lượt:

```text
A. JDK24 javac --release 11:   PASS
B. JDK24 java app smoke:       PASS
C. JDK11 java app smoke:       NOT RUN
```

**Kết luận đúng:** API/bytecode Java 11 được kiểm tra ở compiler, smoke runtime JDK 24 được kiểm tra; **chưa đủ bằng chứng để deploy JDK11**.

Giả sử lượt C chạy và thành công:

```text
A. Java11 source/API:       PASS
B. Classfile major55:       PASS
C. Unit JVM11:              PASS
D. Integration JVM11 image: PASS
E. Release dependencies:    PASS
```

Khi đó có cơ sở cho kết luận về Java 11 deployment theo **phạm vi test đã chạy**. Vẫn không suy thành “không có bất kỳ lỗi trên mọi workload” hoặc “mọi bản cập nhật JDK11 đều giống nhau”.

Nếu mục tiêu runtime JDK21, thay runtime checks bằng JDK21; giữ riêng minimum-compatibility test nếu sản phẩm vẫn hứa hỗ trợ JVM11.

## 13. Lỗi phổ biến và cách sửa

| Sai lầm | Vì sao không đủ / sai | Khắc phục |
| --- | --- | --- |
| Compile `--release 11` rồi kết luận “JDK11 đã được test” | JVM11 chưa chạy | Chạy unit/integration JVM11 thực |
| Chỉ đặt `sourceCompatibility/targetCompatibility=11` | Không tự khóa Java 11 APIs | Dùng `--release 11` |
| `mvn -version` báo Java11 nên nghĩ Surefire chắc chắn Java11 | Surefire forks có thể dùng toolchain khác | Assert feature trong test JVM |
| `java -version` trên laptop được dùng để suy production | Container/IDE/CI dùng Java binary khác | Ghi đường dẫn và version của runtime thực |
| Main.class major55 nên tin mọi dependency cũng major55 | Transitive deps có thể newer | Kiểm tra dependency graph/JAR packaging |
| Test library trên JVM24 và công bố hỗ trợ Java11 | Multi-release JAR và API mới có thể khác | Test JVM11 minimum |
| Gradle 9 yêu cầu JDK17+, nên kết luận không thể test Java11 | Daemon JVM khác toolchain JVM | Dùng Gradle toolchain11 cho tests |
| Test khởi tạo HttpClient rồi tuyên bố TLS/HTTP2 đã pass | Chưa gửi request | Tạo integration test với endpoint/certs thật |
| Chỉ test trên host, không test container | OS/native/image/module có thể khác | Test deployment image |
| Bỏ các flags JDK sai bằng `IgnoreUnrecognizedVMOptions` | Che giấu cấu hình deploy sai | Fail fast, sửa flags |
| Dùng internal JDK APIs/reflection hacks để compile | Không có hợp đồng stable | Dùng public documented API và dependency được duy trì |
| Unit test bị skip nhưng pipeline vẫn xanh | Không có bằng chứng runtime | Kiểm tra test discovery/counts, fail khi thiếu tests |
| Tests phụ thuộc timezone/locale/charset mặc định | JDK/OS image có thể khác | Cấu hình explicit và thử môi trường thật |
| Bật smoke test kiểm tra patch bằng đúng major thôi | Major không đủ để xác minh vendor/patch | Assert thêm version/vendor nếu cần |
| Một upgrade image tag được cho là không đổi | Tag có thể trỏ digest mới | Pin digest và chạy regression smoke |

## 14. Checklist phát hành

```text
[ ] Xác định Java API level, minimum JDK và JDK dự kiến deploy
[ ] Ghi JDK exact version/vendor/build/VM, OS/arch, image digest
[ ] Biên dịch với --release phù hợp
[ ] Kiểm tra classfile major version và dependencies
[ ] Chạy unit tests bằng Java toolchain tương ứng
[ ] Assert Runtime.version().feature() từ test process
[ ] Chạy integration tests với DB/HTTP/TLS/native/runtime modules
[ ] Chạy artifact trong image có cùng JDK/flags/permissions với deploy
[ ] Kiểm tra ServiceLoader, JPMS, reflection và multi-release JAR
[ ] Chạy test matrix trên minimum supported và actual deployed JDK
[ ] Đo performance/GC khi cần và lưu logs, metrics
[ ] Không đánh dấu PASS cho job còn NOT TESTED hoặc bị skip
[ ] Lưu artifact checksum, toolchain info, test results và rollback plan
```

**Điều kiện “DONE” cho Java 11 runtime:** compilation target 11 thành công, tests bắt buộc thực sự chạy trên JDK 11 image mục tiêu, dependency/module/OS integration checks đạt và báo cáo ghi rõ binary/version đã thử. Không suy ra điều đó từ một dòng `major version: 55`.

## 15. Câu hỏi tự kiểm tra

**Câu 1:** `javac --release 11` thành công có chứng minh đã test trên JVM11 không?

**Đáp án:** Không. Nó kiểm tra source/API/classfile theo Java11. Runtime11 phải thực thi test.

**Câu 2:** Tại sao `-source 11 -target 11` có thể vẫn cho gọi `String.formatted` trên JDK24?

**Đáp án:** Hai option đó không tự giới hạn system APIs về JDK11; `--release 11` chặn API được thêm sau Java11.

**Câu 3:** Classfile major 55 tương ứng phiên bản nào?

**Đáp án:** Java11; nó vẫn không chứng minh tất cả transitive JARs/APIs phù hợp.

**Câu 4:** Kiểm tra JDK của Surefire bằng `mvn -version` đã đủ chưa?

**Đáp án:** Chưa. Cần kiểm tra test fork/toolchain, tốt nhất assert `Runtime.version().feature()` bên trong một test đang chạy.

**Câu 5:** Gradle 9 cần JDK17+ để chạy daemon, vậy có thể biên dịch/test app Java11 không?

**Đáp án:** Có. Chạy Gradle daemon trên JDK17+, chọn JDK11 qua Java toolchain cho compiler/test tasks.

**Câu 6:** `HttpClient.newHttpClient() != null` chứng minh TLS production hoạt động chưa?

**Đáp án:** Chưa. Phải thử endpoint thật, truststore, proxy/DNS, TLS settings và network policy.

**Câu 7:** Vì sao multi-release JAR cần test trên JVM11 và JVM21 nếu thư viện hỗ trợ cả hai?

**Đáp án:** JVM có thể chọn class variant khác nhau theo runtime version, dẫn tới API/hành vi khác.

**Câu 8:** Runtime smoke trên JDK24 và compile `--release 11` đều PASS. Có thể ghi “runtime JDK11 PASS” không?

**Đáp án:** Không. Ghi “API Java11 PASS, runtime JDK24 PASS, runtime JDK11 NOT TESTED” nếu chưa chạy thật trên 11.

**Câu 9:** Nếu app chỉ deploy JDK21 nhưng compile target Java11, phải test runtime nào?

**Đáp án:** JDK21 actual deployment. Thêm JDK11 nếu còn cam kết khả năng chạy ngược tới Java11.

**Câu 10:** Vì sao test trên đúng major JDK vẫn chưa nhất thiết đủ cho một upgrade production?

**Đáp án:** Vendor, patch, OS/architecture, container image, truststore/providers và JVM flags cũng thay đổi; cần đối chiếu đúng image/version và chạy smoke/regression theo rủi ro.

**Ghi nhớ:** Kiểm chứng API Java 11+ có **hai khóa khác nhau**: `--release 11` cho **cú pháp/API/classfile** và **JDK runtime thực** cho **unit/integration tests**. Maven Compiler `release`, Surefire `jdkToolchain`, Gradle `Test.javaLauncher`, container runtime image và các tests phải được cấu hình/đối chiếu độc lập. Đừng đồng nhất JDK chạy build tool với JDK chạy test; đừng kết luận “JDK11 đã kiểm thử” chỉ từ chương trình được compile target11 rồi chạy trên JDK24. Đối chiếu minimum supported JDK, deployed JDK và phiên bản thực tế của dependencies.

**Tài liệu chính thức còn áp dụng:** [Oracle Java SE 11 — javac](https://docs.oracle.com/en/java/javase/11/tools/javac.html); [Oracle Java SE 26 — javac --release](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html); [Maven Compiler Plugin — Setting the --release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html); [Maven Surefire — Toolchains](https://maven.apache.org/surefire/maven-surefire-plugin/examples/toolchains.html); [Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains); [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html); [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html); [Oracle Java SE 11 — java tool](https://docs.oracle.com/en/java/javase/11/tools/java.html).
