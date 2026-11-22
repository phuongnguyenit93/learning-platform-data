# Cấu hình JVM chạy unit test, integration test và tác vụ JavaExec

Trong một dự án Java, lệnh `mvn test` hoặc `./gradlew test` có thể hoàn thành với trạng thái thành công nhưng chưa chắc các bài test đã chạy trên đúng JDK mà sản phẩm cần hỗ trợ. Một lý do là **JVM chạy build tool**, **JDK dùng để biên dịch** và **JVM thực thi test hoặc ứng dụng** không nhất thiết là cùng một Java installation.

Vấn đề trở nên đặc biệt quan trọng khi migration từ JDK cũ sang JDK mới. Nhóm có thể build bằng JDK 21 nhưng cần kiểm thử artifact trên Java 17; unit test cần heap nhỏ và timezone cố định, integration test cần biến môi trường riêng; một tác vụ JavaExec lại phải chạy bằng Java 21 thay vì JVM đang chạy Gradle. Nếu chỉ đổi `JAVA_HOME` hoặc cấu hình `--release`, rất dễ tạo ra kết quả kiểm thử thiếu tin cậy.

Bài học này giải thích các tầng JVM trong Maven và Gradle, cách chọn JDK cho unit test, integration test và tác vụ thực thi Java; cách truyền JVM arguments, system properties và environment variables; cùng quy trình kiểm chứng runtime thực tế trên máy phát triển và CI.

## 1. Một dự án có thể dùng nhiều JVM

Hình dung một pipeline:

```text
                      CI agent / developer shell
                                 |
                     +-----------+-----------+
                     |                       |
                  Maven JVM              Gradle JVM
                     |                       |
             Compiler / toolchains    Compiler / toolchains
                     |                       |
               Test JVM fork            Test JVM fork
                     |                       |
                Integration              Integration
                 Test JVM                 Test JVM
                                             |
                                      JavaExec JVM
```

Đây là mô hình khái niệm, không có nghĩa mọi build luôn tạo ra từng process riêng. Maven Surefire/Failsafe có chế độ fork hoặc không fork; Gradle `Test` và `JavaExec` thường chạy Java code bằng process JVM riêng, trong khi một số tác vụ khác thực thi logic trực tiếp trong JVM của Gradle.

Các vai trò cần phân biệt:

| Vai trò | Ví dụ | Câu hỏi phải xác nhận |
|---|---|---|
| **Build-tool JVM** | JVM chạy Maven hoặc Gradle Daemon. | Maven/Gradle được khởi động bằng JDK nào? |
| **Compiler JDK** | `javac`, toolchain hoặc compiler plugin. | Class file đang được biên dịch bằng compiler nào? |
| **Unit-test JVM** | Forked process của Surefire hoặc Gradle `Test`. | Unit test thực sự chạy trên Java 17 hay 21? |
| **Integration-test JVM** | Fork của Failsafe hoặc custom Gradle `Test`. | Test tích hợp dùng JDK, flags, credentials và endpoint nào? |
| **Application JVM** | Process chạy service trong production. | Artifact có thực sự chạy trên baseline runtime được cam kết không? |
| **JavaExec JVM** | Tác vụ `JavaExec` chạy main class từ Gradle. | Tác vụ nghiệp vụ/dữ liệu được chạy bằng launcher nào? |

**Nguyên tắc:** Biết JDK biên dịch không đồng nghĩa biết JDK thực thi. Biết JDK đang chạy Maven/Gradle cũng không đồng nghĩa mọi test và JavaExec đã dùng JDK đó.

## 2. Ba lớp cấu hình: executable, JVM options và application options

Nhiều lỗi xảy ra vì nhầm ba loại tham số.

### 2.1. Chọn Java executable hoặc launcher

Ví dụ:

```text
C:/jdks/jdk-17/bin/java.exe
C:/jdks/jdk-21/bin/java.exe
```

Đây là quyết định **JDK nào chạy process**. Trong Gradle nên dùng Java Toolchains và `javaLauncher`; trong Maven có thể dùng Toolchains hoặc cơ chế cấu hình JVM riêng của plugin, tùy goal.

### 2.2. Chọn JVM arguments

Ví dụ:

```bash
-Xms128m
-Xmx512m
-Duser.timezone=UTC
--add-opens=java.base/java.lang=ALL-UNNAMED
```

Đây là tham số JVM, cần được đưa vào **đúng process chạy code**. Nếu test chạy trong JVM fork thì thêm `-Xmx512m` cho Maven/Gradle process chưa chắc tác động tới fork đó.

Các flags như `--add-opens` là giải pháp mở package cho reflection; chỉ dùng khi thực sự cần và có kế hoạch bỏ phụ thuộc vào JDK internals.

### 2.3. Chọn application arguments

Ví dụ:

```bash
--config=config/test.yml
--dry-run
--limit=100
```

Đây là các chuỗi được chuyển tới `main(String[] args)`, không phải JVM options. Với Gradle `JavaExec`, dùng `args(...)` cho chúng; dùng `jvmArgs(...)` cho JVM flags.

### 2.4. System property khác environment variable

```java
String profile = System.getProperty("app.profile");
String serviceUrl = System.getenv("SERVICE_URL");
```

Chúng đến từ hai không gian cấu hình khác nhau:

- System property: thường đặt bằng `-Dapp.profile=test`, Gradle `systemProperty(...)` hoặc cấu hình plugin Maven.
- Environment variable: do process cha truyền vào hoặc được cấu hình bằng `environment(...)` / `environmentVariables`.

Không mặc định rằng `-Dapp.profile=test` tạo ra `APP_PROFILE`; cũng không mặc định mọi environment variable được tự chuyển thành system property.

## 3. In runtime thực tế từ bên trong test

Để xác nhận JDK mà test đang sử dụng, cách trực tiếp nhất là in hoặc assert dữ liệu **ngay trong JVM chạy test**:

```java
import java.nio.charset.Charset;
import java.time.ZoneId;
import java.util.Locale;

public final class RuntimeDiagnostics {
    public static void print() {
        System.out.println("java.version = "
                + System.getProperty("java.version"));
        System.out.println("java.vendor = "
                + System.getProperty("java.vendor"));
        System.out.println("java.home = "
                + System.getProperty("java.home"));
        System.out.println("java.vm.name = "
                + System.getProperty("java.vm.name"));
        System.out.println("java.class.version = "
                + System.getProperty("java.class.version"));
        System.out.println("file.encoding = "
                + System.getProperty("file.encoding"));
        System.out.println("default charset = "
                + Charset.defaultCharset());
        System.out.println("timezone = " + ZoneId.systemDefault());
        System.out.println("locale = " + Locale.getDefault());
        System.out.println("profile = "
                + System.getProperty("app.profile"));
        System.out.println("service url = "
                + System.getenv("SERVICE_URL"));
    }
}
```

Với JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class RuntimeTest {
    @Test
    void usesJava17() {
        RuntimeDiagnostics.print();

        assertEquals(17, Runtime.version().feature());
    }
}
```

Chỉ dùng assertion Java 17 nếu test suite này **thực sự được cấu hình để chạy trên Java 17**. Nếu mục đích là test đa JDK, thay bằng ràng buộc tương thích hoặc parameterization phù hợp.

Một bản ghi duy nhất từ `java -version` ngoài terminal không thay thế kiểm tra trong test process. Điều quan trọng là `System.getProperty("java.home")` và `Runtime.version()` trong đúng process.

## 4. Maven: JDK chạy Maven khác JVM chạy Surefire

Maven được khởi động bằng Java executable do Maven launcher/environment chọn. Kiểm tra:

```bash
mvn -version
```

Kết quả thường cho biết Maven version, Java version, Java home và OS. Tuy nhiên, khi Maven Surefire Plugin tạo fork JVM khác, `mvn -version` **không đủ** để xác nhận JDK của unit test.

Các nguồn cấu hình có vai trò khác nhau:

| Cấu hình | Tác động chính |
|---|---|
| `JAVA_HOME` / PATH | Ảnh hưởng cách launcher chọn JVM khi khởi động Maven, tùy môi trường. |
| `MAVEN_OPTS` | JVM arguments cho Maven process; không phải cách đáng tin cậy để đặt riêng mọi test fork. |
| `.mvn/jvm.config` | JVM arguments cho Maven process theo cơ chế launcher Maven; không nên coi là cấu hình riêng Surefire. |
| Maven Compiler Plugin | Kiểm soát biên dịch và có thể chọn JDK/toolchain. |
| Maven Surefire Plugin | Chạy unit tests theo cấu hình fork, JVM, `argLine`, properties. |
| Maven Failsafe Plugin | Chạy integration tests trong vòng đời `integration-test` và `verify`. |
| Maven Toolchains | Cho plugin có hỗ trợ lựa chọn JDK theo metadata thay vì phụ thuộc duy nhất JVM Maven. |

### 4.1. `--release` không quyết định JVM test

Ví dụ:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Thuộc tính này yêu cầu tạo mã phù hợp release 17 khi Maven Compiler Plugin hỗ trợ cấu hình tương ứng. Nó **không tự bảo đảm** unit test, integration test hay ứng dụng chạy bằng Java 17.

Nếu Maven chạy bằng Java 21 và Surefire không được chọn toolchain riêng, test có thể vẫn chạy trong Java 21 dù code đã được biên dịch cho Java 17.

## 5. Maven Surefire: JVM cho unit test

Maven Surefire Plugin thường dùng để thực thi unit tests ở pha `test` của Maven lifecycle. Một cấu hình mẫu:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <version>3.5.2</version>
      <configuration>
        <forkCount>1</forkCount>
        <reuseForks>true</reuseForks>
        <argLine>-Xmx512m -Duser.timezone=UTC</argLine>
        <systemPropertyVariables>
          <app.profile>unit-test</app.profile>
        </systemPropertyVariables>
        <environmentVariables>
          <SERVICE_URL>http://localhost:18080</SERVICE_URL>
        </environmentVariables>
      </configuration>
    </plugin>
  </plugins>
</build>
```

Phiên bản plugin ở đây là ví dụ dùng để trình bày cú pháp, không phải lời khẳng định đó là bản mới nhất. Khi áp dụng thực tế, chọn phiên bản được dự án và JDK mục tiêu hỗ trợ.

Giải thích:

- `forkCount=1`: cho phép tối đa một fork JVM chạy test tại một thời điểm cho module tương ứng.
- `reuseForks=true`: tái sử dụng fork theo chính sách Surefire.
- `argLine`: truyền JVM options tới **forked JVM**.
- `systemPropertyVariables`: thiết lập system properties trong test process.
- `environmentVariables`: cấu hình environment variables cho forked process.

`forkCount` có thể nhận các giá trị như `1C` theo khả năng của plugin để liên hệ số fork với số core. Chỉ tăng số fork sau khi kiểm tra tính cô lập của test, database, port và tài nguyên CI.

### 5.1. Có nên đặt `forkCount=0` không?

Với `forkCount=0`, Surefire chạy test trong Maven JVM thay vì fork JVM riêng. Khi đó bạn mất ranh giới process và một số cấu hình dành cho fork (như chọn executable hoặc `argLine`) không còn mang tác dụng như mong đợi.

Trong migration, nên ưu tiên test JVM fork riêng nếu cần:

- Kiểm chứng JDK runtime khác JVM Maven.
- Cô lập system properties hoặc classloader.
- Áp dụng `--add-opens` hoặc heap flags riêng cho test.
- Xử lý leak, shutdown hooks hoặc lỗi gây ảnh hưởng sang Maven process.

Không nên dùng `forkCount=0` chỉ để tránh lỗi launch; hãy tìm nguyên nhân cấu hình JVM/toolchain không phù hợp.

### 5.2. Chọn JDK cho fork bằng `jdkToolchain`

Surefire hỗ trợ chọn toolchain JDK cho các fork:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <version>3.5.2</version>
  <configuration>
    <forkCount>1</forkCount>
    <jdkToolchain>
      <version>17</version>
    </jdkToolchain>
    <argLine>-Xmx512m</argLine>
  </configuration>
</plugin>
```

Điều kiện là Maven có thể tìm thấy toolchain phù hợp, chẳng hạn thông qua `~/.m2/toolchains.xml` hoặc khả năng discovery tương ứng với plugin/toolchain version đã chọn. Chọn JDK bằng toolchain giúp tránh phụ thuộc vào `JAVA_HOME` của shell.

Nếu đồng thời đặt một executable JVM rõ ràng bằng cấu hình plugin, cần kiểm tra quy tắc ưu tiên của chính phiên bản Surefire đang dùng; không cấu hình hai nguồn chọn JVM trái nhau rồi suy đoán kết quả.

### 5.3. Chỉ định JVM executable bằng `jvm`

Một cấu hình khác khi thực sự muốn khóa đường dẫn executable:

```xml
<configuration>
  <forkCount>1</forkCount>
  <jvm>/opt/jdks/jdk-17/bin/java</jvm>
</configuration>
```

Đường dẫn trên là ví dụ Linux. Cách này có thể phù hợp cho môi trường cố định nhưng khó di chuyển giữa Windows, Linux và nhiều CI agents. Thường nên ưu tiên Toolchains khi cần tính di động.

## 6. Maven Failsafe: JVM cho integration test

Maven Failsafe Plugin được thiết kế cho integration tests và thường gắn vào hai pha:

- `integration-test`: chạy integration tests và ghi kết quả.
- `verify`: kiểm tra kết quả và làm build thất bại nếu có test lỗi.

Điểm quan trọng là chạy tới `verify`, ví dụ `mvn verify`. Chỉ gọi `mvn integration-test` có thể không thực hiện toàn bộ bước kiểm tra kết quả theo cách người dùng mong muốn.

### 6.1. Cấu hình Failsafe

```xml
<build>
  <plugins>
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
      <configuration>
        <forkCount>1</forkCount>
        <reuseForks>true</reuseForks>
        <jdkToolchain>
          <version>21</version>
        </jdkToolchain>
        <argLine>-Xmx1g -Duser.timezone=UTC</argLine>
        <systemPropertyVariables>
          <app.profile>integration-test</app.profile>
        </systemPropertyVariables>
        <environmentVariables>
          <SERVICE_URL>http://localhost:19090</SERVICE_URL>
        </environmentVariables>
      </configuration>
    </plugin>
  </plugins>
</build>
```

Ví dụ cố tình chọn Java 21 cho integration-test fork để minh họa việc unit test và integration test có thể chạy ở hai JDK khác nhau. Không phải mọi dự án cần cách chia này; nó chỉ có ý nghĩa khi có mục tiêu kiểm thử cụ thể.

Theo conventions của Failsafe, các tên như `*IT.java`, `IT*.java` hoặc `*ITCase.java` thường được nhận diện là integration tests. Điều này có thể được tùy chỉnh bằng `includes` và `excludes`. Hãy bảo đảm quy ước đặt tên của dự án phù hợp với plugin, tránh tình trạng “build xanh vì không có test nào được tìm thấy”.

### 6.2. Không để unit test và integration test dùng chung cấu hình ngoài ý muốn

Unit tests thường cần:

- Chạy nhanh, tách khỏi network và database.
- Fixtures in-memory hoặc test doubles.
- Cấu hình ổn định, ít phụ thuộc môi trường.

Integration tests thường cần:

- Database/service thật hoặc test containers.
- Environment variables và credentials của môi trường thử nghiệm.
- Timeout lớn hơn; có thể cần thêm bộ nhớ.
- Cleanup resources sau mỗi bài test hoặc test suite.

Nên tạo chính sách rõ: cái gì được chia sẻ (ví dụ timezone, encoding), cái gì tách biệt (service endpoints, credentials, heap, parallelism). Không đưa secret thật vào `pom.xml`; cung cấp qua secret manager/CI environment và tránh in vào logs.

### 6.3. Phân biệt Maven lifecycle với thời điểm khởi động dịch vụ

Nếu integration tests cần một server chạy sẵn, phải bảo đảm service/database được khởi động ở pha thích hợp và dọn dẹp cả khi test thất bại. Không nên chỉ gọi một tiến trình background bằng shell mà không có cơ chế chờ readiness/cleanup.

Một số dự án dùng container orchestration, Testcontainers hoặc plugin Maven chuyên dụng. Cơ chế cụ thể thay đổi theo kiến trúc, nhưng mục tiêu luôn là test có input và endpoint xác định, không tình cờ kết nối đến production.

## 7. Maven Toolchains: cách khai báo nhiều JDK

Maven Toolchains giúp một số plugin có thể dùng JDK khác với JDK đã khởi động Maven. Một ví dụ cấu trúc `~/.m2/toolchains.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17</version>
    </provides>
    <configuration>
      <jdkHome>/opt/jdks/jdk-17</jdkHome>
    </configuration>
  </toolchain>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>21</version>
    </provides>
    <configuration>
      <jdkHome>/opt/jdks/jdk-21</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
```

Đường dẫn mang tính minh họa. Trong dự án thật, file toolchains phải phản ánh JDK installations có thật trên từng máy hoặc runner. Với một số bản Maven Toolchains Plugin mới, có khả năng discovery khác; cần xác nhận plugin và cách phát hiện JDK trong tổ chức.

Trong `pom.xml`, Maven Toolchains Plugin có thể yêu cầu toolchain cho những plugin có tích hợp với nó. Ví dụ:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-toolchains-plugin</artifactId>
  <version>3.2.0</version>
  <executions>
    <execution>
      <goals>
        <goal>toolchain</goal>
      </goals>
    </execution>
  </executions>
  <configuration>
    <toolchains>
      <jdk>
        <version>17</version>
      </jdk>
    </toolchains>
  </configuration>
</plugin>
```

Cấu hình trên mô tả **toolchain mặc định được chọn cho plugin tương thích**; Surefire và Failsafe có thể chỉ định `jdkToolchain` riêng để chọn JDK khác nếu plugin hỗ trợ. Vì vậy, khi thấy ba version trong build, phải xác định plugin nào sử dụng version nào thay vì coi toolchain của compiler là JDK của tất cả test.

**Giới hạn quan trọng:** Một plugin Maven không tự động tôn trọng Toolchains chỉ vì dự án có file `toolchains.xml`. Plugin cần hỗ trợ cơ chế đó, hoặc phải được cấu hình executable cụ thể.

## 8. Maven: phân biệt `exec:java` và `exec:exec`

Trong Maven, Apache Exec Maven Plugin cung cấp hai goal hay bị nhầm:

| Goal | Cách thực thi | Có chọn JVM process độc lập không? |
|---|---|---|
| `exec:java` | Chạy main class trong JVM đang chạy Maven, với classloader/thread handling của plugin. | Không fork một JVM Java mới theo cách `exec:exec`. |
| `exec:exec` | Chạy executable bên ngoài do plugin chỉ định. | Có thể chạy một `java` executable cụ thể để tạo JVM riêng. |

Đây là điểm tương đồng với Gradle `JavaExec` nhưng **không hoàn toàn đồng nhất**. Trong Gradle, `JavaExec` được thiết kế để khởi động process Java riêng. Maven `exec:java` lại chạy trong Maven JVM.

### 8.1. `exec:java` và tác động của Maven JVM

```xml
<plugin>
  <groupId>org.codehaus.mojo</groupId>
  <artifactId>exec-maven-plugin</artifactId>
  <version>3.5.1</version>
  <configuration>
    <mainClass>com.example.tools.MigrationTool</mainClass>
  </configuration>
</plugin>
```

Khi gọi:

```bash
mvn exec:java
```

main class dùng JVM của Maven. Các JVM arguments như heap hoặc `--add-opens` cần được đưa vào JVM Maven từ lúc startup; không thể coi `exec:java` là một JVM fork hoàn toàn độc lập với cấu hình runtime riêng.

Để chạy một công cụ cần JDK khác, hoặc muốn tách memory/flags khỏi Maven, hãy dùng một process ngoài.

### 8.2. `exec:exec` chạy `java` riêng

Ví dụ cấu hình lệnh Java ngoài:

```xml
<plugin>
  <groupId>org.codehaus.mojo</groupId>
  <artifactId>exec-maven-plugin</artifactId>
  <version>3.5.1</version>
  <configuration>
    <executable>${env.MIGRATION_JAVA_HOME}/bin/java</executable>
    <arguments>
      <argument>-Xmx512m</argument>
      <argument>-Dapp.mode=dry-run</argument>
      <argument>-classpath</argument>
      <classpath/>
      <argument>com.example.tools.MigrationTool</argument>
      <argument>--dry-run</argument>
    </arguments>
  </configuration>
</plugin>
```

`MIGRATION_JAVA_HOME` là biến môi trường ví dụ chứa thư mục JDK của công cụ. `<classpath/>` là thành phần đặc biệt của Exec Plugin cho phép plugin ghép project classpath phù hợp. Trong build thực tế, cần xác định scope classpath và đảm bảo class `MigrationTool` được biên dịch trước khi gọi goal.

Khi thực thi Java process bên ngoài, thứ tự tham số là:

```text
java [JVM options] -classpath [classpath] MainClass [application args]
```

Nếu project modular, có thể cần `--module-path` và `--module module/mainClass` thay cho classpath. Không tự giả định plugin sẽ dựng module path phù hợp khi dùng JavaExec/exec từ cấu hình classpath.

## 9. Gradle: JVM chạy Gradle khác Java Toolchain

Gradle có thể chạy trong Gradle Daemon JVM, còn các Java compilation/test/execution tasks có thể sử dụng JDK khác thông qua Java Toolchains.

Kiểm tra Gradle:

```bash
./gradlew --version
```

Kết quả cho biết Gradle version và thông tin JVM liên quan của Gradle. Với Gradle mới, cách hiển thị “Launcher JVM” và “Daemon JVM” có thể khác, nên đọc toàn bộ output. Nhưng lệnh này **chưa xác nhận JVM của từng test task**.

### 9.1. Các cách chọn JVM cho Gradle

| Cơ chế | Chủ yếu tác động tới |
|---|---|
| `JAVA_HOME` / PATH | Cách Gradle wrapper/client được khởi động, tùy môi trường. |
| `org.gradle.java.home` | JDK chạy Gradle Daemon trong các cấu hình được hỗ trợ. |
| Gradle Daemon JVM criteria | Tiêu chí chọn Daemon JVM ở phiên bản Gradle có hỗ trợ. |
| `java.toolchain` | Compiler, launcher và toolchain dùng bởi các task Java có tích hợp. |
| `Test.javaLauncher` | JDK chạy forked test process của một `Test` task. |
| `JavaExec.javaLauncher` | JDK chạy Java process do tác vụ `JavaExec` tạo. |
| `Test.jvmArgs` / `JavaExec.jvmArgs` | JVM flags cho task tương ứng. |

Gradle version phải tương thích với JDK chạy Gradle Daemon. **Không thể chọn một JDK bất kỳ chỉ vì toolchain target hỗ trợ phiên bản đó**; cần kiểm tra Gradle Java compatibility matrix của đúng Gradle release.

### 9.2. Thiết lập toolchain cho Java project

Ví dụ `build.gradle.kts`:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

Ví dụ chọn JDK 17 làm toolchain mặc định của Java project. Compiler và các task Java có tích hợp toolchain thường lấy version này nếu không cấu hình override.

Nếu cần kiểm soát API đích khi compile bằng JDK mới:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

`options.release` kiểm soát ngôn ngữ/bytecode/API target qua `javac --release`; nó **không chọn JVM thực thi unit test hoặc JavaExec**.

## 10. Gradle `Test`: JVM cho unit tests

Ví dụ cấu hình Kotlin DSL:

```kotlin
import org.gradle.jvm.toolchain.JavaLanguageVersion

plugins {
    java
}

tasks.test {
    useJUnitPlatform()

    javaLauncher.set(
        javaToolchains.launcherFor {
            languageVersion.set(JavaLanguageVersion.of(17))
        }
    )

    jvmArgs("-Xmx512m")
    systemProperty("app.profile", "unit-test")
    systemProperty("user.timezone", "UTC")
    environment("SERVICE_URL", "http://localhost:18080")

    maxParallelForks = 1
}
```

Các mục:

- `useJUnitPlatform()`: chọn JUnit Platform cho test được viết bằng JUnit 5 hoặc framework tương thích; dự án cần thêm các JUnit dependencies/engine tương ứng.
- `javaLauncher`: chọn Java executable cho fork của `Test` task.
- `jvmArgs(...)`: JVM options.
- `systemProperty(...)`: system properties của process test.
- `environment(...)`: environment variables cho process test.
- `maxParallelForks`: số fork test tối đa mà task cho phép chạy song song.

Không cần đặt `-Dapp.profile=unit-test` đồng thời vào `jvmArgs` nếu đã đặt `systemProperty("app.profile", "unit-test")`. Có thể dùng cả hai cơ chế nhưng dễ trùng cấu hình; chọn một cách nhất quán.

### 10.1. Cấu hình mọi task loại `Test`

Nếu dự án có nhiều `Test` tasks:

```kotlin
tasks.withType<Test>().configureEach {
    jvmArgs("-Xmx768m")
    systemProperty("user.timezone", "UTC")
}
```

Cấu hình này áp dụng cho mọi `Test` task được Gradle phát hiện trong project, bao gồm custom integration-test task nếu loại đó là `Test`. Nên dùng để thiết lập các thuộc tính chung; nếu task có mục tiêu runtime khác nhau, override có chủ đích cho từng task.

### 10.2. `forkEvery` và cách ly trạng thái

Gradle hỗ trợ `forkEvery` để kiểm soát số test classes được chạy trước khi fork được thay bằng một fork khác. Ví dụ:

```kotlin
tasks.test {
    forkEvery = 100
    maxParallelForks = 2
}
```

Điều này có thể giúp giảm rò rỉ trạng thái static hoặc native resources trong suite lớn, nhưng làm tăng chi phí khởi động JVM. Nó không thay thế việc viết test độc lập và dọn dẹp tài nguyên đúng cách.

Khi đặt `maxParallelForks=2`, hãy bảo đảm database, port, file paths và mock servers có thể được dùng đồng thời. Hai JVM vẫn có thể ghi vào cùng một tài nguyên ngoài nếu test không được cô lập.

## 11. Gradle: tạo một integration-test task riêng

Gradle có thể tổ chức integration tests bằng một source set/task riêng hoặc dùng JVM Test Suites plugin. Dưới đây là một cách khai báo trực tiếp, giúp nhìn rõ **classpath** và **JVM launcher**.

### 11.1. Cấu trúc dự án

```text
src/
├── main/java/...
├── test/java/...                 # unit tests
└── integrationTest/java/...      # integration tests
```

### 11.2. Tạo source set và cấu hình phụ thuộc

Ví dụ `build.gradle.kts`:

```kotlin
plugins {
    java
}

val integrationTestSourceSet = sourceSets.create("integrationTest") {
    java.srcDir("src/integrationTest/java")
    resources.srcDir("src/integrationTest/resources")

    compileClasspath += sourceSets["main"].output
    runtimeClasspath += output + compileClasspath
}

configurations[
    integrationTestSourceSet.implementationConfigurationName
].extendsFrom(configurations["testImplementation"])

configurations[
    integrationTestSourceSet.runtimeOnlyConfigurationName
].extendsFrom(configurations["testRuntimeOnly"])
```

Cấu hình trên tạo source set riêng và cho integration tests dùng các dependency nền của unit tests. Trong dự án thực tế có thể thêm dependency integration-test-only hoặc điều chỉnh classpath theo kiến trúc. Không nên dùng `sourceSets["test"].output` nếu muốn giữ hai test suites độc lập về class/code fixtures.

### 11.3. Tạo task `integrationTest`

Tiếp tục trong cùng `build.gradle.kts`:

```kotlin
val integrationTestTask = tasks.register<Test>("integrationTest") {
    description = "Runs integration tests."
    group = "verification"

    testClassesDirs = integrationTestSourceSet.output.classesDirs
    classpath = integrationTestSourceSet.runtimeClasspath

    useJUnitPlatform()

    javaLauncher.set(
        javaToolchains.launcherFor {
            languageVersion.set(JavaLanguageVersion.of(21))
        }
    )

    jvmArgs("-Xmx1g")
    systemProperty("app.profile", "integration-test")
    environment("SERVICE_URL", "http://localhost:19090")

    shouldRunAfter(tasks.test)
}

tasks.named("check") {
    dependsOn(integrationTestTask)
}
```

Ví dụ chọn Java 21 cho integration-test process, trong khi ví dụ unit test đã chọn Java 17. Hệ thống thật cần đảm bảo cả hai JDK được cài hoặc Gradle có cơ chế provisioning được cấu hình.

`shouldRunAfter(tasks.test)` chỉ đặt **ưu tiên thứ tự khi cả hai task nằm trong task graph**; nó không tự tạo quan hệ dependency. `check.dependsOn(integrationTestTask)` bảo đảm integration tests được đưa vào khi chạy `check`.

Nếu integration tests cần một service chạy thật tại `localhost:19090`, phải cung cấp quy trình chuẩn bị service, readiness và teardown. Cấu hình endpoint đơn thuần không khởi động service đó.

### 11.4. JVM Test Suites

Ở những phiên bản Gradle hỗ trợ JVM Test Suites, một phương án khác là khai báo suite qua `testing { suites { ... } }`. API này thuận tiện để tạo test source sets và targets thống nhất với Gradle. Dù dùng cách nào, điểm cần chú ý vẫn là JVM của **task `Test` được tạo ra**, vì đó là nơi Java test code chạy.

Không nên đồng thời khai báo thủ công một task `integrationTest` cùng tên với task do JVM Test Suites tự tạo mà không hiểu task graph; có thể gây trùng hoặc conflict.

## 12. Gradle `JavaExec`: JVM chạy chương trình Java riêng

`JavaExec` là task Gradle dùng để khởi động một ứng dụng Java trong **process JVM mới**. Nó thường phục vụ:

- Chạy công cụ migration dữ liệu.
- Chạy lệnh import/export hoặc batch jobs.
- Chạy code generator hoặc command-line application.
- Chạy một main class để smoke-test.
- Thực hiện tác vụ phụ trợ dùng runtime classpath của project.

Ví dụ:

```kotlin
tasks.register<JavaExec>("runMigration") {
    group = "application"
    description = "Runs the data migration command."

    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("com.example.tools.DataMigration")

    javaLauncher.set(
        javaToolchains.launcherFor {
            languageVersion.set(JavaLanguageVersion.of(21))
        }
    )

    jvmArgs("-Xmx512m")
    systemProperty("migration.mode", "dry-run")
    environment("APP_ENV", "staging")
    args("--dry-run", "--limit=100")
}
```

Lệnh chạy:

```bash
./gradlew runMigration
```

Ví dụ có hai vị trí hoàn toàn khác nhau:

- `jvmArgs("-Xmx512m")` tác động tới JVM được JavaExec khởi động.
- `args("--dry-run", "--limit=100")` được chuyển vào `DataMigration.main(String[] args)`.

`javaLauncher` giúp chọn đúng JDK mà không phụ thuộc hoàn toàn vào Gradle Daemon JVM. Nếu task cần dùng module path thay vì classpath, phải cấu hình task/ứng dụng modular thích hợp và kiểm tra cách plugin/java task hỗ trợ JPMS.

### 12.1. Kiểm chứng trong main class

```java
package com.example.tools;

import java.util.Arrays;

public final class DataMigration {
    public static void main(String[] args) {
        System.out.println("Java: "
                + Runtime.version().feature());
        System.out.println("Java home: "
                + System.getProperty("java.home"));
        System.out.println("Mode: "
                + System.getProperty("migration.mode"));
        System.out.println("Environment: "
                + System.getenv("APP_ENV"));
        System.out.println("Arguments: "
                + Arrays.toString(args));
    }
}
```

Khi chạy task ví dụ, console phải cho thấy Java feature 21 nếu đúng launcher và JDK 21 có sẵn. Nếu kết quả khác, kiểm tra task đang được cấu hình ở đúng subproject, plugin khác có override hay không, và Java executable được chọn.

## 13. So sánh các cơ chế chính: Maven và Gradle

| Nhu cầu | Maven | Gradle |
|---|---|---|
| JVM chạy build tool | `mvn -version`, launcher/JAVA_HOME, Maven options. | `./gradlew --version`, daemon JVM, JVM criteria. |
| Biên dịch cho Java 17 | Compiler Plugin `<release>17</release>` hoặc property tương ứng. | `options.release.set(17)`. |
| Chọn JDK unit test | Surefire `jdkToolchain`/`jvm` với fork. | `Test.javaLauncher`. |
| JVM flags unit test | Surefire `argLine`. | `Test.jvmArgs(...)`. |
| Unit test system properties | Surefire `systemPropertyVariables`. | `Test.systemProperty(...)`. |
| Integration test | Failsafe `integration-test` + `verify`. | Custom `Test` task hoặc JVM Test Suite. |
| Chọn JDK integration test | Failsafe `jdkToolchain`/`jvm`. | `integrationTest.javaLauncher`. |
| Chạy Java main class ngoài build JVM | Exec Maven Plugin `exec:exec` với java executable. | `JavaExec` với `javaLauncher`. |
| Chạy main trong build JVM | Exec Maven Plugin `exec:java`. | Một số task/plugin thực thi code trong daemon; không đồng nhất với JavaExec. |
| Kiểm chứng runtime | In `java.home`/`Runtime.version()` từ test/process. | Tương tự, trong process của `Test`/`JavaExec`. |

Không nhầm tên các plugin với bản thân JVM. Việc hai dự án cùng dùng Maven hoặc Gradle không bảo đảm cùng cơ chế fork và runtime.

## 14. Tình huống migration: build trên JDK 21, test trên JDK 17

Giả sử thư viện phải hỗ trợ Java 17, nhưng nhóm phát triển muốn dùng toolchain mới để build.

Một phương án:

```text
Maven / Gradle Daemon  -> JDK 21 (nếu build tool hỗ trợ)
Compiler              -> JDK 21, --release 17
Unit-test runtime     -> JDK 17
Integration tests     -> JDK 17 + JDK 21 ở CI matrix
Application runtime   -> Java 17 minimum
```

Điều này kiểm tra được hai điều:

1. Compiler không tạo bytecode/API vượt quá Java 17 theo `--release 17`.
2. Các test chạy thực sự trên Java 17, giúp phát hiện lỗi runtime mà compile không thể phát hiện.

Tuy nhiên, cần kiểm tra cả dependencies ngoài project. `--release 17` không tự biến một JAR dependency đã biên dịch cho Java 21 thành tương thích với Java 17.

### 14.1. Vì sao chỉ chạy test trên Java 21 chưa đủ?

Một class có thể dùng reflection, ServiceLoader, native library, class loading hoặc behavior có khác biệt giữa JDKs. Nếu test chỉ chạy trong Java 21, thư viện có thể vẫn chứa lỗi chỉ xảy ra ở Java 17.

Một CI matrix có thể kiểm thử:

```text
Build artifact once (release 17)
          |
          +--> Test on JDK 17
          |
          +--> Test on JDK 21
```

Tùy yêu cầu sản phẩm, cũng có thể build riêng trên từng JDK, nhưng cần ghi rõ mục tiêu: kiểm tra compiler compatibility hay runtime behavior.

## 15. Tình huống migration: integration test cần JDK mới hơn

Giả sử test tích hợp dùng một thư viện test utility chỉ hỗ trợ Java 21, trong khi code sản phẩm cần chạy trên Java 17.

Có thể cấu hình:

```text
Production classes  -> target Java 17
Unit tests          -> Java 17
Integration tests   -> Java 21
```

Nhưng hãy thận trọng: integration tests trên Java 21 **không chứng minh** production behavior đã được kiểm thử trên Java 17. Nếu sản phẩm cam kết runtime 17, vẫn phải có ít nhất một suite phù hợp chạy trên Java 17, đặc biệt cho serialization, JDBC, reflection, TLS và module access.

Ngoài ra, test code biên dịch cho Java 21 không thể được chạy trên JVM Java 17. Nếu hai suites dùng các source sets/toolchains khác nhau, cần kiểm tra release target của **test classes** tương ứng, không chỉ main classes.

## 16. Vì sao `JAVA_HOME` và `PATH` dễ gây nhầm?

Trên một máy có nhiều JDK:

```text
JAVA_HOME -> JDK 17
PATH      -> JDK 21/bin ở trước các thư mục khác
```

Cách chọn JVM của `java`, `javac`, Maven launcher và Gradle wrapper có thể không giống nhau. Ví dụ một wrapper script có thể ưu tiên `JAVA_HOME`, trong khi gọi trực tiếp `java -version` dùng executable đầu tiên trong `PATH`.

Các dấu hiệu nên kiểm tra:

```bash
java -version
javac -version
mvn -version
./gradlew --version
```

Trên Linux/macOS:

```bash
which java
which javac
```

Trên Windows PowerShell:

```powershell
Get-Command java
Get-Command javac
$env:JAVA_HOME
```

Sau đó xác nhận **trong test/JavaExec process**. Nếu toolchains đã được cấu hình, việc đổi `JAVA_HOME` có thể không đổi launcher mà Gradle `Test` hoặc Maven Surefire thực sự chọn.

## 17. JVM flags chỉ ảnh hưởng process nhận chúng

Một số loại cấu hình phổ biến:

| Nhóm | Ví dụ | Vấn đề cần cân nhắc |
|---|---|---|
| Heap | `-Xms128m -Xmx512m` | Heap test fork không phải heap Gradle/Maven JVM. |
| GC | `-XX:+UseG1GC` | Flag/GC hỗ trợ và default có thể đổi theo JDK. |
| System property | `-Duser.timezone=UTC` | Cần hiểu ảnh hưởng tới formatter/timezone trong code. |
| Reflective access | `--add-opens=module/package=target` | Dùng scope nhỏ nhất và có kế hoạch loại bỏ. |
| Export internal package | `--add-exports=module/package=target` | Có thể cần cho legacy dependencies, không phải API ổn định. |
| Assertions | `-ea` | Một số test/framework phụ thuộc việc assertions được bật. |
| JVM logging | `-Xlog:gc*` | Unified logging syntax khác flags GC logging trên JDK cũ. |
| Charset | `-Dfile.encoding=UTF-8` | Không thay thế việc dùng charset tường minh trong I/O. |
| Locale | `-Duser.language=en -Duser.country=US` | Chỉ dùng khi cần môi trường ổn định, vẫn phải test logic locale. |

Không đưa JVM flags không được hỗ trợ bởi JDK mục tiêu vào mọi test job. Ví dụ một flag tồn tại ở JDK 21 có thể không có ở JDK 8; build sẽ thất bại ngay trước khi test bắt đầu. Khi có test matrix, cấu hình flags theo runtime tương ứng và document lý do cần từng flag.

### 17.1. `MAVEN_OPTS` và `org.gradle.jvmargs` không thay thế test JVM config

Ví dụ:

```text
MAVEN_OPTS=-Xmx2g
org.gradle.jvmargs=-Xmx2g
```

Các tùy chọn trên chủ yếu điều khiển JVM của build tool. Chúng không phải cách trực tiếp để quy định heap cho từng test fork hoặc JavaExec JVM. Trong Gradle, cấu hình `org.gradle.jvmargs` nằm trong `gradle.properties`; trong Maven, `MAVEN_OPTS` là biến môi trường của launcher.

Đặt `-Xmx2g` cho Gradle Daemon không bảo đảm Gradle `Test` có heap 2 GiB. Muốn kiểm soát fork, đặt `Test.maxHeapSize` hoặc `Test.jvmArgs` rõ ràng. Tương tự, Surefire/Failsafe dùng cấu hình fork của plugin.

## 18. Java agents, coverage và `argLine`

Trong Maven, một agent như JaCoCo thường cần thêm `-javaagent:...` vào JVM chạy tests. Nếu plugin coverage tự sinh property `argLine`, việc ghi đè `<argLine>...</argLine>` một cách vô ý có thể làm mất Java agent.

Với Surefire, có cơ chế late property evaluation như `@{argLine}` trong các cấu hình phù hợp:

```xml
<configuration>
  <argLine>@{argLine} -Xmx512m</argLine>
</configuration>
```

Khi áp dụng, cần bảo đảm property được khởi tạo hợp lệ và plugin coverage thực sự gán nó; nếu không, cấu hình có thể truyền một chuỗi chưa thay thế vào command line. Một lựa chọn khác là dùng tên property riêng cho agent rồi tham chiếu nhất quán từ JaCoCo và Surefire.

Trong Gradle, JaCoCo plugin có thể gắn agent vào `Test` tasks thông qua tích hợp của plugin. Hãy kiểm tra agent nằm trong **test fork** thay vì chỉ trên Gradle Daemon; đồng thời đảm bảo Java agent tương thích với JDK đang chạy test.

## 19. Environment isolation và secret handling

Integration tests thường cần credential, service URL và resource names. Không đưa secret thật vào `pom.xml`, `build.gradle.kts` hoặc ví dụ lệnh được commit.

Một số nguyên tắc:

- Truyền secret qua CI secret store hoặc cơ chế bảo mật phù hợp.
- Chỉ cấp secret cho task thực sự cần, không cho cả build process nếu không cần thiết.
- Không log nguyên văn environment hay system properties có secret.
- Test dùng database/schema riêng; tránh trùng port/tên bucket giữa parallel jobs.
- Các giá trị như `SERVICE_URL` phải được kiểm tra để không vô tình trỏ đến production.
- Xóa tài nguyên test sau khi job kết thúc, kể cả khi test thất bại.

### 19.1. Gradle provider API cho cấu hình ngoài

Ví dụ dùng Gradle property làm đầu vào:

```kotlin
tasks.named<Test>("integrationTest") {
    val endpoint = providers.gradleProperty("itServiceUrl")
        .orElse("http://localhost:19090")

    systemProperty("it.service.url", endpoint.get())
}
```

Giá trị mặc định chỉ phù hợp nếu môi trường test thực sự có service tại đó. Trong CI nghiêm ngặt, có thể yêu cầu property bắt buộc thay vì fallback, để tránh bỏ qua lỗi cấu hình.

### 19.2. Maven system properties truyền qua command line

Khi cần override một thuộc tính dùng trong test:

```bash
mvn verify -Dit.service.url=http://localhost:19090
```

Tùy cách Surefire/Failsafe được cấu hình, user properties của Maven có thể được đưa vào test process theo cơ chế của plugin. Với dự án có chính sách bảo mật nghiêm ngặt, nên định nghĩa rõ mapping thông qua `systemPropertyVariables` hoặc property configuration, thay vì dựa hoàn toàn vào behavior mặc định.

Đường dẫn, URL và các giá trị trong ví dụ chỉ minh họa, không phải endpoint có thật.

## 20. Test trên nhiều JDK mà không nhân đôi cấu hình thiếu kiểm soát

Một chiến lược thường dùng:

```text
                      Shared source code
                             |
                    Build artifact (17)
                             |
         +-------------------+-------------------+
         |                                       |
      JDK 17                                  JDK 21
         |                                       |
  Unit + integration                         Unit + smoke
         |                                       |
         +-------------------+-------------------+
                             |
                         Compare
```

Không bắt buộc mọi job phải chạy cùng khối lượng test. Có thể dành suite nặng cho minimum supported JDK, còn smoke/compatibility cho các JDK khác, miễn là rủi ro và coverage được mô tả rõ.

### 20.1. Những sự khác biệt đáng kiểm tra giữa JDK

- Charset và locale mặc định.
- Reflection/JPMS `opens` và `exports`.
- TLS truststore và security providers.
- Java serialization/JSON/XML và timezone.
- JDBC drivers, native libraries, compression.
- GC, JVM flags và memory behavior.
- ServiceLoader/automatic modules.
- Class file major version và API availability.

Chạy cùng artifact trên nhiều runtime giúp phát hiện một số runtime incompatibility. Nhưng để phát hiện lỗi compiler hoặc annotation processor thay đổi giữa JDK, có thể cần job biên dịch riêng bằng từng toolchain.

## 21. Debug khi unit test chạy đúng nhưng integration test thất bại

Một tình huống điển hình:

```text
Unit tests PASS on developer machine
Integration tests FAIL in CI
Error: UnsupportedClassVersionError
```

Quy trình:

1. In `java.version` và `java.home` từ unit-test JVM và integration-test JVM.
2. Xác nhận class file major version của test classes và dependencies.
3. Kiểm tra Failsafe `jdkToolchain` hoặc Gradle integration-test `javaLauncher`.
4. Xác nhận CI có JDK đúng version và toolchain được tìm thấy.
5. Kiểm tra dependency của integration tests có yêu cầu JDK cao hơn runtime không.

Không chỉ sửa `maven.compiler.release` hoặc `options.release` cho main source; integration-test classes có thể được biên dịch bằng cấu hình khác, hoặc một thư viện test là nguyên nhân.

### 21.1. Test không tìm thấy class vì classpath khác nhau

Nếu unit test thấy class nhưng integration test báo `ClassNotFoundException`:

- Maven: kiểm tra test classpath, scopes, exclusions và dependency resolution trong module tương ứng.
- Gradle: kiểm tra `integrationTestSourceSet.runtimeClasspath`, `integrationTestImplementation` và `integrationTestRuntimeOnly`.
- JPMS: kiểm tra module path, module names và runtime resolution.

Không tự động thêm toàn bộ classpath của unit tests vào integration tests nếu điều đó kéo theo mock dependencies làm sai môi trường tích hợp.

### 21.2. Test chạy bằng JVM đúng nhưng kết quả khác nhau

Khi `java.version` xác nhận runtime đúng mà output vẫn khác, so sánh:

- System properties và environment variables.
- Timezone, default charset và locale.
- Service endpoint, database state và fixture.
- Parallelism, thread scheduling và GC.
- JVM flags/agents của từng task.

Đừng mặc định JDK khác là nguyên nhân khi test đang dùng dữ liệu hoặc cấu hình ngoài khác nhau.

## 22. Những thông báo lỗi thường gặp

| Thông báo / triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `UnsupportedClassVersionError` | Test JVM cũ hơn bytecode của test hoặc dependency. | Xem `java.home` test JVM và `major version`. |
| `NoClassDefFoundError` trong fork | Thiếu runtime dependency hoặc module. | Xem classpath/module path và artifact thực tế. |
| `InaccessibleObjectException` | JPMS chặn reflection. | Cập nhật thư viện hoặc dùng `--add-opens` có phạm vi hẹp cho đúng fork. |
| `The forked VM terminated without properly saying goodbye` | JVM crash, `System.exit`, OOM, agent/flag sai. | Xem fork logs, dump, heap và crash report. |
| Unit test dùng JDK 21 dù muốn 17 | Chỉ đặt compiler release, chưa chọn runtime toolchain. | Cấu hình Surefire/Gradle `Test` launcher. |
| Integration tests không chạy | Goal/phase hoặc include patterns sai. | Maven chạy `verify`, kiểm tra Failsafe includes; Gradle task graph. |
| JavaExec chạy sai JVM | Task lấy launcher mặc định/Daemon khác mong muốn. | Đặt `javaLauncher` và in version từ main. |
| JVM không nhận biết flag | Flag đã bị xóa/đổi trên JDK mới. | Kiểm tra option theo JDK chạy fork. |
| Port/address already in use | Nhiều test forks chia sẻ cùng port. | Tách port/dữ liệu, giới hạn parallelism. |
| `NoSuchMethodError` chỉ ở integration tests | Dependency runtime khác unit tests. | So resolved dependency graph, classpath. |

Thông báo “forked VM terminated” không phải chứng cứ duy nhất cho một nguyên nhân. Cần xem `hs_err_pid*.log` nếu JVM crash, output của process, kết quả OOM và flags thực tế trước khi điều chỉnh bộ nhớ hoặc tắt fork.

## 23. Quan sát command line của fork khi cần

Trong Maven có thể chạy với verbose/debug options khi đang điều tra:

```bash
mvn -X test
mvn -X verify
```

Gradle:

```bash
./gradlew test --info --stacktrace
./gradlew integrationTest --info --stacktrace
./gradlew runMigration --info --stacktrace
```

Các tùy chọn debug có thể làm log rất dài, và command line/environment có thể chứa secret. Chỉ lưu/chia sẻ log trong phạm vi được phép, che nội dung nhạy cảm và không bật mức log cao không cần thiết ở production.

Ngoài ra, nên tạm in `Runtime.version()` và `java.home` từ **bên trong** test hoặc main class, vì đó là bằng chứng trực tiếp về JVM đang thực thi code.

### 23.1. Build cache và up-to-date checks

Gradle có thể bỏ qua task vì output được coi là up-to-date hoặc cache hit, nên log của lần chạy không nhất thiết chứa output mới từ test. Nếu mục đích là xác nhận process thực tế ở một lần điều tra, có thể chạy lại task có chủ đích bằng flags tương ứng như `--rerun-tasks`, nhưng chỉ trong quy trình kiểm tra thật; không cần thay cấu hình lâu dài.

Tương tự, Maven hoặc CI cache có thể giữ artifact đã biên dịch bằng JDK cũ. Khi thấy hành vi không khớp với config, kiểm tra output class file và build provenance trước.

## 24. Các lỗi thiết kế cấu hình dễ gặp

**Chỉ thay `JAVA_HOME` rồi coi toàn bộ toolchain đã đổi.** Maven/Gradle plugin có thể chọn JDK qua Toolchains; fork JVM có thể khác.

**Dùng `--release` làm cách chọn runtime.** `--release` không bắt buộc test process chạy bằng JDK target.

**Đặt test heap trong `MAVEN_OPTS` hoặc `org.gradle.jvmargs`.** Chúng chủ yếu điều khiển build process, không phải bộ nhớ của fork test.

**Đưa `--dry-run` vào `jvmArgs`.** Đó là program argument, phải nằm sau main class hoặc được cấu hình qua `args`.

**Dùng `exec:java` để chạy tool cần JDK khác Maven.** Goal này không tạo JVM ngoài như `exec:exec`.

**Không chạy Maven tới `verify`.** Failsafe có thể ghi lỗi ở integration-test phase nhưng chưa đưa failure vào kết quả cuối theo đúng lifecycle.

**Tạo Gradle `integrationTest` task nhưng không gắn vào `check`.** CI chạy `check` có thể bỏ qua integration tests.

**Tăng số fork khi test dùng chung port/database.** Test có thể thất bại ngẫu nhiên, đặc biệt trên CI nhiều core.

**Dùng secret trực tiếp trong build script.** Giá trị có thể bị commit hoặc lộ qua logs/config cache.

**Giữ flags mở toàn bộ JDK internals mãi mãi.** Workaround có thể che dependency không tương thích và tăng rủi ro an ninh.

**Chạy integration tests trên JDK mới rồi khẳng định baseline cũ đã được hỗ trợ.** Cần test runtime thấp nhất nếu đó là cam kết của sản phẩm.

## 25. Quy trình cấu hình khi chuyển JDK

Một quy trình có thể áp dụng cho cả Maven và Gradle:

### Bước 1 — Xác định ma trận yêu cầu

Ghi minimum runtime, compiler JDK, JDK cho unit tests, JDK cho integration tests và JDK cho batch/JavaExec. Nếu chúng bằng nhau, ghi rõ; nếu khác, giải thích lý do.

### Bước 2 — Kiểm tra build tool compatibility

Kiểm tra phiên bản Maven/Gradle, Surefire/Failsafe, Compiler Plugin hoặc plugins khác có hỗ trợ JDK mới không. Với Gradle, kiểm tra compatibility matrix cho JDK chạy Daemon và toolchain riêng.

### Bước 3 — Cấu hình compiler target

Chọn `--release` hoặc cơ chế tương đương khi cần phát hành bytecode/API cho JDK cũ; không nhầm với runtime test.

### Bước 4 — Cấu hình JVM unit test riêng

Dùng Surefire `jdkToolchain`/`jvm` hoặc Gradle `Test.javaLauncher`. Cấu hình heap, timezone, locale và system properties theo hợp đồng của suite.

### Bước 5 — Cấu hình integration test riêng

Dùng Failsafe hoặc custom Gradle `Test` suite; thiết lập runtime launcher, classpath, endpoints, credentials, parallelism và quy trình startup/teardown của môi trường thử nghiệm.

### Bước 6 — Cấu hình JavaExec hoặc process runner

Với Gradle, dùng `JavaExec.javaLauncher` và phân biệt `args` với `jvmArgs`. Với Maven, phân biệt `exec:java` trong Maven process với `exec:exec` tạo process ngoài.

### Bước 7 — Kiểm chứng từ chính process

In `Runtime.version()`, `java.home`, profile và một số properties không nhạy cảm từ unit/integration/JavaExec processes. Đừng kết luận chỉ từ `java -version` của shell.

### Bước 8 — Chạy suite trên runtime cam kết

Đảm bảo minimum supported JDK và các target JDK quan trọng đều được bao phủ. Tách lỗi class file/API, dependency resolution, config và integration environment.

### Bước 9 — Ghi nhận cấu hình trong CI

Ghim wrapper/plugin versions, định nghĩa toolchain provisioning, và lưu log runtime diagnostics không chứa secret. Tránh cấu hình phụ thuộc vào đường dẫn cục bộ của một developer.

## 26. Checklist cấu hình JVM cho build và test

- [ ] Biết chính xác JDK đang chạy Maven/Gradle Daemon.
- [ ] Biết JDK compiler và `--release`/source compatibility.
- [ ] Đã xác định JDK cho JVM unit-test fork.
- [ ] Đã xác định JDK cho JVM integration-test fork.
- [ ] Đã xác định JDK cho JavaExec hoặc process runner.
- [ ] Đã cấu hình riêng JVM flags và application arguments.
- [ ] System properties và environment variables được truyền đúng process.
- [ ] Không đặt secrets trong build scripts hoặc command logs công khai.
- [ ] Maven Surefire/Failsafe có cấu hình fork phù hợp.
- [ ] Maven integration tests được kiểm tra ở pha `verify`.
- [ ] Gradle `integrationTest` được gắn vào task graph khi cần.
- [ ] Các test forks có tài nguyên/port/database được cô lập.
- [ ] Java Toolchains được cấu hình đúng và JDK cần thiết có sẵn.
- [ ] Không nhầm `org.gradle.jvmargs`/`MAVEN_OPTS` với test JVM arguments.
- [ ] Đã in/ghi nhận Java version từ bên trong từng test/JavaExec process.
- [ ] Đã kiểm thử trên minimum runtime mà sản phẩm cam kết hỗ trợ.
- [ ] Các `--add-opens`/`--add-exports` đều có lý do và kế hoạch giảm bỏ.
- [ ] Có logs và hướng dẫn chẩn đoán khi fork JVM không khởi động.

## 27. Tài liệu tham khảo

- [Apache Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/): cấu hình unit test execution, fork và JVM options.
- [Apache Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/): integration tests và các goals `integration-test`, `verify`.
- [Maven Surefire — Fork Options and Parallel Test Execution](https://maven.apache.org/surefire/maven-surefire-plugin/examples/fork-options-and-parallel-execution.html): `forkCount`, `reuseForks` và các cơ chế chạy song song.
- [Maven Surefire — Java Toolchains](https://maven.apache.org/surefire/maven-surefire-plugin/examples/toolchains.html): chọn JDK riêng cho test forks.
- [Apache Maven Toolchains Plugin](https://maven.apache.org/plugins/maven-toolchains-plugin/): quản lý JDK toolchains cho plugin tương thích.
- [MojoHaus Exec Maven Plugin](https://www.mojohaus.org/exec-maven-plugin/): khác biệt giữa `exec:java` và `exec:exec`.
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): Java Toolchains và Java launcher.
- [Gradle — Testing in Java and JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): cấu hình task `Test`, forks và test execution.
- [Gradle — JVM Test Suite Plugin](https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html): khai báo nhiều test suites.
- [Gradle — JavaExec](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.JavaExec.html): `mainClass`, `javaLauncher`, JVM arguments, program arguments.
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): JDK hỗ trợ cho Gradle runtime và toolchains.
- [Java Toolchain and `javac --release`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): phân biệt compiler target với Java runtime.

## Kết luận

Để migration Java đáng tin cậy, cần cấu hình và quan sát **đúng JVM thực thi từng loại công việc**. Maven có Surefire cho unit tests, Failsafe cho integration tests, Toolchains để chọn JDK cho plugin tương thích, cùng Exec Plugin để chạy Java code trong Maven JVM hoặc ở process ngoài. Gradle có Java Toolchains, `Test.javaLauncher` và `JavaExec.javaLauncher` để chọn JVM cho từng task. `--release` giải quyết tương thích biên dịch, còn `jvmArgs`, system properties, environment variables, classpath và module path điều khiển runtime thực tế. Xác nhận `java.home`/`Runtime.version()` ngay trong test và JavaExec process, giữ cấu hình tách biệt giữa các suite, và chạy trên JDK tối thiểu được hỗ trợ sẽ giúp phát hiện lỗi tương thích trước khi triển khai production.
