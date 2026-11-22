# Phân biệt chuyển runtime Maven với chuyển mô hình POM

## 1. Hai loại nâng cấp khác nhau, không nên làm đồng thời theo phản xạ

Khi một nhóm nói “nâng cấp từ Maven 3 lên Maven 4”, câu đó có thể chỉ **hai công việc khác nhau**:

1. **Chuyển runtime Maven**: thay Maven executable/distribution từ Maven 3 sang Maven 4. Maven 4 sẽ đọc POM, dựng effective model, resolve artifacts và gọi plugins. Trong giai đoạn này file `pom.xml` **vẫn có thể giữ `modelVersion=4.0.0`**.
2. **Chuyển mô hình POM**: sửa Build POM trong repository từ **model 4.0.0 sang model 4.1.0** để dùng ngôn ngữ khai báo mới: `root="true"`, `<subprojects>`, parent/subproject inference, `bom` packaging và một số tính năng Maven 4-only. **Maven 3 không build được một source POM model 4.1.0**.

Đổi runtime và đổi POM model không phải cùng một phép biến đổi. Chúng có lịch kiểm tra, tiêu chí tương thích, rủi ro và cách rollback khác nhau. Apache Maven đề xuất tiến trình ba bước: chuẩn bị dự án trên Maven 3 mới; chạy song song Maven 3 và Maven 4 với ít thay đổi nhất; chỉ sau khi từ bỏ Maven 3 build mới áp dụng các tính năng POM riêng của Maven 4.

**Nguyên tắc xuyên suốt:** đừng đổi `<modelVersion>4.0.0</modelVersion>` thành `4.1.0` chỉ vì `mvn --version` đã hiện Maven 4. Và đừng kỳ vọng đổi `modelVersion` trong Git sẽ tự cài Maven 4 cho laptop, IDE và CI.

Bài thuộc nhóm **Nâng cấp Maven** của Build Tool Maven; mục tiêu là hiểu ranh giới giữa Maven executable, Maven model, Java JDK, plugins và POM của artifact được phát hành, sau đó biết cách tổ chức migration có bằng chứng.

## 2. Sáu trục version cần phân biệt

| Trục | Nguồn sự thật | Ví dụ | Ý nghĩa |
| --- | --- | --- | --- |
| Maven runtime | `mvn --version` hoặc Maven Wrapper distribution | Maven 3.x / Maven 4.x | Engine chạy lifecycle, Resolver, plugins, model validator |
| Maven POM model | `<modelVersion>` trong `pom.xml` | `4.0.0` / `4.1.0` | Cấu trúc và ngữ nghĩa Build POM |
| Maven project version | `<version>` của project/parent | `1.0.0` / `1.1.0` | Version trong GAV artifact |
| JVM chạy Maven | Java được `mvn --version` báo | JDK 17 / JDK 21 | JVM chạy Maven core và plugin code |
| Java target của sản phẩm | `maven.compiler.release` hoặc `<release>` | 8, 11, 17, 21 | Java language/API/classfile compatibility |
| Plugin version | `<build><plugins>` / `pluginManagement` | Compiler Plugin 3.14.0 | Plugin implementation/API/runtime requirements |

Một dự án có thể chạy **Maven 4 trên JDK 17**, có **POM model 4.0.0**, phát hành **artifact version 1.0.0** và compile mã **target Java 11**. Bốn con số đó không mâu thuẫn.

### Ví dụ đọc đúng POM

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example.maven</groupId>
    <artifactId>hello-service</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
</project>
~~~

- `modelVersion=4.0.0`: POM model, **không phải** Maven runtime 4.
- `version=1.0.0`: GAV, không phải JDK version.
- `maven.compiler.release=17`: Java target, không yêu cầu POM model 17.
- `mvn --version`: Maven executable/JDK đang được dùng, **không thể suy ra hoàn toàn từ đoạn POM**.

## 3. Ma trận tương thích cơ bản

| Maven executable | Source Build POM model | Build từ source được hỗ trợ? |
| --- | --- | --- |
| Maven 3 | 4.0.0 | Có, với plugin/JDK đáp ứng yêu cầu |
| Maven 4 | 4.0.0 | **Có**, đây là hướng chuyển runtime trước |
| Maven 4 | 4.1.0 | Có, dùng tính năng riêng của Maven 4 |
| Maven 3 | 4.1.0 | **Không**, Maven 3 không hỗ trợ mô hình mới |

“Được hỗ trợ về POM model” không bảo đảm build luôn PASS. Maven 4 có thể thay validation, plugin behavior, lifecycle/Resolver và minimum Java runtime. Một project model 4.0.0 từng PASS ở Maven 3 vẫn cần **verify đầy đủ trên Maven 4**.

Nếu tổ chức còn CI Maven 3 hoặc plugin/tool cần Maven 3 làm build engine, hãy giữ model 4.0.0 cho tới khi các hệ thống đó được chuyển. Chỉ chuyển model 4.1.0 sau khi có quyết định **ngừng hỗ trợ Maven 3 build từ source**.

## 4. Chuyển runtime Maven thực sự thay những gì?

Maven runtime là chương trình `mvn` hoặc Maven distribution được Wrapper gọi. Thay runtime có thể ảnh hưởng:

- POM parsing, interpolation, inheritance, profile activation và validation severity.
- Dependency, parent, BOM và plugin resolution qua Maven Resolver.
- CLI options, logs, root directory detection và reactor ordering.
- Lifecycle phases, custom goal executions và hành vi build đa dự án.
- Plugin API compatibility; một plugin cũ có thể dùng Maven 2/3 internals không còn được hỗ trợ.
- Maven core extensions, class realms, plugin/extension dependency boundaries.
- Default behavior của plugin hoặc lifecycle ở một số trường hợp.
- Java chạy Maven: **Maven 4 yêu cầu Java 17+** theo tài liệu chính thức.

Chuyển runtime **không tự thay**:
- Project `<version>` hoặc GAV.
- `maven.compiler.release` của sản phẩm.
- Java source code sang JPMS.
- POM schema lên 4.1.0.
- Dependency versions/Plugin versions đã được pin, trừ khi còn dùng defaults/inheritance hoặc build behavior khác.

### Kiểm tra runtime thay vì đoán

~~~bash
mvn --version
java -version
javac -version
~~~

`mvn --version` quan trọng nhất vì nó cho biết Maven và JVM của **Maven process**. `java -version` hay Project SDK trong IDE có thể khác khi `JAVA_HOME`, PATH, Maven Runner JDK hoặc Toolchains khác nhau.

## 5. Chuyển mô hình POM thay đổi cú pháp và ràng buộc của source

Maven 3 hỗ trợ model 4.0.0. Maven 4 vẫn hỗ trợ 4.0.0 và thêm model 4.1.0 dành cho Build POM.

Những tính năng đáng cân nhắc trong model 4.1.0:

1. Thuộc tính `root="true"` đánh dấu root project.
2. `<subprojects>` và `<subproject>` thay cho `<modules>` và `<module>`.
3. Tự suy parent groupId/artifactId/version dựa trên quan hệ parent/project.
4. Suy version của dependency vào sibling subproject khi điều kiện được đáp ứng.
5. Packaging mới `bom` phân biệt Bill of Materials với parent `pom`.
6. Các phần mở rộng model và profiles theo Maven 4.
7. Một số cách khai báo source directory và build layout mới.

**Không phải mọi tính năng Maven 4 runtime đều cần model 4.1.0.** Apache Maven nói rõ Maven 4.0.x có thể dùng model 4.0.0 nếu không cần model-specific features.

Một root POM model 4.1.0 minh họa:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.1.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.1.0 https://maven.apache.org/xsd/maven-4.1.0.xsd"
         root="true">
    <modelVersion>4.1.0</modelVersion>
    <groupId>vn.example.platform</groupId>
    <artifactId>platform</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <subprojects>
        <subproject>api</subproject>
        <subproject>service</subproject>
    </subprojects>
</project>
~~~

Đây là **ví dụ cấu trúc Maven 4-only**, giả định `api/pom.xml` và `service/pom.xml` tồn tại. Không dùng nguyên xi làm project Java runnable một module ở phần sau.

### Không sửa bằng find/replace toàn bộ

Một PR đơn giản đổi mọi chữ `4.0.0` thành `4.1.0` có thể:
- Vô tình thay artifact/plugin versions hoặc URLs không liên quan.
- Làm namespace/schemaLocation thiếu nhất quán.
- Mất Maven 3 build compatibility không có nhu cầu thực.
- Che các lỗi plugin/JDK chưa được giải quyết.
- Không kiểm chứng các Maven 4-specific features thực sự sử dụng.

Chỉ đổi model sau khi đã xác minh runtime migration, xác định tính năng cần dùng và có test matrix/rollback.

## 6. Maven 4 cần JDK 17 để chạy, không ép ứng dụng phải target Java 17

Theo tài liệu Maven 4, **Java 17 là minimum runtime để chạy Maven 4**. Điều đó **khác** mức Java mà Compiler Plugin nhắm tới.

Ví dụ bạn dùng Maven 4 với JDK 17, nhưng project có:

~~~xml
<properties>
    <maven.compiler.release>11</maven.compiler.release>
</properties>
~~~

Khi dùng compiler/JDK phù hợp, Java sources được compile theo language/API platform Java 11. Maven 4 runtime vẫn chạy trên JDK 17.

Đừng nhầm:
- **Maven JVM JDK 17**: công cụ build chạy bằng Java 17.
- **Compiler `--release 11`**: sản phẩm nhắm APIs/bytecode Java 11.
- **Runtime test trên Java 11**: bước riêng cần có nếu ứng dụng phải chạy trên Java 11.

`--release 11` không tự đảm bảo dependencies đều có bytecode tương thích Java 11. Dùng Toolchains và integration tests trên runtime đích khi cần.

**Không ghi `<modelVersion>17</modelVersion>`** để target Java 17. `modelVersion` không có ý nghĩa Java language level.

## 7. Quy trình nâng cấp ba giai đoạn

~~~text
A. PREPARE — Maven 3 và model 4.0.0
   Baseline PASS, pin plugin versions, loại warnings
                 |
                 v
B. RUNTIME TRIAL — Maven 4 và model vẫn 4.0.0
   Cùng Git commit, POM, JDK, goals, kiểm tra song song
                 |
                 v
C. POM MODEL MIGRATION — model 4.1.0 (tùy chọn)
   Chỉ sau khi chấp nhận bỏ Maven 3 làm builder
   Đổi POM features, review consumer compatibility
~~~

Ba bước này được hướng dẫn chính thức trong **Starting with Maven 4**. Đặc biệt không cần làm C ngay khi B hoàn tất.

Lợi ích của việc tách:
- Biết lỗi do **runtime Maven 4** hay do **model 4.1.0**.
- Dễ rollback một thay đổi ở một thời điểm.
- Dễ review plugin/JDK updates.
- Giữ Maven 3 CI hoạt động trong giai đoạn quá độ.
- Kiểm tra Maven 3 consumers độc lập với Maven 3 build ability.

## 8. Giai đoạn A: baseline Maven 3 và kiểm kê

Trên checkout đã được duyệt:

~~~bash
git rev-parse --verify HEAD
git status --porcelain=v1 --untracked-files=all
mvn --version
mvn -B -ntp clean verify
~~~

Ghi lại:
- Git SHA, working directory, dirty/untracked state.
- Maven executable và JVM của Maven 3.
- POM root, child modules, parents, imported BOMs, profiles/settings.
- Plugins và extensions; plugin versions/requirements.
- Số tests được Surefire/Failsafe chạy thật, skipped/failed counts.
- Maven command chính thức của CI và những quality gates đã được bind.
- JAR/WAR output, runtime smoke test và artifact checksum khi cần.
- Maven Wrapper version/config và IDE Maven Runner JDK.

Có thể xuất effective model và active profiles:

~~~bash
mvn -B -ntp help:effective-pom -Doutput=target/effective-pom.xml
mvn -B -ntp help:active-profiles
~~~

Nếu parent POM không resolve, `help:effective-pom` cũng có thể fail; khi đó xử lý parent/mirror trước.

### Vì sao cần dọn warnings khi còn ở Maven 3?

Maven 4 có **stricter model validation** và một số cấu hình trước đây chỉ được cảnh báo nay có thể bị từ chối. Ví dụ:
- Duplicate plugin declarations trong `<build><plugins>`.
- POM/plugin configuration không hợp lệ.
- Tham chiếu property nội bộ cũ.
- Custom lifecycle phase binding không còn được hỗ trợ giống trước.

Cần sửa cấu hình đúng, không tắt validation để làm build xanh. Các sửa tương thích Maven 3 nên được thực hiện trước khi thay runtime để giảm nhiễu.

## 9. Giai đoạn B: chạy Maven 3 và Maven 4 với POM 4.0.0

Mục tiêu là thay **chỉ Maven executable** trong điều kiện có thể.

Bản chạy A (terminal/workspace đã chọn Maven 3):

~~~bash
mvn --version
mvn -B -ntp clean verify
~~~

Bản chạy B (terminal/workspace khác đã chọn Maven 4):

~~~bash
mvn --version
mvn -B -ntp clean verify
~~~

**Hai dòng `mvn` trông giống nhau không chứng minh hai runtimes khác nhau.** Phải kiểm tra output `mvn --version` của từng môi trường. Nếu dùng đường dẫn tuyệt đối, macOS/Linux thường có `bin/mvn`, Windows thường có `bin/mvn.cmd`; dùng paths thực tế thay vì dựa vào alias giả định.

Giữ cố định:
- Git commit và POM file content.
- JDK major/vendor khi khả thi.
- Active profiles, settings/mirrors, repositories.
- Maven goals, module selection (`-pl`, `-am`) và skip flags.
- Test environments và network policies.

Nên dùng **workspace riêng cho mỗi Maven run** để tránh `target/`/generated outputs đè nhau. Có thể dùng local Maven repositories riêng để cô lập cache nếu ngân sách disk/network và policy cho phép, nhưng phải ghi rõ đó là biến khác và đánh giá ảnh hưởng.

### Đối chiếu bằng chứng

| Chỉ số | Maven 3 | Maven 4 | Diễn giải |
| --- | --- | --- | --- |
| `mvn --version` | Maven 3 thật | Maven 4 thật | Runtime đã thay đúng |
| Git SHA + POM SHA | Giá trị gốc | Giá trị gốc | Source và model giống nhau |
| `clean verify` | Exit code/log | Exit code/log | So lifecycle result |
| Surefire/Failsafe | Tests/skips/fails | Tests/skips/fails | Tránh pass nhờ skip |
| Plugins | Goals/version | Goals/version | Tìm compatibility khác |
| JAR/WAR | Manifest/runtime | Manifest/runtime | Hành vi artifact cuối |
| Dependency graph | Resolved versions | Resolved versions | Kiểm tra upstream divergence |
| SHA-256 | Digest | Digest | Không mặc định phải bằng nhau |
| CI reports | Archived | Archived | Bằng chứng review/rollback |

**JAR hash không tự phải giống nhau** nếu build chưa được cấu hình reproducible hoặc Maven/plugins ghi timestamps/order/metadata khác. Cần so contents/API/runtime tests và chỉ yêu cầu exact digest equality khi đã thiết kế reproducible build.

## 10. Maven Wrapper: runtime version còn nằm trong CI và IDE

Nếu project có Maven Wrapper, thường có:

~~~text
mvnw
mvnw.cmd
.mvn/wrapper/maven-wrapper.properties
~~~

`distributionUrl` trong wrapper properties quyết định Maven distribution được tải/chạy. Thay URL đó là **runtime cutover**, không phải đổi `modelVersion`.

Linux/macOS:

~~~bash
./mvnw --version
./mvnw -B -ntp clean verify
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd -B -ntp clean verify
~~~

Các lệnh chỉ áp dụng khi project **đã có Wrapper hợp lệ**. Khi nâng:
- Pin Maven distribution theo release/policy được duyệt.
- Kiểm tra Wrapper scripts/config integrity.
- CI phải dùng đúng Wrapper, không vô tình gọi Maven installed binary.
- IDE Maven Runner có thể dùng bundled/external Maven khác, cần kiểm tra.
- Java JDK cho Maven 4 phải là 17+.
- Parent/BOM/plugin versions và repositories vẫn là các đầu vào riêng.

**Maven Wrapper không tự pin JDK**. Nếu chỉ đổi Maven Wrapper mà CI image còn Java 11, Maven 4 sẽ không chạy; đổi model 4.1.0 cũng không sửa được.

## 11. Plugin migration là vấn đề độc lập với POM model

Một POM có thể giữ model `4.0.0` nhưng vẫn gặp lỗi khi Maven 4 chạy vì plugin không tương thích Maven core/API.

Apache Maven Compiler Plugin có dòng **3.x tương thích Maven 3**, đồng thời có **4.x beta** cần các Maven 4 runtime cụ thể. Chẳng hạn Compiler Plugin 3.14.0 là một bản 3.x dùng được trong giai đoạn thử Maven 3/Maven 4; không nên đổi thẳng sang Compiler Plugin 4.x beta nếu project còn phải chạy Maven 3.

Ví dụ plugin fragment:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.14.0</version>
</plugin>
~~~

Đoạn này phải được đặt dưới `<build><plugins>` trong POM đầy đủ. Những plugin versions khác cũng có minimum Maven/JDK requirements riêng, xem **Plugin Details → System Requirements** và changelog.

Phân biệt:
- **Plugin version upgrade**: thay cách thực thi compiler/tests/packaging.
- **Maven runtime upgrade**: thay Maven core/execution engine.
- **POM model upgrade**: thay schema của Build POM.
- **Java target upgrade**: thay language/API/classfile target.

Một plugin error không thể được “chữa” chỉ bằng đổi modelVersion. Và đổi Compiler Plugin sang 4.x không tự cài Maven 4 binary.

## 12. Những khác biệt Maven 4 có thể ảnh hưởng dù POM vẫn 4.0.0

| Đầu mục | Điều cần kiểm tra |
| --- | --- |
| Duplicate plugin declarations | Maven 4 có thể fail khi Maven 3 trước đây chỉ warn |
| Plugin API/internals | Plugin hoặc core extension cũ có thể không chạy |
| Root directory detection | Maven 4 khuyến khích `.mvn` root marker hoặc model root attribute |
| Lifecycle phase bindings | `pre-integration-test`/`post-integration-test` có thay đổi về model thực thi |
| Reactor multi-project | Dependency order, failure recovery, custom build goals |
| Maven Resolver | Mirror, repository metadata, negative cache/validation |
| Install/Deploy Plugin | Thay đổi default `installAtEnd`/`deployAtEnd` trong Maven 4 |
| Maven properties | Một số property nội bộ cũ deprecated/removed |

Theo migration guide, các phase cũ `pre-integration-test`/`post-integration-test` được thay bằng **`before:integration-test`** và **`after:integration-test`** trong Maven 4. Nếu project còn build bằng Maven 3, **không máy móc ghi cú pháp mới vào mọi POM 4.0.0** trước cutover; phải kiểm tra phiên bản runtime hiểu được phase/goal nào.

Tài liệu Maven 4 cũng nêu mặc định `installAtEnd=true` và `deployAtEnd=true` thay cho hành vi trước ở một số Maven Install/Deploy Plugin versions. **Điều này không khiến `mvn verify` tự install/deploy**. Nó chỉ liên quan khi thực sự chạy phases/goals ghi artifacts local/remote. Không thử `deploy` trên kho production khi chưa được cấp phép.

## 13. Ví dụ Java 17: giữ một POM `4.0.0` dùng cho hai runtime

Dựng một project đơn module để tránh nhầm lẫn với POM 4.1.0:

~~~text
maven-runtime-compat-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/maven/RuntimeModelDemo.java
    └── test/java/vn/example/maven/RuntimeModelDemoTest.java
~~~

Yêu cầu: JDK 17+, một Maven 3.9+ environment, một Maven 4 environment được phép dùng, Maven repositories resolve được plugin/JUnit dependencies. Không dùng Docker, database hay deploy repository.

### 13.1. File `pom.xml` đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example.maven</groupId>
    <artifactId>maven-runtime-compat-demo</artifactId>
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
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
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
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.maven.RuntimeModelDemo</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Điểm quan trọng:
- XML namespace và `modelVersion` đều là **4.0.0**, không sử dụng Maven 4-specific schema.
- Project GAV là `vn.example.maven:maven-runtime-compat-demo:1.0.0`.
- `maven.compiler.release=17` là Java target.
- JUnit Jupiter chỉ dùng ở test scope.
- Compiler/Surefire/Jar/Clean Plugin versions được pin làm baseline.
- Jar Plugin tạo `Main-Class`, giúp `java -jar` chạy.
- Không có `<distributionManagement>` và không cần `mvn deploy`.

Đây là POM dành cho bài học, **không khẳng định versions là latest**. Nếu Maven 4 RC/plugin combination trên môi trường thử có incompatibility, đọc log và chọn bản plugin tương thích được tài liệu xác nhận. Không đổi modelVersion để né plugin failure.

### 13.2. `RuntimeModelDemo.java`

Tạo `src/main/java/vn/example/maven/RuntimeModelDemo.java`:

~~~java
package vn.example.maven;

public final class RuntimeModelDemo {
    private RuntimeModelDemo() {
    }

    public static int addExactly(int left, int right) {
        return Math.addExact(left, right);
    }

    public static String banner() {
        return "MODEL=4.0.0; TARGET_JAVA=17; RESULT=OK";
    }

    public static void main(String[] args) {
        System.out.println(banner());
        System.out.println("SUM=" + addExactly(5, 7));
    }
}
~~~

Banner là một **string constant minh họa**, không đo runtime Maven đang chạy. Để biết runtime Maven 3/4 phải xem `mvn --version`.

### 13.3. `RuntimeModelDemoTest.java`

Tạo `src/test/java/vn/example/maven/RuntimeModelDemoTest.java`:

~~~java
package vn.example.maven;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class RuntimeModelDemoTest {
    @Test
    void bannerDeclaresModelAndJavaTarget() {
        assertEquals(
                "MODEL=4.0.0; TARGET_JAVA=17; RESULT=OK",
                RuntimeModelDemo.banner());
    }

    @Test
    void additionIsExact() {
        assertEquals(12, RuntimeModelDemo.addExactly(5, 7));
    }

    @Test
    void overflowFailsInsteadOfWrapping() {
        assertThrows(ArithmeticException.class,
                () -> RuntimeModelDemo.addExactly(
                        Integer.MAX_VALUE, 1));
    }
}
~~~

Đây là **ba test methods**: message, phép cộng và overflow. `Math.addExact` ném `ArithmeticException` khi int overflow. Surefire được cấu hình để tìm test tên `*Test`; dependency `junit-jupiter` có Jupiter engine phù hợp.

### 13.4. Chạy baseline

Trong Maven 3 terminal:

~~~bash
mvn --version
mvn -B -ntp clean verify
java -jar target/maven-runtime-compat-demo-1.0.0.jar
~~~

**Stdout chính xác của riêng lệnh `java -jar`**:

~~~text
MODEL=4.0.0; TARGET_JAVA=17; RESULT=OK
SUM=12
~~~

Khi dependencies/plugin versions resolve được, Maven `clean verify` sẽ compile Java 17, chạy ba unit tests rồi tạo JAR. `verify` **không tự install/deploy**.

Tại Maven 4 terminal/workspace **khác** với cùng source/POM, chạy lại **ba lệnh y hệt**, lưu `mvn --version` và các kết quả. Lý tưởng cả hai đều có 3 unit tests, cùng runtime stdout. **Không yêu cầu console Maven giống nhau từng dòng hoặc SHA-256 của JAR giống nhau nếu chưa chốt reproducible-build settings.**

## 14. Kiểm tra artifact và Java runtime sau build

Với demo:

~~~bash
jar tf target/maven-runtime-compat-demo-1.0.0.jar
java -jar target/maven-runtime-compat-demo-1.0.0.jar
~~~

Tìm các entry:

~~~text
META-INF/MANIFEST.MF
vn/example/maven/RuntimeModelDemo.class
~~~

JAR có thể chạy bằng Java 17+ tương thích nhờ main class và bytecode target 17. **Java runtime test** này độc lập với parser POM version: sau khi JAR được tạo, `java -jar` không đọc source `pom.xml` của project.

Không nhầm **resolve một dependency** với **thực thi bytecode**. Maven 3 consumer có thể resolve một JAR được Maven 4 phát hành nhưng chạy fail nếu JAR được compile cho Java cao hơn runtime consumer.

### So checksum khi cần truy vết

Linux/macOS có `sha256sum` hoặc `shasum -a 256` tùy OS:

~~~bash
sha256sum target/maven-runtime-compat-demo-1.0.0.jar
~~~

Checksum phải được tính từ artifact thực, không có hash cố định trong tài liệu. Hash khác giữa Maven 3 và Maven 4 **không tự chỉ ra lỗi** nếu timestamp, archive order, manifest hoặc plugin metadata khác. Khi cần binary reproducibility, cấu hình và kiểm tra độc lập mục tiêu đó.

## 15. Build POM và Consumer POM là hai vai trò khác nhau

Đây là khái niệm cần hiểu trước khi chuyển model 4.1.0.

**Build POM** trong Git chứa:
- Build plugins, executions, source directories.
- Parent, properties/profiles, dependencies.
- Project-specific configuration cần cho Maven xây dựng artifact.

**Consumer POM** được publish/install để downstream tools resolve:
- GAV, dependencies và dependency management liên quan.
- Parent/BOM metadata cần thiết theo chính sách xuất bản.
- Các phần model consumer cần, không nhất thiết mọi chi tiết build.

Maven 4 có cơ chế tạo consumer POM. Vì thế **Build POM model 4.1.0** có thể dùng Maven 4-only syntax, còn **metadata cho Maven 3 consumers** được chuyển về model 4.0.0 khi tính năng phù hợp.

### Phân biệt hai câu

- “Maven 3 project có thể dùng dependency JAR do Maven 4 build.” → **Có thể**, nếu artifact POM/bytecode/dependency graph tương thích.
- “Maven 3 checkout chính source có model 4.1.0 rồi build project ấy.” → **Không**, Maven 3 không hiểu Build POM model 4.1.0.

Đây là khác biệt giữa **consumer compatibility** và **builder compatibility**.

### Consumer POM không mặc định luôn fully flattened

Theo tài liệu Maven 4, POM mà consumers thấy không nhất thiết bị flatten hoàn toàn theo mọi version và packaging. Flattening là một policy/cấu hình riêng; ví dụ user property:

~~~text
-Dmaven.consumer.pom.flatten=true
~~~

Khi bật flatten, parent/build-only metadata có thể được xử lý/loại theo cách khác, nhưng behavior thực tế còn phụ thuộc Maven version, scopes và packaging. Với một số model-specific profiles, Maven có thể cảnh báo nếu không thể chuyển xuống consumer model 4.0.0 an toàn.

**Không khẳng định Maven 3 consumer chắc chắn chạy được chỉ vì build Maven 4 PASS**. Kiểm tra POM artifact publish thực tế và thử consumer Maven 3 độc lập.

## 16. Root detection: `.mvn` tương thích rộng hơn `root="true"`

Maven 4 cần xác định project root/top directory để hỗ trợ multi-project behavior và một số properties.

Hai hướng chính:
- Đặt thư mục **`.mvn`** tại root repository. Cách này đã được Maven 3 hỗ trợ.
- Đặt **`root="true"`** trên `<project>` model 4.1.0. Đây là Maven 4-only model feature.

Trong giai đoạn B đang giữ compatibility, dùng `.mvn` marker nếu phù hợp thay vì đổi model 4.1.0 chỉ để tắt cảnh báo root directory.

Thư mục `.mvn` có thể chứa Maven-specific config như `maven.config`, `jvm.config` hoặc Wrapper files; **không commit secrets**. Nếu team dùng directory property mới như `${project.rootDirectory}` hoặc `${session.rootDirectory}`, phải đánh giá khả năng chạy lại bằng Maven 3.

Một số property nội bộ cũ như `${executionRootDirectory}` và `${multiModuleProjectDirectory}` được tài liệu Maven 4 nêu là deprecated/removed; kiểm tra POM/plugins dùng chúng trước khi cutover.

## 17. `<modules>` và `<subprojects>` không phải Java JPMS

Maven 3 thường dùng:

~~~xml
<modules>
    <module>api</module>
    <module>service</module>
</modules>
~~~

Maven 4 model 4.1.0 có:

~~~xml
<subprojects>
    <subproject>api</subproject>
    <subproject>service</subproject>
</subprojects>
~~~

Cả hai là **POM fragments**, phải đặt trong root `<project>` đúng model. Maven 4 vẫn hỗ trợ `<modules>` vì tương thích; `<subprojects>` là cấu trúc mới và `<modules>` được deprecated trong model 4.1.0.

**Đừng nhầm Maven subproject với Java 9 `module-info.java`/JPMS.** Đổi tag Maven không tự biến ứng dụng thành named Java module, không tự đổi classpath sang module path.

Maven 4 còn có auto-discovery subprojects trong một số điều kiện, ví dụ parent packaging `pom`, không khai báo danh sách modules/subprojects và các thư mục con trực tiếp chứa POM. Không mặc định mọi folder có POM đều tham gia reactor; xác minh bằng Maven output và effective project graph.

## 18. Parent inference và sibling dependency version

Trong model 4.0.0 dùng Maven 3, child parent thường được khai báo:

~~~xml
<parent>
    <groupId>vn.example.platform</groupId>
    <artifactId>platform</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
<artifactId>service</artifactId>
~~~

Đây là **fragment trong child POM**, không phải POM độc lập. Với sibling dependency `api`, Maven 3 thường cần version từ dependencyManagement hoặc `<version>` hợp lệ.

Trong Maven 4 model 4.1.0, các chi tiết parent có thể được suy từ project structure, ví dụ:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.1.0">
    <modelVersion>4.1.0</modelVersion>
    <artifactId>service</artifactId>
    <parent/>
    <dependencies>
        <dependency>
            <groupId>vn.example.platform</groupId>
            <artifactId>api</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

**Đây là ví dụ Maven 4-only trong một multi-project build phù hợp**, không phải standalone runnable POM. `api` phải là sibling project được Maven 4 nhận diện để suy version.

Không copy `<parent/>` và dependency thiếu version từ model 4.1.0 vào model 4.0.0 khi CI vẫn chạy Maven 3. Ngay cả khi Maven 4 chấp nhận một số forms với model 4.0.0 trong các release candidate, **Maven 3 compatibility vẫn là tiêu chí cần kiểm tra độc lập**.

## 19. BOM packaging: trường hợp model 4.1.0 có ích thật

Maven 3 thường phát hành BOM là artifact POM có `<packaging>pom</packaging>` và `<dependencyManagement>`. Maven 4 model 4.1.0 có packaging riêng **`bom`**.

Ví dụ BOM Build POM Maven 4:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.1.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.1.0 https://maven.apache.org/xsd/maven-4.1.0.xsd">
    <modelVersion>4.1.0</modelVersion>
    <groupId>vn.example.platform</groupId>
    <artifactId>company-bom</artifactId>
    <version>1.0.0</version>
    <packaging>bom</packaging>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.10.2</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
~~~

Đây là **ví dụ Maven 4-only**, không chạy bằng Maven 3. Maven 4 có thể tạo consumer POM tương thích Maven 3 khi install/deploy BOM theo cơ chế POM chuyển đổi.

Lưu ý:
- `packaging=bom` chỉ dành cho Build POM model 4.1.0 trở lên.
- Maven 3 consumer thường import BOM qua dependency `type=pom`, `scope=import` trong `<dependencyManagement>`.
- `dependencyManagement` **không tự thêm** dependency vào classpath project.
- Nếu BOM import trong cùng reactor gây cảnh báo hoặc không resolve như mong muốn, đọc Maven 4 docs về external BOM resolution.
- Chỉ gọi bước publish vào repository staging/test nếu quyền và policy cho phép; không deploy production từ bài tập.

## 20. Dùng Maven Upgrade Tool để xem đề xuất trước khi sửa

Maven 4 release candidates có công cụ **`mvnup`** (từ dòng RC có tích hợp), hỗ trợ `check` và `apply`. Đây là công cụ **Maven 4**, không phải một lệnh có sẵn trong Maven 3.

Khi đã xác nhận installation có công cụ:

~~~bash
mvnup --help
mvnup check --model-version 4.0.0
~~~

Target 4.0.0 giúp đánh giá migration mà vẫn hướng tới Maven 3-compatible model.

Chỉ sau khi team quyết định dùng Maven 4-only features, kiểm tra đề xuất:

~~~bash
mvnup check --model-version 4.1.0 --all
~~~

Và **chỉ trong branch/worktree có quyền thay files**:

~~~bash
mvnup apply --model-version 4.1.0 --all
git diff -- pom.xml
~~~

`apply` **có thể sửa nhiều POMs** trong reactor. Phải review toàn bộ diff, giữ backup/version control, không chạy bừa trên workspace chung. `check` không thay `mvn clean verify`; nó là công cụ migration analysis, không xác minh mọi plugin/test behavior.

**Maven Upgrade Tool không tự cài Maven runtime cho developer/CI**, cũng không tự chứng minh consumer POM đã tương thích Maven 3. Đó là hai bước xác minh riêng.

## 21. CI matrix chuẩn cho giai đoạn dual support

~~~text
Reviewed Git SHA + POM model 4.0.0
                 |
       +---------+---------+
       |                   |
       v                   v
  Maven 3 runtime      Maven 4 runtime
  JDK 17+              JDK 17+
  clean verify         clean verify
       |                   |
       +---------+---------+
                 |
                 v
Compare test counts, plugin goals,
dependency tree, JAR behavior and CI logs
                 |
          +------+------+
          |             |
         PASS          FAIL
          |             |
          v             v
  Plan runtime cutover  Diagnose one difference
                 |
                 v
After Maven 3 retirement:
  Separate POM 4.1.0 PR + consumer tests
~~~

Mỗi matrix job cần:
- Workspace tách biệt, không cùng clean một `target/`.
- Maven/JDK thực tế được log.
- Same Git SHA/POM trong giai đoạn so runtime.
- Same profiles/settings/goals hoặc ghi chênh lệch có giải thích.
- Có Surefire/Failsafe reports, số tests chạy và skips.
- Packaged artifacts và smoke tests trên đúng file cuối.
- Không dùng `-DskipTests`/`-DskipITs` để pass release gate.
- Không deploy lên production repository trong job thử nghiệm.

**`mvn validate` pass chưa đủ để tuyên bố Maven 4-compatible**: mã phải compile, tests chạy, resources/package đúng và integrations cần thiết hoàn tất.

## 22. Khi Maven 4 fail với POM 4.0.0: đọc đúng nguyên nhân

| Triệu chứng | Nguyên nhân đáng kiểm tra | Không nên làm |
| --- | --- | --- |
| Maven 4 không khởi động | JDK chưa đủ Java 17 | Thay `modelVersion` tùy tiện |
| Duplicate plugin declaration fail | POM cấu trúc trùng | Bỏ validation |
| Plugin goal không load | Plugin/API/version incompatibility | Nâng mọi plugin major cùng lúc |
| Lifecycle phase không khớp | Bindings pre/post phase cũ | Đổi schema ngay mà chưa phân tích |
| Parent/BOM không resolve | GAV/relativePath/repository/mirror | Xóa toàn `.m2` |
| Compiler `release` không được hỗ trợ | JDK/Compiler Plugin | Bỏ qua unit tests |
| Surefire fails | Test assertions/fixture/JDK | `-DskipTests` rồi gọi PASS |
| Failsafe integration fails | Runtime service, packaged artifact | `-DskipITs` trong release |
| Maven 3 fail khi POM 4.1.0 | Maven 3 không hiểu model mới | Gọi là cache hỏng |
| Consumer Maven 3 fail | Published POM metadata, parent/BOM, bytecode | Kết luận mọi JAR Maven 4 đều không dùng được |

Mỗi failure phải có Maven goal, logs, effective POM, test reports hoặc GAV liên quan. Không suy lỗi cache chỉ vì đổi runtime xong thấy khác behavior.

## 23. Builder compatibility khác consumer compatibility

Một dự án Maven 4 producer có thể build bằng model 4.1.0 và tạo **Consumer POM model 4.0.0** cho downstream. Điều đó không làm Maven 3 đọc được chính source Build POM 4.1.0 của producer.

Cách kiểm chứng consumer compatibility:
1. Maven 4 build producer từ source model 4.1.0.
2. Install/publish vào **test local repository hoặc staging repository được phép**.
3. Đọc POM metadata thực sự consumer nhận, không chỉ source `pom.xml`.
4. Tạo Maven 3 consumer với dependency đúng GAV; chạy `mvn clean verify`.
5. So dependency graph, parent/BOM resolution, scopes và runtime tests.
6. Kiểm tra Java bytecode target và JDK của consumer.
7. Ghi rõ Consumer POM có flattening hay không, theo Maven version/policy.

**Maven 3 resolve được dependency không đồng nghĩa runtime Java 8 chạy được class target Java 17.** POM/build compatibility và Java binary compatibility là những ràng buộc độc lập.

## 24. Rollback: khác nhau khi chỉ đổi runtime và khi đã đổi model

### Nếu mới đổi runtime

Khi POM vẫn model 4.0.0:
- Khôi phục Maven Wrapper/CI distribution được duyệt.
- Giữ XML model 4.0.0.
- Khôi phục plugin changes không tương thích Maven 3 nếu có.
- Re-run Maven 3 `clean verify` và so baseline.

Đây là rollback engine, thường có phạm vi nhỏ hơn schema migration.

### Nếu đã đổi model 4.1.0

Không thể chỉ đổi con số `4.1.0` thành `4.0.0` nếu POM đã dùng:
- `root="true"`.
- `<subprojects>`.
- `<parent/>` và sibling version inference.
- `bom` packaging.
- Maven 4-only phase syntax/properties.

Muốn quay về Maven 3 cần **chuyển cấu trúc/tái bổ sung coordinates và versions**, xem lại parent/subprojects và chạy Maven 3 tests. Dùng branch/commit rollback có review, không global replace trong workspace chung.

## 25. Những sai lầm cần tránh

1. **Maven 4 executable yêu cầu modelVersion 4.1.0.** Sai: model 4.0.0 vẫn được hỗ trợ.
2. **Đổi modelVersion tự cài Maven 4.** Sai: phải chỉnh binary/Wrapper/CI.
3. **`modelVersion` là Java version.** Sai: Java target dùng `release`.
4. **Maven 4 cần JDK 17 nên tất cả thư viện phải target Java 17.** Sai.
5. **Maven 4 đọc model 4.0.0 nên mọi plugin cũ đều chạy.** Không được đảm bảo.
6. **Nâng Compiler Plugin 4.x giúp Maven 3 trở thành Maven 4.** Sai, còn gây incompatibility.
7. **POM 4.1.0 vẫn build được bằng Maven 3.** Sai.
8. **Consumer POM luôn fully flattened.** Không, phụ thuộc policy/version.
9. **Maven 3 không bao giờ dùng được artifact do Maven 4 tạo.** Sai, kiểm tra consumer metadata và Java target.
10. **Chạy `mvn install`/`deploy` là phép thử vô hại.** Chúng có side effects local/remote.
11. **Chỉ nhìn `mvn clean verify` text, không cần `mvn --version`.** Không biết runtime thật.
12. **Có JAR file nghĩa là tests đều chạy.** Không, xem Surefire/Failsafe reports.
13. **Đổi parent, plugin, JDK, runtime và model trong một PR để nhanh.** Làm giảm khả năng chẩn đoán.
14. **Đổi `<modules>` thành `<subprojects>` đồng nghĩa Java JPMS migration.** Không.
15. **Cùng SHA-256 là điều kiện bắt buộc cho mọi runtime comparison.** Chỉ đúng khi build được thiết kế byte-for-byte reproducible.
16. **Maven 4 source POM 4.1.0 tự tương thích mọi consumer.** Phải test published POM thực.

## 26. Bài tập tự luyện

**Bài 1:** Từ POM mẫu, chỉ ra `modelVersion`, GAV, Java target, Compiler Plugin version và Maven executable version. Vì sao chỉ câu cuối cần `mvn --version`?

**Bài 2:** Dựng project Java17/JUnit5 ở mục 13. Chạy Maven 3 `clean verify`, ghi ba test methods và stdout chính xác của `java -jar`.

**Bài 3:** Dùng cùng POM model4.0.0 trên Maven4 runtime, so output. Vì sao không đổi `modelVersion` trong bài thử này?

**Bài 4:** So Maven JVM JDK17 với Compiler `release=11`. Phải chạy integration tests trên Java11 hay không nếu sản phẩm cam kết tương thích Java11?

**Bài 5:** Viết fragment Maven3 `<modules>` và Maven4 `<subprojects>`; giải thích tại sao câu chuyện này không đụng Java `module-info.java`.

**Bài 6:** Khi Maven4 báo duplicate plugin declaration, giải thích vì sao sửa plugin declaration tốt hơn đổi POM schema 4.1.0.

**Bài 7:** Dựng parent/child fragment ở model4.1 với `<parent/>`; những thông tin nào Maven3 cần khai báo lại nếu rollback?

**Bài 8:** Phân biệt BOM packaging `pom` và `bom`. Consumer Maven3 cần POM artifact dạng nào để import BOM?

**Bài 9:** Dùng `mvnup check --model-version 4.1.0 --all` trong checkout thử. Tại sao chỉ sau review mới cân nhắc `apply`?

**Bài 10:** Lập CI matrix Maven3/4 giữ cùng SHA/JDK/POM, lưu test reports, plugin versions, artifact digest và lỗi đầu tiên.

**Bài 11:** Maven3 consumer resolve JAR do Maven4 build nhưng runtime Java11 fail. Có thể là lỗi modelVersion hay bytecode target?

**Bài 12:** Thiết kế rollback khác nhau cho tình huống (A) chỉ đổi Maven Wrapper, (B) đã sử dụng model4.1 subprojects/inference.

## 27. Checklist ra quyết định nâng cấp

1. Phân biệt Maven executable, POM model, project version, JDK và plugin versions.
2. Đã ghi `mvn --version` thật từ từng environment.
3. Maven 3 baseline `clean verify` pass trên Git SHA cụ thể.
4. Có plugin/core-extension inventory và compatibility assessment.
5. JDK chạy Maven 4 đáp ứng Java17+.
6. Java target và runtime sản phẩm được giữ như hợp đồng.
7. POM model4.0.0 được giữ khi thử Maven4 runtime lần đầu.
8. Maven3/Maven4 runs có cùng POM/source/goals/profiles.
9. Test counts, failures/skips và artifact behavior được đối chiếu.
10. Duplicate plugin/warnings/old properties được đánh giá.
11. Custom lifecycle bindings được kiểm tra qua logs.
12. Maven Wrapper, CI image, IDE Maven Runner đã đồng bộ.
13. Không vô tình dùng `-DskipTests` để làm xanh build.
14. Không `install`/`deploy` vào kho không được phép.
15. Có plan rollback runtime khi chỉ mới nâng Maven executable.
16. Team đã quyết định bỏ Maven3 builder trước khi chuyển model4.1.0.
17. Model4.1 XML namespace và schema được khai báo nhất quán.
18. Root/subproject/parent inference được review theo structure thực.
19. BOM packaging chỉ dùng với consumer POM compatibility test.
20. `mvnup check` đi trước `apply`; source diff được review.
21. Published Consumer POM được kiểm tra trên downstream Maven3 nếu cần.
22. Java classfile/API compatibility của artifact được test độc lập.
23. CI giữ logs, Git SHA, report counts và provenance/digest khi cần.
24. Release status Maven4 RC/GA được kiểm tra qua Apache Maven release history khi triển khai, không suy từ ví dụ.
25. Mục tiêu migration được ghi rõ: **runtime cutover**, **POM model features**, hay cả hai ở các giai đoạn khác nhau.

### Tổng kết

**Chuyển runtime Maven là đổi engine chạy build; chuyển mô hình POM là đổi cú pháp và khả năng biểu đạt của Build POM.** Maven 4 tiếp tục đọc model 4.0.0, vì vậy có thể nâng runtime và kiểm tra compatibility trước khi dùng model 4.1.0. Chỉ khi cần Maven 4-only model features và sẵn sàng ngừng Maven 3 builder mới nên đổi Build POM schema.

Một khía cạnh thứ ba là **Consumer POM**: Maven 4 có thể phát hành metadata để Maven 3 dùng dependencies, nhưng điều đó không làm Maven 3 build được source POM 4.1.0. Kiểm chứng cả consumer metadata, dependency graph và Java runtime behavior trên downstream thực tế.

Lộ trình đáng tin: **Maven 3 baseline → Maven 4 chạy POM4.0.0 → xử lý runtime/plugin differences → cutover → tùy chọn POM4.1.0 → downstream consumer tests**. Giữ môi trường kiểm soát, báo đúng tests đã chạy và có phương án rollback. Không dùng find/replace modelVersion hoặc skip tests làm phương pháp nâng cấp.

### Tài liệu tham khảo chính thức

- [Apache Maven — Starting with Maven 4](https://maven.apache.org/guides/mini/guide-migration-to-mvn4.html)
- [Apache Maven — What's New in Maven 4?](https://maven.apache.org/whatsnewinmaven4.html)
- [Apache Maven — Maven Releases History](https://maven.apache.org/docs/history)
- [Apache Maven — POM 4.0.0 Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Maven 4 Model Reference](https://maven.apache.org/ref/4-LATEST/api/maven-api-model/maven.html)
- [Apache Maven — Maven Upgrade Tool](https://maven.apache.org/tools/mvnup.html)
- [Apache Maven — Maven Wrapper](https://maven.apache.org/tools/mavenwrapper.html)
- [Apache Maven — Maven Plugins Compatibility Plan](https://maven.apache.org/developers/compatibility-plan.html)
- [Maven Compiler Plugin — System Requirements](https://maven.apache.org/plugins/maven-compiler-plugin/plugin-info.html)
- [Maven Compiler Plugin — Java release target](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Maven Surefire Plugin — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
