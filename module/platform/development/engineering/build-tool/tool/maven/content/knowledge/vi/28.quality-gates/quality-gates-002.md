# Kiểm tra phiên bản Maven, Java và các yêu cầu môi trường

## 1. Vấn đề: cùng source nhưng build khác nhau

Một dự án Java có thể build thành công ở laptop nhưng thất bại trên CI không phải vì mã nguồn sai. Những nguyên nhân thường gặp gồm Maven quá cũ, Java chạy Maven không phù hợp, compiler JDK thiếu hoặc chọn nhầm, profile bắt buộc chưa bật, biến môi trường bị thiếu, file cấu hình không tồn tại, proxy/repository không truy cập được, hoặc service integration test chưa sẵn sàng.

Một **cổng chất lượng môi trường (environment quality gate)** là tập các điều kiện bắt buộc phải đạt trước khi build được coi là hợp lệ. Nó cần trả lỗi rõ, sớm và làm process Maven có exit code khác 0 khi không đạt.

Trong bài này, điều kiện ví dụ là:

- Maven **3.9.x** (từ 3.9.0 đến trước 4.0.0).
- JVM chạy Maven phải là **Java 17 hoặc mới hơn**.
- Source Java được biên dịch với `--release 17`.
- Khi bật profile `ci-gates`: phải có biến `DEMO_CI_READY=yes`, Maven property `deploy.target` bằng `test` hoặc `staging`, và file `ci/quality-gate.txt`.
- Unit tests JUnit Jupiter phải thực sự được chạy và pass.
- Không dùng skip flags hay chính sách reactor che lỗi để khiến CI xanh giả.

Công cụ trọng tâm là **Maven Enforcer Plugin 3.6.3**. Các ví dụ còn dùng Maven Compiler Plugin 3.14.1, Surefire 3.5.4, JAR Plugin 3.4.2 và JUnit Jupiter 5.11.4. Đây là các version được ghim để học tập và tái hiện, không phải cam kết chúng luôn mới nhất.

### Kết quả học tập

Sau bài, bạn sẽ biết kiểm tra Maven/Java từ terminal, phân biệt JVM chạy Maven với JDK compiler và target bytecode, dùng Enforcer rules cho Maven/Java/env/property/file, cấu hình profile CI, viết POM/Java/JUnit runnable, chẩn đoán lỗi validate/compile/test, kiểm tra exit code Bash/PowerShell/CMD, sử dụng Maven Wrapper/Toolchains đúng vai trò và triển khai gates trong reactor nhiều module.

---

## 2. Tách riêng những thành phần dễ nhầm

| Lớp | Kiểm tra | Cách xác minh |
| --- | --- | --- |
| Maven runtime | Maven phiên bản nào được khởi động? | `mvn -version` |
| JVM chạy Maven | Java version của chính tiến trình Maven | Dòng Java trong `mvn -version`; `requireJavaVersion` |
| JDK compiler | Compiler có thật và hỗ trợ Java17? | `javac -version`, Compiler Plugin, Toolchains |
| Bytecode/API target | Build tạo classes theo mức release nào? | `maven.compiler.release`; kiểm tra bytecode nếu cần |
| Test JVM | Unit tests đang chạy Java nào? | Surefire/JUnit và test `Runtime.version()` |
| OS/CPU | Linux, Windows, macOS, x64, ARM64? | `mvn -version`, CI runner, `requireOS` |
| Maven property | Một giá trị cấu hình có được cung cấp và hợp lệ? | `requireProperty` |
| Environment variable | Một biến có tồn tại và match regex? | `requireEnvironmentVariable` |
| File bắt buộc | File có ở đúng đường dẫn trước build? | `requireFilesExist` |
| External service | DB, API, registry có sẵn sàng? | Health/smoke/integration test |
| Network/credentials | Repository, proxy, TLS, token đúng? | Resolution/connection checks |
| Tài nguyên hệ thống | Disk, RAM, permissions đủ không? | CI/OS preflight riêng |

**Maven Enforcer không tự kiểm tra mọi thứ trong bảng.** Nó giúp diễn tả các rules có sẵn. Những điều kiện vận hành như database connect được hoặc credentials còn hiệu lực phải xác minh thêm.

### 2.1. Ba thông tin Java khác nhau

~~~bash
mvn -version
java -version
javac -version
~~~

`mvn -version` cho biết Java runtime Maven đang dùng. `java -version` cho biết Java launcher trên PATH, có thể khác Java được chọn bởi `JAVA_HOME`/IDE Maven runner. `javac -version` cho biết compiler trên PATH, có thể khác compiler được Toolchains hoặc Compiler Plugin chọn.

Ví dụ logic:

~~~text
Maven process:  Java 21
PATH javac:     Java 17
Compiler target: --release 17
~~~

Đây không nhất thiết là cấu hình sai. JVM chạy Maven, compiler JDK và target release là ba khái niệm độc lập.

### 2.2. Source target không tự chọn JDK

Trong POM:

~~~xml
<maven.compiler.release>17</maven.compiler.release>
~~~

yêu cầu compiler sử dụng release17 khi hỗ trợ. Nó không tải JDK17, không bảo đảm Maven chạy trên JDK17 và không xác nhận production runtime đang dùng Java17. Nếu compiler quá cũ, compile có thể báo `release version 17 not supported`.

---

## 3. Đặt cổng kiểm tra ở phase validate

Thứ tự mặc định của Maven lifecycle được rút gọn:

~~~text
validate
  |
  v
compile
  |
  v
test-compile
  |
  v
test
  |
  v
package
  |
  v
verify
  |
  v
install
  |
  v
deploy
~~~

Khi bind `enforcer:enforce` vào `validate`, yêu cầu tool/environment được kiểm tra **trước compile/test/package**. Đây là cách fail sớm, giúp developer nhận thông báo đúng nguyên nhân.

Snippet:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.6.3</version>
    <executions>
        <execution>
            <id>enforce-tool-versions</id>
            <phase>validate</phase>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <requireMavenVersion>
                        <version>[3.9.0,4.0.0)</version>
                    </requireMavenVersion>
                    <requireJavaVersion>
                        <version>[17,)</version>
                    </requireJavaVersion>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đây là **trích đoạn plugin**, chưa phải POM độc lập. Goal `enforcer:enforce` thực thi các rules trong cấu hình; chỉ gọi `mvn validate` mà không bind goal thì phase này không tự đoán các điều kiện.

Vẫn cần lưu ý: Maven có thể phải tải Enforcer Plugin hoặc dependencies từ repository trước khi rule chạy. “Fail early” không có nghĩa hệ thống không thực hiện bất kỳ network access nào.

---

## 4. Rule requireMavenVersion

~~~xml
<requireMavenVersion>
    <version>[3.9.0,4.0.0)</version>
    <message>Use Maven 3.9.x.</message>
</requireMavenVersion>
~~~

Ý nghĩa version range:

| Range | Điều kiện |
| --- | --- |
| `[3.9.0,4.0.0)` | Từ 3.9.0 (bao gồm) đến trước 4.0.0 |
| `[3.9.0,)` | Tối thiểu 3.9.0 |
| `[3.9.6]` | Chỉ 3.9.6 |
| `(,4.0.0)` | Thấp hơn 4.0.0 |

`[`/`]` gồm biên, `(`/`)` loại biên. Enforcer có quy ước riêng khi chỉ ghi một version, thường hiểu là tối thiểu; dùng range có ngoặc rõ sẽ dễ review hơn.

Mẫu khóa Maven 3.9.x, **không có nghĩa Maven 4 vĩnh viễn không phù hợp**. Khi đội ngũ đã thử nghiệm Maven 4, có thể nới range theo chính sách thật.

### 4.1. Enforcer khác prerequisites

POM có thể chứa `<prerequisites><maven>...` nhưng trường này không nên được coi là quality gate tổng quát cho library/application Maven projects. Dùng Enforcer để kiểm tra version và các điều kiện môi trường khác một cách tường minh.

---

## 5. Rule requireJavaVersion

~~~xml
<requireJavaVersion>
    <version>[17,)</version>
    <message>Maven must run on Java 17 or newer.</message>
</requireJavaVersion>
~~~

Rule kiểm tra **Java VM chạy Maven**, không kiểm JDK mới nhất đã cài trên host hoặc compiler toolchain được chọn riêng.

| Maven JVM | Với `[17,)` |
| --- | --- |
| Java 11 | FAIL |
| Java 17 | PASS |
| Java 21 | PASS |

Muốn bắt buộc Maven JVM đúng dòng 17, dùng:

~~~xml
<requireJavaVersion>
    <version>[17,18)</version>
</requireJavaVersion>
~~~

Dòng này loại Maven chạy trên JDK21, dù JDK21 có thể biên dịch Java17-compatible code với `--release 17`. Vì vậy phải chọn range dựa trên yêu cầu thực tế, không khóa cứng vì suy đoán.

### 5.1. Java version không chứng minh có javac

Có môi trường Java runtime 17 nhưng không có compiler tool `javac`. Rule Java version có thể pass dù build source sẽ fail ở Compiler Plugin. Để kiểm tra, dùng:

~~~bash
javac -version
mvn clean compile
~~~

Với Toolchains, compiler được plugin chọn có thể không trùng `javac` trong terminal; khi đó cần xem toolchain logs/configuration.

### 5.2. Java version normalization

Enforcer rule chuẩn hóa một số chuỗi Java version trước khi so sánh. Khi gặp vendor build string khác thường, xem documentation của `requireJavaVersion` và JVM của `mvn -version`. Không viết script tự so sánh lexicographic chuỗi `17.0.10` với `17.0.9`.

---

## 6. Rule requireEnvironmentVariable

~~~xml
<requireEnvironmentVariable>
    <variableName>DEMO_CI_READY</variableName>
    <regex>yes</regex>
    <regexMessage>Set DEMO_CI_READY=yes.</regexMessage>
</requireEnvironmentVariable>
~~~

Kiểm tra env var tồn tại và toàn bộ giá trị match regex `yes`. Một biến `DEMO_CI_READY=no` sẽ FAIL, dù đã được set.

Đây là **marker ví dụ không chứa secret**. Việc biến tồn tại không chứng minh container đã start, database healthy hay tài khoản cloud hợp lệ.

Nếu project cần thông tin nhạy cảm, dùng CI secret manager và tránh in token ra terminal/log. Không yêu cầu người dùng lưu secret trong POM hoặc README.

---

## 7. Rule requireProperty

~~~xml
<requireProperty>
    <property>deploy.target</property>
    <regex>^(test|staging)$</regex>
    <regexMessage>Use test or staging target.</regexMessage>
</requireProperty>
~~~

Rule yêu cầu Maven property `deploy.target` bằng `test` hoặc `staging`. Có thể truyền:

~~~bash
mvn "-Ddeploy.target=test" validate
~~~

Lưu ý property có thể đến từ CLI, POM, parent, profile hoặc Maven property resolution. `requireProperty` **không xác minh** người vận hành đã tự gõ một command-line option; nó kiểm resolved value.

Tên `deploy.target` không tự kích hoạt deploy. Lệnh `mvn verify` không publish artifact chỉ vì property có chữ `deploy`.

---

## 8. Rule requireFilesExist và requireOS

### 8.1. Kiểm tra file bắt buộc

~~~xml
<requireFilesExist>
    <files>
        <file>${project.basedir}/ci/quality-gate.txt</file>
    </files>
    <message>Missing required CI marker file.</message>
</requireFilesExist>
~~~

File phải tồn tại khi rule chạy. Nếu rule ở `validate`, không chọn file chỉ được tạo ở phase `package`. Rule không parse file, không xác minh checksum, không kiểm database/service readiness.

### 8.2. Kiểm tra hệ điều hành

Trong project có native tool chỉ chạy Unix có thể dùng:

~~~xml
<requireOS>
    <family>unix</family>
</requireOS>
~~~

Rule `requireOS` hỗ trợ các lựa chọn `family`, `name`, `arch`, `version`. Đây là **snippet minh họa**, không đưa vào POM runnable vì project Java demo hoạt động trên cả Windows, macOS và Linux.

Không thêm OS gate quá hẹp nếu thư viện Java portable. Cần phân biệt hệ điều hành của developer với hệ điều hành của CI và runtime production.

---

## 9. Dự án Java17/JUnit5 hoàn chỉnh

Tạo cấu trúc:

~~~text
environment-gate-demo/
├── pom.xml
├── ci/
│   └── quality-gate.txt
└── src/
    ├── main/java/vn/example/gates/EnvironmentApp.java
    └── test/java/vn/example/gates/EnvironmentAppTest.java
~~~

Có **4 file** phải tạo. Dự án sử dụng hai tầng gate:

1. **Baseline:** luôn kiểm tra Maven/Java version rồi compile và unit test.
2. **CI profile:** khi bật `-Pci-gates`, kiểm thêm env var/property/file marker ở `validate`.

### 9.1. pom.xml đầy đủ

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>environment-gate-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.6.3</version>
                <executions>
                    <execution>
                        <id>enforce-tool-versions</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <requireMavenVersion>
                                    <version>[3.9.0,4.0.0)</version>
                                    <message>Use Maven 3.9.x.</message>
                                </requireMavenVersion>
                                <requireJavaVersion>
                                    <version>[17,)</version>
                                    <message>Run Maven on Java 17 or newer.</message>
                                </requireJavaVersion>
                            </rules>
                            <fail>true</fail>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.gates.EnvironmentApp</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>ci-gates</id>
            <build>
                <plugins>
                    <plugin>
                        <groupId>org.apache.maven.plugins</groupId>
                        <artifactId>maven-enforcer-plugin</artifactId>
                        <version>3.6.3</version>
                        <executions>
                            <execution>
                                <id>enforce-ci-prerequisites</id>
                                <phase>validate</phase>
                                <goals>
                                    <goal>enforce</goal>
                                </goals>
                                <configuration>
                                    <rules>
                                        <requireEnvironmentVariable>
                                            <variableName>DEMO_CI_READY</variableName>
                                            <regex>yes</regex>
                                            <regexMessage>Set DEMO_CI_READY=yes.</regexMessage>
                                        </requireEnvironmentVariable>
                                        <requireProperty>
                                            <property>deploy.target</property>
                                            <regex>^(test|staging)$</regex>
                                            <regexMessage>Use test or staging target.</regexMessage>
                                        </requireProperty>
                                        <requireFilesExist>
                                            <files>
                                                <file>${project.basedir}/ci/quality-gate.txt</file>
                                            </files>
                                            <message>Missing ci/quality-gate.txt.</message>
                                        </requireFilesExist>
                                    </rules>
                                    <fail>true</fail>
                                </configuration>
                            </execution>
                        </executions>
                    </plugin>
                </plugins>
            </build>
        </profile>
    </profiles>
</project>
~~~

Đây là **POM hoàn chỉnh**, không phải trích đoạn. Khi profile `ci-gates` được bật, hai executions của cùng Enforcer Plugin có ID khác nhau nên cùng tham gia phase validate. Có thể xem `mvn help:effective-pom -Pci-gates` để kiểm tra cấu hình cuối sau Maven profile merge.

### 9.2. EnvironmentApp.java

File `src/main/java/vn/example/gates/EnvironmentApp.java`:

~~~java
package vn.example.gates;

public final class EnvironmentApp {
    private EnvironmentApp() {
    }

    public static String banner() {
        return "ENVIRONMENT READY";
    }

    public static void main(String[] args) {
        System.out.println(banner());
    }
}
~~~

`main` in chính xác:

~~~text
ENVIRONMENT READY
~~~

Dòng này là **stdout của chương trình khi gọi Java**, không phải stdout tự sinh trong `mvn verify`.

### 9.3. EnvironmentAppTest.java

File `src/test/java/vn/example/gates/EnvironmentAppTest.java`:

~~~java
package vn.example.gates;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class EnvironmentAppTest {
    @Test
    void bannerIsStable() {
        assertEquals("ENVIRONMENT READY", EnvironmentApp.banner());
    }

    @Test
    void testRuntimeIsAtLeastJava17() {
        assertTrue(
                Runtime.version().feature() >= 17,
                "Tests must execute on Java 17 or newer"
        );
    }
}
~~~

Surefire 3.5.4 có thể khám phá JUnit Jupiter tests qua tên `EnvironmentAppTest`. Kỳ vọng **2 tests PASS**, 0 failures/errors khi JVM test từ Java17 trở lên.

Test thứ hai kiểm tra **test JVM**, không nhất thiết cùng JVM chạy Maven nếu project sau này cấu hình Surefire fork/Toolchains khác.

### 9.4. File quality-gate.txt

File `ci/quality-gate.txt` chứa một dòng:

~~~text
CI_PREREQUISITES_CONFIRMED
~~~

Đây chỉ là file marker để thử rule `requireFilesExist`. Rule chứng minh file tồn tại, **không** chứng minh nội dung đúng, credentials hợp lệ hay external system ready.

---

## 10. Chạy baseline và xác nhận output

Tại root của `environment-gate-demo`:

~~~bash
mvn -version
javac -version
mvn clean verify
~~~

Nếu Maven3.9.x, JDK17+ và dependencies/plugins khả dụng, quá trình dự kiến:

~~~text
validate  -> Enforcer Maven/Java checks PASS
compile   -> Compiler Plugin --release 17
test      -> Surefire chạy 2 JUnit tests PASS
package   -> tạo environment-gate-demo-1.0.0.jar
verify    -> BUILD SUCCESS
~~~

Đây là tóm tắt, không phải log Maven nguyên văn. Sau build:

~~~bash
java -cp target/classes vn.example.gates.EnvironmentApp
~~~

Stdout chính xác:

~~~text
ENVIRONMENT READY
~~~

Với Maven JAR Plugin đã khai `Main-Class`:

~~~bash
java -jar target/environment-gate-demo-1.0.0.jar
~~~

Cũng in chính xác `ENVIRONMENT READY`. Ví dụ không có dependency runtime ngoài JDK, nên binary JAR có thể chạy riêng.

**Lưu ý:** `mvn validate` chỉ kiểm tra version rules (khi profile CI chưa bật), **không compile hoặc chạy JUnit**. Một validate pass không phải bằng chứng release đã sẵn sàng.

---

## 11. Bật profile CI trên Bash/Linux/macOS

~~~bash
DEMO_CI_READY=yes mvn -Pci-gates "-Ddeploy.target=test" clean verify
~~~

Lệnh đáp ứng:

- `requireEnvironmentVariable`: có `DEMO_CI_READY=yes`.
- `requireProperty`: `deploy.target=test` match regex.
- `requireFilesExist`: file `ci/quality-gate.txt` đã có.
- `requireMavenVersion` và `requireJavaVersion`: vẫn phải đạt.
- Java compiler/tests: chạy sau validate nếu rules pass.

Có thể dùng `staging`:

~~~bash
export DEMO_CI_READY=yes
mvn -Pci-gates "-Ddeploy.target=staging" clean verify
~~~

Kỳ vọng cả hai Enforcer executions pass, rồi 2 JUnit tests pass; Maven exit code `0`.

---

## 12. Bật profile CI trên PowerShell và CMD

### PowerShell

~~~powershell
$env:DEMO_CI_READY = "yes"
mvn -Pci-gates "-Ddeploy.target=test" clean verify
$code = $LASTEXITCODE
Write-Output "exit_code=$code"
~~~

Khi build pass, stdout của lệnh cuối:

~~~text
exit_code=0
~~~

### Windows CMD

~~~bat
set "DEMO_CI_READY=yes"
mvn -Pci-gates "-Ddeploy.target=test" clean verify
echo exit_code=%ERRORLEVEL%
~~~

Kết quả build pass:

~~~text
exit_code=0
~~~

Cú pháp đặt biến môi trường giữa Bash, PowerShell và CMD không giống nhau. Biến được set ở một terminal **không tự xuất hiện** ở IDE Maven runner hoặc process CI khác nếu chúng không kế thừa environment ấy.

---

## 13. Thử failure: sai biến môi trường

~~~bash
DEMO_CI_READY=no mvn -Pci-gates "-Ddeploy.target=test" clean verify
~~~

Rule yêu cầu regex `yes`, nên build **FAIL tại validate**. Process Maven thông thường trả mã thoát **nonzero**. Compiler và Surefire **chưa chạy trong invocation đó**; không được ghi “2 tests PASS”.

Trên PowerShell:

~~~powershell
$env:DEMO_CI_READY = "no"
mvn -Pci-gates "-Ddeploy.target=test" clean verify
$LASTEXITCODE
~~~

Mong đợi giá trị nonzero. Khôi phục `yes` trước khi thực hành bước khác.

---

## 14. Thử failure: property thiếu hoặc sai

Sai giá trị:

~~~bash
DEMO_CI_READY=yes mvn -Pci-gates "-Ddeploy.target=production" clean verify
~~~

`requireProperty` cho phép `test` hoặc `staging`, vì vậy `production` không match. Build fail. Tên property không tự deploy chương trình: `mvn verify` không phải `mvn deploy`.

Thiếu property:

~~~bash
DEMO_CI_READY=yes mvn -Pci-gates clean verify
~~~

Vì POM không khai mặc định `deploy.target`, rule cũng fail. Trong project thật, property có thể đến từ parent/profile/settings; hãy kiểm tra **effective POM** thay vì suy đoán chỉ CLI quyết định.

---

## 15. Thử failure: thiếu file marker

Trong một **bản sao project**, tạm đổi tên `ci/quality-gate.txt`, rồi bật profile CI. `requireFilesExist` tìm đúng đường dẫn `${project.basedir}/ci/quality-gate.txt`; khi thiếu, build fail ở validate.

Đổi file về tên cũ sau thử nghiệm. Không xóa project/CI files thật để tạo failure. Một file rỗng vẫn có thể pass existence check; nếu yêu cầu nội dung/schema/checksum phải có **rule hoặc test khác**.

---

## 16. Thử Maven/Java version mismatch

Với hai ranges trong POM:

| Maven | JVM của Maven | Kỳ vọng |
| --- | --- | --- |
| 3.9.x | Java17 | PASS version rules |
| 3.9.x | Java21 | PASS version rules |
| 3.8.x | Java17 | FAIL requireMavenVersion |
| 4.x | Java17 | FAIL requireMavenVersion |
| 3.9.x | Java11 | FAIL requireJavaVersion |

Bảng giả định Enforcer Plugin đã được resolve và có thể khởi động. Nếu plugin hoặc launcher không tương thích môi trường cũ, lỗi có thể xuất hiện **trước** khi rule trả thông báo range mismatch.

Để điều tra, chạy `mvn -version` từ cùng terminal/process với command build. Đừng tự hạ JDK thật chỉ để thử trong môi trường production; dùng sandbox/container khi được phép.

---

## 17. Maven Wrapper giúp nhất quán Maven, không tự cấp JDK

Một project có Maven Wrapper thường có:

~~~text
mvnw
mvnw.cmd
.mvn/wrapper/maven-wrapper.properties
~~~

Khi dự án đã tích hợp wrapper:

~~~bash
./mvnw -version
./mvnw clean verify
~~~

Windows:

~~~bat
mvnw.cmd -version
mvnw.cmd clean verify
~~~

Wrapper giúp chọn Maven distribution theo cấu hình repository, giảm sai lệch version giữa developers và CI. Nhưng wrapper **không tự cài JDK** và lần đầu có thể cần network để tải Maven distribution. Enforcer vẫn có tác dụng ngăn một người dùng `mvn` trực tiếp với version không được hỗ trợ.

**Bốn file của project runnable không bao gồm Maven Wrapper.** Các lệnh trên chỉ chạy sau khi bạn thêm wrapper theo tài liệu riêng, không phải bước bắt buộc để hoàn thành demo.

---

## 18. Maven Toolchains và kiểm tra JDK thực thi

Maven Toolchains Plugin hỗ trợ chọn một JDK/tool dùng bởi các plugin **toolchain-aware**, độc lập với JVM đang chạy Maven. Chẳng hạn:

~~~text
JVM chạy Maven: Java21
JDK Compiler:   Java17
Bytecode target: Java17
Test JVM:       tùy Surefire/Toolchain configuration
~~~

Enforcer `requireJavaVersion [17,)` kiểm tra Java21 của Maven và PASS, **không tự chứng minh compiler phải JDK17**. Cần đọc Toolchains/Compiler logs và kiểm tra JDK được chọn.

Maven Toolchains Plugin 3.2.0 giới thiệu JDK discovery, với các goals như:

~~~text
toolchains:select-jdk-toolchain
toolchains:display-discovered-jdk-toolchains
~~~

Cơ chế truyền thống `~/.m2/toolchains.xml` vẫn có. Chỉ cấu hình toolchain khi thật sự cần tách JVM Maven và JDK build; không nhầm “maven.compiler.release=17” với “đã tìm đúng JDK17”.

---

## 19. Các điều kiện không thể được xác nhận chỉ bằng Enforcer rules

Dù Maven/Java/env/property/file checks pass, build vẫn có thể lỗi vì:

- Maven repository/mirror/proxy/DNS/TLS không truy cập được.
- Credentials không hợp lệ, bị thu hồi hoặc thiếu quyền.
- Compiler/annotation processor/plugin không tương thích.
- Docker daemon, database hoặc HTTP service không ready.
- Disk/RAM không đủ, file permission sai, native library không có.
- Locale, timezone, encoding, OS architecture khác môi trường test.
- Artifact đã cache bị hỏng hoặc dependency version không được publish.

Các lệnh để phân biệt lỗi:

~~~bash
mvn -version
mvn -B -ntp clean verify
mvn -o validate
~~~

`-B` bật batch mode; `-ntp` giảm transfer progress; `-o` là offline mode. Nếu lệnh offline PASS, điều đó chỉ cho thấy plugin/dependency cần đã được cache, **không chứng minh repository mạng đang hoạt động**.

Không xóa cả `~/.m2/repository` mù quáng khi gặp resolution failure. Xác định artifact hoặc metadata cụ thể bị lỗi và xử lý theo policy.

### 19.1. Biến tồn tại không đồng nghĩa external service healthy

`DB_HOST=localhost` có thể được set đúng nhưng database chưa chạy. Một check presence không thay health check có timeout. Đối với integration test, hãy kết nối thử sandbox service, xác minh schema/migration và credentials có quyền đúng, rồi cleanup resource theo lifecycle phù hợp.

### 19.2. Không in secrets để debug

Không đưa API keys, database passwords hoặc tokens vào POM/README hoặc log. Khi kiểm tra env var nhạy cảm, ưu tiên secret manager/CI injection và xác minh hành động được phép thay vì in giá trị. File marker của bài không chứa secret.

---

## 20. Cách giữ exit code đúng cho CI

Nếu Enforcer rule FAIL tại validate và `fail=true`, Maven module/build thường FAIL với exit code **khác 0**. Tuy nhiên shell script có thể vô tình nuốt mã ấy.

### Bash

~~~bash
mvn clean verify
status=$?
printf 'maven_exit=%s\n' "$status"
exit "$status"
~~~

Sai nếu chèn `echo` giữa Maven và `status=$?`; khi đó `$?` là exit của echo.

Nếu pipe qua tee:

~~~bash
set -o pipefail
mvn clean verify | tee build.log
status=$?
exit "$status"
~~~

`pipefail` giúp Bash pipeline trả nonzero khi Maven fail. Nếu dùng `set -e` và muốn thu reports trước khi exit, có thể bắt status trong `if`:

~~~bash
if mvn -fae clean verify; then
    status=0
else
    status=$?
fi

# Thu reports nếu CI có công cụ tương ứng.
exit "$status"
~~~

### PowerShell

~~~powershell
mvn clean verify
$code = $LASTEXITCODE
Write-Output "Maven exit=$code"
exit $code
~~~

### CMD

~~~bat
mvn clean verify
echo Maven exit=%ERRORLEVEL%
~~~

Trong CMD script có khối ngoặc, `%ERRORLEVEL%` có thể được expand trước khi các command bên trong chạy; dùng delayed expansion/cấu trúc phù hợp nếu cần.

---

## 21. Các cách vô hiệu hóa gate và rủi ro

### 21.1. Enforcer skip

~~~bash
mvn -Denforcer.skip=true clean verify
~~~

Enforcer có property `enforcer.skip`. Lệnh có thể bỏ qua version/env constraints; thành công sau khi skip **không phải bằng chứng** điều kiện môi trường đạt. Không dùng skip flags trên release/merge gate khi rules bắt buộc.

### 21.2. Enforcer fail=false

Enforcer có `fail`/`enforcer.fail`. Khi false, rule violations có thể chỉ được log dưới dạng warnings thay vì làm build fail. Đây là cơ chế khác với “điều kiện đã đạt”. CI phải kiểm tra effective configuration và tránh bypass ngoài ý muốn.

### 21.3. Reactor fail-never

~~~bash
mvn -fn clean verify
~~~

`-fn` có thể trả `0` dù một hoặc nhiều module FAIL trong Maven Reactor. Nếu CI chỉ nhìn process exit, nó có thể xanh giả. Đối với reactor nhiều module muốn thu thêm diagnostics nhưng vẫn fail khi có lỗi, ưu tiên:

~~~bash
mvn -fae clean verify
~~~

`-fae` tiếp tục modules không bị ảnh hưởng và giữ exit nonzero khi có failure. `-ff` là default, dừng sớm.

### 21.4. Enforcer failFast không phải Reactor -ff

`failFast` của Enforcer quyết định ngừng kiểm tra **rules** sau rule đầu tiên thất bại. Reactor `-ff` quyết định ngừng build **modules** sau project failure. Đừng gộp hai cấp điều khiển này.

### 21.5. Skip tests không tương đương pass

`-DskipTests` có thể bỏ thực thi tests dù Enforcer PASS. Một build có tests skipped không chứng minh code đã được kiểm thử. Đối với CI, đọc Surefire XML/test count, không chỉ dòng BUILD SUCCESS.

---

## 22. Parent POM và reactor nhiều module

Nếu parent khai Enforcer execution trong `build/plugins` và child khai parent relationship, execution có thể được **kế thừa** và chạy ở mỗi module khi đến `validate`. Điều này hợp lý cho rules phiên bản Maven/Java chung.

Nhưng rule:

~~~xml
<requireFilesExist>
    <files>
        <file>${project.basedir}/ci/quality-gate.txt</file>
    </files>
</requireFilesExist>
~~~

sẽ dùng `project.basedir` của **module hiện tại**. Nếu file chỉ nằm ở root, các child modules không có file tương ứng có thể FAIL.

Giải pháp:

- Chỉ đặt file/env gate ở đúng module/profile sở hữu yêu cầu.
- Với rule chỉ dành root, cân nhắc `<inherited>false</inherited>` tại execution phù hợp.
- Parent `pluginManagement` chỉ quản lý version/config khi plugin được dùng; không mặc nhiên kích hoạt mọi execution ở mỗi child.
- Xem effective POM của đúng module, không chỉ root POM.
- Khi dùng `-pl`/`-am`, nhớ rằng modules không nằm trong invocation sẽ không được kiểm chứng.

Không nói “mọi module đã pass” từ một lần `mvn -pl :one-module verify` chỉ chọn một module.

---

## 23. Lệnh kiểm tra effective POM, profile và reports

~~~bash
mvn help:effective-pom
mvn help:active-profiles
mvn -Pci-gates help:active-profiles
mvn help:effective-pom -Pci-gates
mvn clean verify
~~~

Xác nhận:

- Enforcer 3.6.3 có execution `enforce-tool-versions`.
- Khi bật `ci-gates`, execution `enforce-ci-prerequisites` cũng có hiệu lực.
- Compiler 3.14.1 dùng release17.
- Surefire 3.5.4 chạy `EnvironmentAppTest` gồm 2 tests.
- JAR Plugin 3.4.2 tạo binary JAR đúng tọa độ.

Báo cáo kiểm thử thường ở:

~~~text
target/surefire-reports/
  TEST-vn.example.gates.EnvironmentAppTest.xml
~~~

Trong build pass, cần có **2 tests run, 0 failures/errors**. Nếu Enforcer FAIL ở validate, không coi report cũ từ build trước là test của invocation thất bại.

Kiểm tra archive và chạy:

~~~bash
jar tf target/environment-gate-demo-1.0.0.jar
java -jar target/environment-gate-demo-1.0.0.jar
~~~

Stdout chương trình:

~~~text
ENVIRONMENT READY
~~~

---

## 24. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân điển hình | Hướng xử lý |
| --- | --- | --- |
| Maven version rule FAIL | Maven ngoài range [3.9,4) | Kiểm tra Maven executable/Wrapper |
| Java version rule FAIL | JVM chạy Maven dưới Java17 | Kiểm tra JAVA_HOME, Maven runner JDK |
| Maven Java17 nhưng compiler fail | JDK compiler khác/thiếu | Kiểm tra Toolchains và Compiler Plugin |
| Java trên PATH khác Maven Java | Launch environment khác | Tin `mvn -version` cho Maven JVM |
| Env var rule FAIL | Chưa set `DEMO_CI_READY=yes` | Truyền biến vào đúng Maven process |
| Property rule FAIL | `deploy.target` thiếu hoặc sai | Dùng test/staging đúng policy |
| Files rule FAIL | `ci/quality-gate.txt` thiếu | Kiểm tra basedir và file source |
| Profile CI không chạy | Không dùng `-Pci-gates` | Kiểm tra active-profiles |
| Compiler báo release17 unsupported | Compiler JDK quá cũ | Chọn JDK mới, không bỏ target17 |
| Plugin resolution FAIL | Repository/proxy/certificate/cache | Chẩn đoán Maven repository |
| Enforcer PASS nhưng database fail | Env rules không kiểm service health | Thêm integration readiness tests |
| CI báo xanh dù lỗi rule | Enforcer skip/fail=false hoặc Reactor -fn | Sửa policy, giữ exit nonzero |
| Test count bằng 0 | Tests bị skip/discovery sai | Xem Surefire reports và naming |
| Child module báo thiếu file ở root | project.basedir trỏ child | Đổi owner/path của rule |
| Build local PASS, CI FAIL | Khác JDK/OS/env/secrets/network | So sánh tool/runtime versions |
| Artifact không chạy dù build PASS | Packaging/launcher/runtime khác | Smoke test trên Java runtime đích |

---

## 25. Bài tập thực hành

### Bài A — Ba phiên bản Java

`mvn -version` báo Java21, `javac -version` báo 17 và POM có `maven.compiler.release=17`. Enforcer kiểm giá trị nào? Compiler Plugin thực sự dùng compiler nào nếu Toolchains được bật?

### Bài B — Baseline

Tạo 4 file từ mục 9. Chạy:

~~~bash
mvn clean verify
java -jar target/environment-gate-demo-1.0.0.jar
~~~

Chứng minh 2 unit tests PASS và stdout `ENVIRONMENT READY`.

### Bài C — Bật CI profile

~~~bash
DEMO_CI_READY=yes mvn -Pci-gates "-Ddeploy.target=test" clean verify
~~~

Nêu tên 2 executions ở validate và từng rule kiểm tra gì.

### Bài D — Sai environment variable

~~~bash
DEMO_CI_READY=no mvn -Pci-gates "-Ddeploy.target=test" clean verify
~~~

Tại sao build fail trước compiler? Có được báo tests đã pass khi chúng chưa chạy không?

### Bài E — Sai property

~~~bash
DEMO_CI_READY=yes mvn -Pci-gates "-Ddeploy.target=production" clean verify
~~~

Giải thích regex và vì sao command không deploy production.

### Bài F — Thiếu file

Trong bản sao project, đổi tên `ci/quality-gate.txt`. Rule nào fail? File tồn tại nhưng nội dung sai có được rule phát hiện không?

### Bài G — Maven/Java ranges

So sánh `[17,)` và `[17,18)`. Tại sao Maven chạy JDK21 có thể compile Java17 bytecode với `--release17` nhưng không pass rule thứ hai?

### Bài H — Maven Wrapper

Khi thêm Wrapper vào project khác, so sánh `mvn -version` với `./mvnw -version`. Wrapper có tự cài JDK không?

### Bài I — Toolchains

Maven chạy JDK21, Compiler Plugin chọn JDK17. Cần logs/cấu hình gì để chứng minh compiler thật và release target đúng?

### Bài J — Multi-module

Parent có requireFilesExist sử dụng `project.basedir`. Vì sao child không thấy file ở root? Đề xuất profile/module owner đúng.

### Bài K — Bypass Enforcer

Chạy `-Denforcer.skip=true` trong bản sao thực hành. Vì sao successful build không có nghĩa gate đã pass?

### Bài L — CI exit code

Viết Bash script bắt `$?` ngay sau Maven rồi `exit "$status"`. Điều gì xảy ra khi đặt `echo` trước `$?` hoặc pipe `tee` không có `pipefail`?

### Bài M — Extra requirements

Một biến DB host đã có nhưng database chưa hoạt động. Thiết kế health check có timeout và integration test để phân biệt presence với readiness.

### Bài N — Khôi phục build

Đặt env `yes`, property `staging`, file marker đúng, chạy `mvn -Pci-gates ... clean verify`. Xác nhận exit 0, Enforcer PASS, 2 tests PASS.

---

## 26. Checklist áp dụng thực tế

- [ ] Đã công bố dải Maven/JDK versions hỗ trợ.
- [ ] Dùng `mvn -version` để xác định Java chạy Maven, không đoán theo PATH.
- [ ] Kiểm tra compiler JDK và target release riêng.
- [ ] Enforcer Plugin ghim version, `enforce` bind validate.
- [ ] Maven/Java rules rõ version ranges, có message dễ xử lý.
- [ ] Env/property/file rules có phạm vi profile/module hợp lý.
- [ ] Đã kiểm tra os/arch nếu app dùng native tools.
- [ ] Không coi env var có mặt là bằng chứng service ready.
- [ ] Không chứa secrets trong POM/source/log.
- [ ] Có Maven Wrapper nếu nhóm cần Maven distribution thống nhất.
- [ ] Toolchains được kiểm chứng khi compiler/test JVM khác Maven JVM.
- [ ] CI thực thi tests, không chỉ validate.
- [ ] Không cho bypass bằng enforcer.skip/fail=false, skipTests hoặc -fn nếu trái chính sách.
- [ ] Đọc reports/test count và giữ numeric Maven exit code.
- [ ] Với reactor, kiểm tra module coverage và `project.basedir`.
- [ ] Không phát hành artifact chỉ vì `jar` tồn tại nếu quality gates chưa pass.

**Kết luận:** Kiểm tra đúng Maven, Java/JDK và yêu cầu môi trường là bước đầu tiên của cổng chất lượng. Maven Enforcer Plugin giúp thất bại sớm tại `validate`; Compiler/Toolchains, unit/integration tests và CI health checks bổ sung những kiểm chứng khác. Chỉ coi build đạt khi **đúng môi trường, tests thực sự chạy, các module cần thiết đã được kiểm tra và exit code phản ánh chính xác thất bại/thành công**.

## 27. Tài liệu chính thức

- [Apache Maven Enforcer Plugin — Usage](https://maven.apache.org/enforcer/maven-enforcer-plugin/usage.html): bind `enforce`, `fail`, `skip`, `failFast`.
- [Enforcer Goal — enforcer:enforce](https://maven.apache.org/enforcer/maven-enforcer-plugin/enforce-mojo.html): default phase validate.
- [Maven Enforcer Built-in Rules](https://maven.apache.org/enforcer/enforcer-rules/index.html).
- [Require Maven Version](https://maven.apache.org/enforcer/enforcer-rules/requireMavenVersion.html).
- [Require Java Version](https://maven.apache.org/enforcer/enforcer-rules/requireJavaVersion.html).
- [Version Range Specification](https://maven.apache.org/enforcer/enforcer-rules/versionRanges.html).
- [Require Environment Variable](https://maven.apache.org/enforcer/enforcer-rules/requireEnvironmentVariable.html).
- [Require Property](https://maven.apache.org/enforcer/enforcer-rules/requireProperty.html).
- [Require Files Exist](https://maven.apache.org/enforcer/enforcer-rules/requireFilesExist.html).
- [Require OS](https://maven.apache.org/enforcer/enforcer-rules/requireOS.html).
- [Apache Maven Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html).
- [Maven Compiler Plugin — Set Release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html).
- [Maven Toolchains Plugin](https://maven.apache.org/plugins/maven-toolchains-plugin/).
- [Maven Wrapper](https://maven.apache.org/tools/wrapper/).
- [Maven Surefire Plugin — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html).
