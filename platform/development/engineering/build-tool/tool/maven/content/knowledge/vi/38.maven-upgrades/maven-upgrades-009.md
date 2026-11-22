# Dùng công cụ hỗ trợ nâng cấp Maven và kiểm tra từng thay đổi được tạo

## 1. Tại sao “nâng cấp bằng công cụ” vẫn phải được kiểm tra?

Một dự án Java/Maven thường có nhiều lớp phiên bản: **Apache Maven runtime**, Maven Wrapper, JDK dùng để chạy Maven, Java target bytecode, parent POM, BOM, dependency versions, build/reporting plugins, extensions và cấu hình CI. Một công cụ có thể đề xuất hoặc thay đổi một vài lớp mà **không hiểu hết hợp đồng ứng dụng, giới hạn môi trường hay quy trình release**.

Ví dụ, nâng version `maven-compiler-plugin` trong `pom.xml` không đồng nghĩa đã nâng Apache Maven được chạy ở CI. Ngược lại, sửa `.mvn/wrapper/maven-wrapper.properties` để dùng Maven 4 không tự cập nhật các plugin chỉ tương thích Maven 3. Một thư viện có version mới nhất cũng chưa chắc phù hợp API, license, chính sách bảo mật hoặc JDK hiện tại.

**Mục tiêu bài này:** biết chọn đúng công cụ hỗ trợ nâng cấp, phân biệt lệnh **chỉ đọc/đề xuất** với lệnh **sửa file**, chuẩn bị baseline, chạy từng phép biến đổi có phạm vi hẹp, đọc mọi `git diff`, xác minh effective POM/dependency graph, chạy test và giữ khả năng rollback. Phần cuối có đường đi riêng khi muốn chuyển từ Maven 3 sang Maven 4.

Bài dùng Maven 3.9.x, Java 17 và một project chạy được làm ví dụ. Version trong lệnh/POM được pin để minh họa chứ không khẳng định là bản mới nhất hoặc bản vá bảo mật tại mọi thời điểm. Một số công cụ như `mvnup` thuộc Maven 4, **không** có sẵn trong Maven 3.

## 2. Phân biệt chính xác thứ cần nâng

| Thành phần | Thường nằm ở đâu? | Ví dụ thay đổi | Ai phải xác minh? |
| --- | --- | --- | --- |
| Maven distribution | `mvn -version`, Wrapper `distributionUrl`, runner image | Maven 3.9.x → Maven 4.x | Build/CI owners, plugin compatibility. |
| JDK chạy Maven | `JAVA_HOME`, runner image, `java -version` | JDK 11 → 17 | Toolchain/CI/runtime owners. |
| Java release target | `maven.compiler.release`, Compiler Plugin | 11 → 17 | Java source/consumer compatibility. |
| Parent POM | `<parent>` | Platform parent version | Parent inheritance/effective model. |
| BOM | `<dependencyManagement><scope>import</scope>` | Platform library set | Resolved graph và toàn reactor. |
| Direct dependencies | `<dependencies>` | commons-lang3 version | Source/API, runtime, security. |
| Build plugins | `<build><plugins>`, `<pluginManagement>` | Compiler/Surefire/JAR/Deploy | Goal parameters/lifecycle, minimum Maven. |
| Reporting plugins | `<reporting>` | Javadoc/Site | Report output, CI/docs. |
| Maven extensions | `.mvn/extensions.xml`, build extensions | Resolver/extension | Build startup, API/permissions. |
| Wrapper files | `mvnw`, `mvnw.cmd`, `.mvn/wrapper/*` | Distribution & wrapper script | Supply-chain, checksum, CI. |
| CI workflow | GitHub Actions/Jenkins/GitLab files | Matrix JDK/Maven, cache, secrets | Jobs/permissions/release gates. |

Không gộp các hàng trên thành “upgrade Maven version”. Mỗi loại có **đầu vào, kết quả và tiêu chí hoàn tất khác nhau**. Nên lập một ticket/PR theo từng nhóm rủi ro; ví dụ nâng một dependency ít ảnh hưởng trước, rồi đến parent/BOM, sau cùng mới đổi runtime Maven major.

## 3. Nhóm công cụ và phạm vi của từng công cụ

| Công cụ | Vai trò chính | Có tự sửa source không? |
| --- | --- | --- |
| **MojoHaus Versions Maven Plugin** | Liệt kê và cập nhật versions trong POM/parent/properties. | `display-*` không; `set-property`/`update-*`/`use-*` có. |
| **Apache Maven Wrapper Plugin** | Tạo/cập nhật wrapper scripts/config để pin Maven runtime. | **Có** trên `mvnw`, `mvnw.cmd`, `.mvn/wrapper/*`. |
| **Maven Upgrade Tool (`mvnup`)** | Kiểm và chuyển đổi POM khi nâng lên Maven 4. | `check` không; `apply` có. |
| **OpenRewrite Maven Plugin** | Recipe-based refactor POM/Java/XML/source ở phạm vi recipe. | `dryRun` tạo patch; `run` áp dụng sửa đổi. |
| **Maven Dependency Plugin** | Đọc graph, resolved versions, transitive paths. | `dependency:tree` là chẩn đoán, không sửa POM. |
| **Maven Help Plugin** | Xem `effective-pom`/`effective-settings`/profiles. | Không sửa source POM. |
| **Maven Enforcer Plugin** | Chặn build khi toolchain/dependency policies không đạt. | Thường kiểm/chặn, không nâng POM. |
| **Git** | So sánh, review, chia commit, rollback. | Lệnh inspect chỉ đọc; `restore`/`reset` có thể phá thay đổi. |
| **CI/test/security scanners** | Xác minh compile/test/runtime/security/compatibility. | Phụ thuộc công cụ, không được thay kết luận review. |

**Nguyên tắc kiểm soát:** công cụ nâng cấp chỉ **đề xuất và sửa phần cấu hình**; nhiệm vụ đánh giá đúng/sai, hợp đồng tương thích và quyết định merge thuộc người quản lý project.

## 4. Chuẩn bị nhánh làm việc sạch và ghi baseline

Trước khi chạy bất cứ lệnh `update`/`apply` nào:

~~~bash
git status --short
git branch --show-current
mvn -version
java -version
mvn -B -ntp clean verify
~~~

Trong project thật, cần ghi lại các mốc: source commit, Maven/JDK version, test pass/fail baseline, modules, profiles, active repositories, supported deployment platforms, dependency/security findings hiện tại.

**Nếu baseline đang fail**, phải ghi lỗi tồn tại trước upgrade, không gán mọi lỗi sau này cho công cụ. Đừng chạy một recipe lớn trên working tree có thay đổi chưa commit; trước tiên tạo branch/commit tách biệt hoặc một working copy chuyên dụng.

Chỉ nên tiếp tục khi biết:

- Lệnh build chuẩn là gì: `mvn verify` hay `./mvnw verify`?
- Các profiles quan trọng của CI/prod là gì?
- Có private repositories hoặc build plugins cần credentials không?
- Có parent/BOM controlling versions từ nhiều modules không?
- Có generated sources, shading, test fixtures, native dependencies, source compatibility đặc biệt không?
- Maven major nào đang được support và phiên bản mục tiêu có được tổ chức chấp thuận không?

**Đừng lưu credentials** trong bản baseline, debug dump hoặc patch review. Khi cần effective settings, ẩn/redact server details theo security policy.

## 5. Tách ba giai đoạn: đề xuất, áp dụng, xác minh

Một workflow an toàn:

~~~text
Baseline green on approved Maven/JDK
             |
             v
Discover candidates (display-*, release notes, advisories)
             |
             v
Choose ONE justified upgrade target
             |
             v
Apply ONE narrow transformation
             |
             v
git diff --check + review EVERY changed hunk
             |
       +-----+-----+
       |           |
Unexpected diff   Intended diff
       |           |
Revert just       Validate effective POM,
that change       resolved graph, tests, runtime
                   |
             +-----+-----+
             |           |
         Fails tests    Passes gates
             |           |
     Fix/rollback       Commit one reviewed change
             |
Repeat for next intentional upgrade
~~~

Điều quan trọng là **không gộp 50 upgrades rồi chỉ nhìn BUILD SUCCESS**. Khi có regression, sẽ khó tìm thủ phạm; khi tool sửa thêm parent, plugin management hoặc formatting, reviewer có thể bỏ sót thay đổi có tác động rộng.

Một report “all newer versions available” là danh sách **candidates**, không phải lệnh phải cài tất cả. Một PR nhỏ tăng tốc review, triage và rollback.

## 6. Ví dụ Java 17: ứng dụng minh họa có dependency thật

Cấu trúc:

~~~text
maven-upgrade-review/
├── pom.xml
└── src/
    ├── main/java/org/example/upgrade/
    │   ├── Greeting.java
    │   └── Main.java
    └── test/java/org/example/upgrade/
        └── GreetingTest.java
~~~

Mã sử dụng `org.apache.commons:commons-lang3` thật, để việc nâng dependency version có ý nghĩa. JUnit Jupiter là test-only. POM được viết cho **Maven 3.9.x và JDK 17**.

Dùng `commons-lang3.version=3.14.0` ở trạng thái baseline để minh họa nâng lên một version khác đã chọn; **không** gọi 3.14.0 “đang có CVE”, cũng không khẳng định một version mục tiêu là “fix” nếu không có vendor advisory.

## 7. pom.xml baseline hoàn chỉnh

Tệp `maven-upgrade-review/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.training</groupId>
    <artifactId>maven-upgrade-review</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <name>Maven Upgrade Review Demo</name>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <commons-lang3.version>3.14.0</commons-lang3.version>
        <junit-jupiter.version>5.11.4</junit-jupiter.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>${commons-lang3.version}</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit-jupiter.version}</version>
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
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.6.3</version>
                <executions>
                    <execution>
                        <id>toolchain-policy</id>
                        <phase>validate</phase>
                        <goals><goal>enforce</goal></goals>
                        <configuration>
                            <rules>
                                <requireMavenVersion>
                                    <version>[3.9,4.0)</version>
                                </requireMavenVersion>
                                <requireJavaVersion>
                                    <version>[17,)</version>
                                </requireJavaVersion>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Vì sao POM này là baseline hữu ích?**

- `commons-lang3.version` đặt tại property duy nhất, giúp công cụ thay một mốc phiên bản và review dễ.
- `junit-jupiter.version` độc lập; không nâng nhầm JUnit trong PR chỉ nâng Commons Lang.
- Các build plugins được pin; không tự chọn version dựa trên metadata tại mỗi build.
- Enforcer yêu cầu Maven **3.9.x** và JDK **17+**. Khi muốn chạy Maven 4 test, chính rule này **sẽ chặn**, nên việc chuyển toolchain phải review/update rule có chủ đích.
- POM không thêm `repositories` không đáng tin; dùng Maven Central/mirror đã được quản trị.
- Packaging JAR tạo artifact `target/maven-upgrade-review-1.0.0-SNAPSHOT.jar`, nhưng không có executable manifest/fat-JAR. Phần chạy Java dùng classpath rõ ràng.

**Lưu ý:** `requireJavaVersion` so Maven runtime JDK version, còn `maven.compiler.release` điều khiển target/source API. Tăng Java release trong POM không tự cài JDK mới cho CI.

## 8. Greeting.java và Main.java đầy đủ

Tệp `src/main/java/org/example/upgrade/Greeting.java`:

~~~java
package org.example.upgrade;

import java.util.Locale;
import org.apache.commons.lang3.StringUtils;

public final class Greeting {
    private Greeting() {
    }

    public static String greet(String rawName) {
        String value = StringUtils.isBlank(rawName) ? "guest" : rawName.strip();
        return "Hello, " + StringUtils.upperCase(value, Locale.ROOT) + "!";
    }
}
~~~

Tệp `src/main/java/org/example/upgrade/Main.java`:

~~~java
package org.example.upgrade;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? " Maven " : args[0];
        System.out.println(Greeting.greet(name));
    }
}
~~~

Cả hai class nằm trong package `org.example.upgrade`, path thư mục phải khớp package. `StringUtils.isBlank` và `StringUtils.upperCase(String, Locale)` là các API có trên cả baseline và version nâng ví dụ, nhưng **điều này không thay thế regression test** khi thư viện được dùng ở nhiều chỗ thực tế.

Khi không truyền args, output riêng của Java program sẽ là:

~~~text
Hello, MAVEN!
~~~

Đây là stdout **của `Main`**, không phải tất cả log Maven.

## 9. GreetingTest.java và lệnh kiểm baseline

Tệp `src/test/java/org/example/upgrade/GreetingTest.java`:

~~~java
package org.example.upgrade;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class GreetingTest {
    @Test
    void acceptsName() {
        assertEquals("Hello, MAVEN!", Greeting.greet(" Maven "));
    }

    @Test
    void defaultsWhenBlank() {
        assertEquals("Hello, GUEST!", Greeting.greet("   "));
        assertEquals("Hello, GUEST!", Greeting.greet(null));
    }
}
~~~

Tại thư mục có POM:

~~~bash
mvn -B -ntp clean verify
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Test có hai methods, ba assertions. Baseline test pass nếu Maven/JDK/repositories đáp ứng các điều kiện. Đừng tuyên bố “tests đã pass thực tế” khi chỉ soạn bài: chưa có chạy Maven tại máy của người đọc.

Để chạy chương trình khi đã build, tải runtime dependencies:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy-dependencies -DincludeScope=runtime
~~~

Linux/macOS:

~~~bash
java -cp "target/classes:target/dependency/*" org.example.upgrade.Main
~~~

Windows PowerShell/CMD:

~~~powershell
java -cp "target\classes;target\dependency\*" org.example.upgrade.Main
~~~

Stdout chính xác của đoạn Java mẫu khi không có đối số:

~~~text
Hello, MAVEN!
~~~

**Không dùng `java -jar`** với POM hiện tại: JAR chưa được cấu hình `Main-Class` và runtime classpath không tự nhét Commons Lang vào file JAR chính.

## 10. Đầu tiên dùng Versions Plugin để khảo sát, chưa sửa

MojoHaus Versions Maven Plugin hiện có trang docs mô tả các goals `display-dependency-updates`, `display-plugin-updates`, `display-property-updates` và `display-parent-updates`. Với phiên bản được pin trong bài là `2.25.1`:

~~~bash
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.25.1:display-dependency-updates
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.25.1:display-property-updates
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.25.1:display-plugin-updates
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.25.1:display-parent-updates
~~~

Các goal `display-*` **không tự sửa `pom.xml`**; chúng hỏi repository metadata và báo candidate updates. Output thay đổi theo thời điểm, mirror, available versions, version rules và selected profiles. Vì thế **không bịa danh sách “3.14.0 → X mới nhất”** trong tài liệu.

Với project demo, property `commons-lang3.version` điều khiển thư viện và có thể xuất hiện trong `display-property-updates`; `display-plugin-updates` giúp xem Maven Compiler/Surefire/JAR/Enforcer. Dự án demo không có parent khai báo nên `display-parent-updates` có thể không đưa ra update parent nào.

**Tách biệt:** phiên bản mới nhất được repository báo **không chứng minh** phù hợp với Maven/JDK đang dùng hay khắc phục CVE. Cần đối chiếu changelog, release notes, Maven Plugin minimum requirements, licensing và security advisory.

## 11. Chọn mục tiêu nâng cấp trước khi cho tool sửa file

Một ticket upgrade nên có:

~~~text
Scope:     org.apache.commons:commons-lang3
Before:    3.14.0
Candidate: 3.17.0
Reason:    Example: scheduled compatibility review
JDK:       17
Maven:     3.9.x
Affected:  Greeting.java, direct compile dependency
Checks:    compile, JUnit, dependency tree, runtime smoke, security scan
Rollback:  revert this isolated Git commit if regression occurs
~~~

**Đây là tình huống minh họa**, không có kết luận bảo mật rằng 3.14.0 bị lỗi hay 3.17.0 là phiên bản mới nhất/đã fix. Nếu một upgrade được kích hoạt do CVE, phải lấy **affected/fixed range từ advisory thật** chứ không đoán số phiên bản từ bảng candidates.

Cần trả lời bốn câu hỏi trước khi cập nhật:

1. **Điều gì buộc phải thay?** Security, Maven compatibility, EOL, performance, bugfix?
2. **Có thể nâng nhỏ hơn không?** Patch/minor thường có phạm vi nhỏ hơn major nhưng vẫn cần test.
3. **Ai khác bị ảnh hưởng?** Parent POM/BOM, multi-module, transitive consumers, plugins?
4. **Dấu hiệu thành công là gì?** Effective resolved graph đúng, tests, runtime smoke và release artifacts không đổi ngoài chủ đích.

## 12. versions:set-property cập nhật một property cụ thể

Với POM demo, dùng `versions:set-property` để thay **một** property:

~~~bash
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.25.1:set-property -Dproperty=commons-lang3.version -DnewVersion=3.17.0
~~~

Theo tài liệu MojoHaus, goal `set-property` **đặt giá trị property mà không có sanity check bảo đảm build thành công**. Nó không tự chứng minh Java code tương thích. Vì vậy ngay sau lệnh:

~~~bash
git status --short
git diff --check
git diff -- pom.xml
~~~

Nếu đúng phạm vi, thay đổi ngữ nghĩa mong đợi chỉ là:

~~~diff
-        <commons-lang3.version>3.14.0</commons-lang3.version>
+        <commons-lang3.version>3.17.0</commons-lang3.version>
~~~

Đoạn diff là **expected illustration**, không phải kết quả Git đã chạy. Nếu công cụ sửa thêm parent, BOM, versions của JUnit, plugin khác hoặc đổi cả encoding/formatting, phải giải thích từng thay đổi hoặc rollback những hunk ngoài mục tiêu.

**Lưu ý backup:** các goal Versions Plugin có thể tạo file `pom.xml.versionsBackup` theo tùy chọn `generateBackupPoms` mặc định. File này **không phải** POM mới cần commit như source; kiểm `git status --short`, giữ/loại đúng policy. Không sử dụng `git clean -fdx` bừa bãi chỉ để xóa một file backup.

## 13. Tại sao không chạy ngay use-latest-releases cho cả dự án?

`versions:use-latest-releases` hoặc `update-properties` có thể sửa **nhiều tọa độ** cùng lúc, bao gồm dependencies bạn chưa đánh giá. Một số candidates có thể thay đổi API hoặc minimum JDK, license, transitive dependencies. Các rules version ranges/SNAPSHOT handling cũng có thể khác nhóm tưởng.

Cách an toàn hơn:

- Lấy danh sách candidates qua `display-*`.
- Chọn một GAV hoặc một bộ phiên bản **phải nâng cùng nhau** theo platform/BOM.
- Dùng `set-property`/goal tương ứng cho phạm vi rõ, hoặc sửa thủ công một diff nhỏ.
- Review và test trước khi chạy lượt tiếp theo.
- Với parent/BOM lớn, dùng **một PR riêng**, kiểm tất cả effective child modules.

Không chạy goal **sửa POM** cùng một invocation Maven với lifecycle `clean verify` rồi mặc định lifecycle sẽ đọc lại cấu hình vừa sửa. Tài liệu Versions Plugin lưu ý các goal thay POM nên chạy **riêng**, sau đó dùng **một Maven invocation mới** để test build.

## 14. Kiểm từng thay đổi qua Git diff: thứ tự có ý nghĩa

Sau mỗi tool apply/update:

~~~bash
git status --short
git diff --stat
git diff --check
git diff -- pom.xml
~~~

Với project lớn:

~~~bash
git diff -- .mvn/wrapper/maven-wrapper.properties
git diff -- .github/workflows
git diff -- '**/pom.xml'
~~~

Những lệnh này **chỉ xem** thay đổi. Pattern quote có thể khác giữa shells/Git versions, nên trong review thực tế hãy chọn đường dẫn chính xác cho project nếu glob không hoạt động như mong đợi.

Đọc từng hunk và hỏi:

| Thay đổi | Câu hỏi kiểm tra |
| --- | --- |
| Dependency version | Có đúng artifact/version, scope/type/classifier không? |
| Parent/BOM version | Có làm thay effective graph của tất cả modules không? |
| Build plugin version | Maven/JDK minimum, goal params/default behavior có đổi không? |
| `modelVersion` | Có làm POM không còn build trên Maven 3 không? |
| `distributionManagement`/`repositories` | Tool có đổi deploy target/mirror/credentials boundary không? |
| `.mvn/wrapper/*` | Version, checksum, download URL, script provenance có tin cậy không? |
| CI workflow | Java/Maven, permissions, triggers, secrets và cache có đổi không? |
| Format-only changes | Có che khuất semantic changes không? Cần tách commit? |
| Removed config | Nó có thực sự redundant hay là business requirement? |
| Added generated files | Có chứa secrets, binaries hoặc files không nên commit không? |

**Không chấp nhận “tool tự sửa nên chắc đúng”.** Một thay đổi thuộc files không dự kiến (ví dụ `settings.xml` có credentials) là dấu hiệu phải dừng và điều tra.

## 15. Xác minh effective model và resolved dependency graph

Sau khi nâng property, Maven POM nhìn bằng mắt chưa đủ. Trên một project có parent/BOM, phiên bản được resolve có thể chịu ảnh hưởng `dependencyManagement`/dependency mediation. Dùng:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Chú ý các tình huống:

- Direct dependency dùng property vừa sửa nhưng một BOM/parent có thể quản lý dependency khác theo phiên bản riêng.
- Một thư viện **bắc cầu** có thể bị đổi theo BOM mà không có dòng diff trực tiếp trong child POM.
- Plugin dependencies/classpath riêng **không nhất thiết** hiện trong project `dependency:tree`.
- Source POM có thể build nhưng published POM cho consumer vẫn có cấu hình ngoài ý muốn; nên kiểm artifact phát hành sau cùng.
- Một classifier/type/native artifact có thể dùng platform-specific resolution; cần test các platform theo thực tế.

Với demo, sau khi sửa property sang 3.17.0, `dependency:tree` phải thể hiện direct `org.apache.commons:commons-lang3:jar:3.17.0:compile` nếu không có config khác ghi đè. Nếu tree vẫn 3.14.0, **đừng tự tuyên bố nâng thành công**: tìm project đang chạy, profile/parent/BOM, effective version và CLI options.

## 16. Build + unit tests + runtime smoke sau MỖI thay đổi

Từ root project:

~~~bash
mvn -B -ntp clean verify
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy-dependencies -DincludeScope=runtime
~~~

Rồi chạy ứng dụng Java 17 theo OS:

~~~bash
java -cp "target/classes:target/dependency/*" org.example.upgrade.Main
~~~

Windows:

~~~powershell
java -cp "target\classes;target\dependency\*" org.example.upgrade.Main
~~~

Stdout riêng của program:

~~~text
Hello, MAVEN!
~~~

Đó là **expected output do code Java**, không phải một log Maven thực tế đã được chạy. Nếu test fail sau upgrade, so sánh với baseline, lấy stack trace và dependency graph; ví dụ `NoSuchMethodError` có thể là binary incompatibility do transitive version mediation.

Với production, thêm integration/contract tests, container smoke, serialization/database compatibility, license checks, SCA, performance và deployment canary theo hệ thống; hai unit tests demo không đủ chứng minh mọi đường chạy tương thích.

## 17. Kiểm Security/License không thể được thay bằng “latest”

Versions Plugin hỏi repository versions, **không tự kết luận CVE đã được xử lý**. Khi nâng security dependency:

1. Xác minh CVE/advisory có ảnh hưởng GAV/version thật hay không.
2. Tìm fixed range từ vendor maintainer/GitHub Security Advisory/OSV/NVD hoặc nguồn được phê duyệt.
3. Đối chiếu dependency graph, scopes và đường code có thể bị khai thác.
4. Kiểm license, transitive dependencies, API/Java compatibility của candidate.
5. Chạy SCA/SBOM và tests ở release candidate.
6. Document risk acceptance nếu chưa thể patch; không gọi false positive một lỗ hổng thật.

Một thư viện có số version lớn hơn **không nhất thiết** mới hơn theo semantics tùy ecosystem, và không mặc định không có regression. Security gate cần **dữ liệu mới**, không lấy “scan pass tuần trước” làm bằng chứng CVE không tồn tại hôm nay.

Đối với Maven plugins, chúng chạy code trên CI/dev máy với quyền Maven process; khi upgrade phải kiểm plugin dependencies/permissions như supply-chain risk, không chỉ runtime app dependencies.

## 18. Maven Wrapper Plugin: nâng runtime Maven có kiểm soát

Maven Wrapper giúp thống nhất Maven version giữa developer và CI, thay cho phụ thuộc `mvn` bất kỳ trên `PATH`. Apache Maven Wrapper Plugin `3.3.4` có goal `wrapper`. Trong **một nhánh riêng**, nếu mục tiêu là pin Maven **3.9.11** (một bản ví dụ, không khẳng định mới nhất):

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper -Dmaven=3.9.11
~~~

Lệnh này **thực sự tạo/chỉnh** wrapper scripts/config như `mvnw`, `mvnw.cmd`, `.mvn/wrapper/maven-wrapper.properties`. Do đó phải inspect:

~~~bash
git status --short
git diff -- .mvn/wrapper/maven-wrapper.properties
git diff -- mvnw mvnw.cmd
~~~

Khi wrapper đã tạo và được review, sử dụng:

~~~bash
./mvnw -version
./mvnw -B -ntp clean verify
~~~

Windows:

~~~powershell
.\mvnw.cmd -version
.\mvnw.cmd -B -ntp clean verify
~~~

**Đừng cho rằng `mvnw` tồn tại trước khi chạy goal tạo wrapper.** Nó cũng có thể tải Maven distribution từ `distributionUrl`; doanh nghiệp cần xác minh URL/HTTPS/provenance, SHA-256 checksum khi áp dụng, network allowlist và version pin. **Không tạo checksum giả** bằng cách đoán hash.

Nâng Wrapper Plugin version **khác** với nâng Maven distribution version: một cái điều khiển bộ script/downloader, cái còn lại quyết định Maven CLI runtime được wrapper tải và thực thi.

## 19. Review chính xác file .mvn/wrapper/maven-wrapper.properties

Một cấu hình wrapper thông dụng có `distributionUrl` trỏ tới Maven binary distribution, ví dụ dạng:

~~~properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.11/apache-maven-3.9.11-bin.zip
~~~

Đây là **ví dụ URL cấu trúc**, không tuyên bố file của project hiện đang mang giá trị ấy. Wrapper có thể còn `wrapperUrl`, `distributionSha256Sum` hoặc các properties khác tùy loại wrapper/plugin version.

Review:

- Host có trong danh sách nguồn tin cậy, HTTPS và đường dẫn Maven release đúng?
- Version trong URL có khớp target và CI matrix không?
- Có `distributionSha256Sum` đã lấy từ nguồn chính thức/được quản lý không?
- Wrapper scripts có diff không mong đợi thêm remote commands?
- File mới được commit dưới Git với line endings/permissions đúng?
- Có bí mật bị nhúng vào URL `user:password@host` không? **Không chấp nhận**.
- Trên Windows/Linux đã kiểm chạy đúng Maven version?
- Khi công ty dùng internal mirror cho distribution, registry có quyền hạn/trust đúng?

Nếu tool thay cả wrapper scripts, **đọc diff của tất cả files đã tạo**, không chỉ mỗi file properties. Tùy policy, pin wrapper action hoặc kiểm nguồn script/binary trước khi cho nó chạy trong CI có secrets.

## 20. Nâng plugin versions: kiểm Maven/JDK compatibility

Không phải plugin version cao nhất dùng được cho Maven runtime hiện tại. Một plugin có thể tăng minimum Maven/JDK, đổi default behavior, deprecated parameters hoặc lifecycle phases.

Dùng:

~~~bash
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.25.1:display-plugin-updates
~~~

Sau đó, với mỗi plugin candidate, đọc:

1. Plugin documentation, **System Requirements** và release notes.
2. Maven CLI version `mvn -version` và JDK runtime trên tất cả CI jobs.
3. Plugin parameter names, goals và lifecycle bindings; có tham số bị removed/renamed?
4. Parent `pluginManagement`/child inheritance; effective plugin version thực ở từng module.
5. Plugin dependencies và security advisories.
6. Output artifacts/bytecode/test discovery/report paths trước và sau.
7. Maven 4 compatibility nếu đang có kế hoạch migration.

Ví dụ đặc biệt: **Maven Compiler Plugin version mới có thể yêu cầu Maven major mới**. Apache Maven 4 migration guide khuyên nâng plugins lên **bản phù hợp Maven 3** trước, không lập tức chọn plugin bản Maven 4-only khi project chưa nâng runtime.

Không đổi Compiler/Surefire/Deploy/Release/Shade trong một PR chung trừ khi lý do kỹ thuật buộc chúng liên quan; những plugin này có thể làm thay đổi artifact packaging hoặc release workflow.

## 21. Parent POM và BOM: một dòng thay đổi có tác động hàng chục module

Một project đa module có thể có:

~~~text
parent/
├── pom.xml                (parent, dependencyManagement, pluginManagement)
├── api/pom.xml
├── service/pom.xml
└── batch/pom.xml
~~~

Nếu dùng `versions:update-parent`, phiên bản parent có thể tăng và thay đổi **tất cả inheritance**: versions, plugins, profiles, repositories, Enforcer rules, property defaults và release metadata.

Nếu dùng BOM import:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example.platform</groupId>
            <artifactId>platform-bom</artifactId>
            <version>2.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là **mảnh minh họa với artifact giả**, không thuộc POM runnable. Chỉ đổi BOM `2.0.0` → `2.1.0` (giả định) có thể nâng nhiều thư viện transitively mà child POM không có diff.

Kiểm cả reactor:

~~~bash
mvn -B -ntp -pl :api -am verify
mvn -B -ntp -pl :service -am verify
mvn -B -ntp -pl :batch -am verify
mvn -B -ntp verify
~~~

Các lệnh `-pl` giả định project thật có modules với artifactIds tương ứng; chúng **không chạy trên demo đơn module** ở mục 7. Với multi-module nên có automated test matrix, dependency tree per module và hiệu lực profiles CI/prod.

Không đánh đồng một change parent/BOM “chỉ một dòng XML” với một change tác động nhỏ; **độ rộng ảnh hưởng là hiệu lực ở consumer modules**.

## 22. Dùng Maven Enforcer để chặn nâng runtime vô tình

POM demo đang có:

~~~xml
<requireMavenVersion>
    <version>[3.9,4.0)</version>
</requireMavenVersion>
<requireJavaVersion>
    <version>[17,)</version>
</requireJavaVersion>
~~~

Khi build với Maven 4, rule đầu sẽ fail. Đó là **policy chủ đích**, không phải Maven 4 nhất định bị lỗi. Trước khi điều chỉnh rule, kiểm các Maven 4 compatibility issues thực tế.

Các bước nâng:

1. Chạy baseline Maven 3 green.
2. Kiểm plugin versions phù hợp Maven 3.
3. Xây một test lane Maven 4 trên **trusted branch**, tạm dùng rule phù hợp hoặc test profile riêng theo policy.
4. Chỉ sau khi test green mới cập nhật Enforcer version range để phản ánh Maven versions được hỗ trợ.
5. Nếu bỏ hỗ trợ Maven 3, ghi rõ trong README/CI/release notes; không mở range `[3.9,)` không có kiểm chứng.

Cấu hình Enforcer có thể theo Maven plugin `3.6.3` như demo, nhưng plugin version cũng có thể cần đổi khi có guideline mới. Đừng disable Enforcer toàn bộ để “build xanh”; nó có thể còn chứa những rules khác về dependencies/Java/duplicate classes.

## 23. Chuyển từ Maven 3 sang Maven 4 theo ba pha

Theo Apache Maven hướng dẫn “Starting with Maven 4”:

**Pha 1 — Prepare:** chạy bản Maven 3.9 được hỗ trợ, JDK 17 đủ điều kiện, nâng plugins lên versions tương thích Maven 3, sửa warnings/duplicates/điểm cấu hình đã lỗi.

**Pha 2 — Test in parallel:** dùng Maven 4 trong một CI lane riêng trên cùng project, với **những sửa đổi POM tối thiểu vẫn tương thích Maven 3** nếu mục tiêu là giữ hai runtime. So sánh effective configuration, tests và artifacts.

**Pha 3 — Migrate optional features:** khi sẵn sàng bỏ Maven 3, cân nhắc modelVersion `4.1.0`, cấu trúc subprojects/new lifecycle và Maven 4-only features. Đây là thay đổi **khả năng đọc/build POM**: Maven 3 không hiểu đầy đủ mô hình mới.

Maven 4 cần JDK 17 để chạy. **Đừng nâng `<modelVersion>4.1.0</modelVersion>` khi nhóm còn có nghĩa vụ hỗ trợ Maven 3** chỉ vì tool tự đề xuất. Khi dùng Maven 4, kiểm các thay đổi default behavior như `installAtEnd`/`deployAtEnd`, lifecycle names, plugin compatibility và metadata publishing.

Không nên gộp migration Maven 3→4 với nâng toàn bộ application dependencies cùng lúc. Hai lớp lỗi là khác nhau và có test matrix riêng.

## 24. Maven Upgrade Tool (mvnup): check trước, apply sau

Apache Maven 4 (từ `4.0.0-rc-4`) tích hợp công cụ `mvnup`. **Nó không phải một goal có sẵn trong Maven 3.9.x** và không thay thế hoàn toàn quá trình review người dùng.

Trong một project checkout **đang sạch** với Maven 4 distribution đã cài, xem khả năng chuyển đổi mà chưa sửa POM:

~~~bash
mvnup check --model-version 4.0.0 --all
~~~

`--model-version 4.0.0` giữ POM model version ở dạng Maven 3 còn có thể đọc (vẫn phải kiểm các changes khác). Nếu nhóm đã chấp nhận bỏ Maven 3, có thể kiểm:

~~~bash
mvnup check --model-version 4.1.0 --all
~~~

Khi chọn nâng và đã review plan, tool có lệnh **sửa thực tế**:

~~~bash
mvnup apply --model-version 4.1.0 --all
~~~

**Không chạy dòng `apply` trên project đang có thay đổi chưa commit**. Sau apply:

~~~bash
git status --short
git diff --check
git diff -- '**/pom.xml'
~~~

Theo tài liệu Maven, tool hỗ trợ `--plugins`, `--model`, `--infer`, `--directory`. Nếu mục đích chỉ xem/cập nhật plugin compatibility, chọn **scope hẹp**:

~~~bash
mvnup check --plugins
~~~

Chỉ sau review mới cân nhắc `mvnup apply --plugins`. Các thay đổi tạo ra có thể gồm plugin versions, loại bỏ cấu hình trùng, sửa parent relativePath, deprecated phases và Maven4-specific model features.

**Quan trọng:** `mvnup check` nói *công cụ có thể sửa gì*, không chứng minh build/test/runtime/CI sẽ pass; `apply` cũng không tự đảm bảo Maven 3 vẫn hỗ trợ khi model target là 4.1.0. Mỗi hunk cần owner và reason.

## 25. OpenRewrite: dùng dryRun để xem recipe trước khi sửa

OpenRewrite có Maven plugin hỗ trợ các goals:

~~~text
rewrite:dryRun    -> phân tích và tạo patch/warnings, không áp source edits
rewrite:run       -> áp recipes và sửa source files/POM
rewrite:runNoFork -> biến thể không fork lifecycle
~~~

Một recipe chính thức cho Maven là:

~~~text
org.openrewrite.maven.MigrateToMaven4
~~~

Recipe gồm nhiều phép biến đổi như đổi expressions/lifecycle phases, dọn duplicate dependencies/plugins, HTTPS repositories và nâng plugins không tương thích Maven 4. **Nó có thể sửa nhiều file/hunks**, nên không nên chạy trước khi review recipe và source commit.

Workflow an toàn:

1. Pin **rewrite-maven-plugin version** và recipe artifact/version theo tài liệu/approved build tool policy.
2. Cấu hình recipe đã chọn trong build **trên một nhánh riêng**.
3. Chạy `mvn rewrite:dryRun`, xem patch trong `target/rewrite` và log warnings.
4. Review recipe nào tác động file nào, có đổi model/lifecycle hoặc repository URL không.
5. Chỉ sau đó chạy `mvn rewrite:run` để áp sửa đổi, rồi `git diff --check` và inspect từng hunk.
6. Chạy Maven/JDK/CI compatibility matrix sau apply, đối chiếu artifacts và dependency graph.
7. Nếu patch có thay đổi không hiểu, **không merge**; tinh chỉnh recipe hoặc chia thành recipes nhỏ.

**Các lệnh ngắn ở trên chỉ hoạt động khi OpenRewrite plugin và recipes đã được cài/cấu hình**. Chúng không phải một lệnh “chạy ngay trên mọi POM” mà không cần dependencies. Không dùng wildcard `LATEST` cho plugin recipe trên release pipeline chưa review.

Dry run còn có thể ghi patch files dưới `target/rewrite`, nhưng **không đồng nghĩa không có file tạm/report nào**. Phân biệt “không đổi source” với “không tạo output phụ”.

## 26. So sánh mvnup và OpenRewrite cho Maven 4

| Tiêu chí | `mvnup` | OpenRewrite |
| --- | --- | --- |
| Nơi có công cụ | Đi kèm Maven 4 từ rc-4. | Maven plugin + recipe dependencies. |
| Đầu vào | Maven POMs/subprojects. | Java/XML/POM, các file được recipe hỗ trợ. |
| Khảo sát | `mvnup check`. | `rewrite:dryRun`. |
| Áp dụng | `mvnup apply`. | `rewrite:run`/`runNoFork`. |
| Phạm vi chọn | `--model`, `--plugins`, `--infer`. | Một hoặc nhiều named recipes. |
| Rủi ro | Đổi POM model/plugins/inference. | Batch refactor code/POM có thể rộng. |
| Giới hạn | Không thay tests/business logic review. | Recipe không hiểu mọi custom build flow. |
| Thao tác sau | Git diff, full builds, CI matrix. | Git diff, full builds, CI matrix. |

Không nhất thiết chạy **cả hai** trên cùng checkout rồi merge toàn bộ output. Mỗi công cụ có thể chạm cùng POM và tạo những diff khác nhau; nên chạy **trong branches riêng** để so sánh, chọn strategy, hoặc chạy tuần tự chỉ khi biết rõ phép biến đổi bổ sung.

Với Maven 3.9.x và mục tiêu nâng một thư viện, `mvnup` là **không phù hợp**: dùng Versions Plugin và tests. Với Maven 4 migration, `mvnup` là lựa chọn từ chính Apache Maven; OpenRewrite hữu ích khi muốn recipes rộng hơn hoặc xử lý nhiều project cùng chuẩn.

## 27. Kiểm thay đổi modelVersion và Maven 4-only features

Hai POM model versions:

~~~xml
<modelVersion>4.0.0</modelVersion>
~~~

và:

~~~xml
<modelVersion>4.1.0</modelVersion>
~~~

**Không chỉ là tăng số**. Apache Maven 4 hướng dẫn model version `4.1.0` cho các POM features mới như root/subprojects/BOM packaging/inference. Maven 3 không hỗ trợ model mới như Maven 4.

Review các hunk sau upgrade tool:

- `<modelVersion>`, XML namespace/schema location.
- `<modules>`/`<subprojects>` và root project markers.
- Parent `groupId`/`version` inference; dependency version removal.
- Duplicate plugin/dependency declarations được dọn: có làm thay effective model không?
- Removed/deprecated phase names và executions binding.
- Plugin versions/parameters và Maven 4 minimum versions.
- Lifecycle default `installAtEnd`/`deployAtEnd`, ảnh hưởng artifact promotion.
- Repository URLs/HTTPS, relativePath và profile activation.
- CI Wrapper runtime/JDK Enforcer ranges và published consumer POM.

Với mỗi hunk, ghi lý do “Maven 4 required compatibility fix” hoặc “optional cleanup”, rồi kiểm diff bằng tests. **Một phép loại bỏ POM version** có thể làm module nội bộ vẫn build nhưng consumer bên ngoài resolve sai nếu không có consumer POM phù hợp; cần kiểm artifact sau publish.

## 28. CI matrix: thử runtime cũ và mới khi còn support cả hai

Một migration Maven runtime nên có ít nhất hai lanes:

~~~text
Lane A: approved Maven 3.9.x + JDK17 -> clean verify, report/test artifacts
Lane B: chosen Maven 4.x + JDK17    -> clean verify, report/test artifacts
                                    |
                                    v
                         compare tests, dependency trees,
                         build plugin behavior, resulting JAR/POM
~~~

**Lưu ý demo:** POM Enforcer hiện có rule `[3.9,4.0)` nên Maven 4 lane **sẽ fail** nếu không cập nhật range. Đây là **policy phải được review** trong migration branch, không là lý do tự disable validation.

CI có thể dùng separate Maven installations hoặc Wrapper distributions trong các jobs, nhưng kiểm `mvn -version`/`./mvnw -version` thật; một job matrix chỉ đổi tên biến `MAVEN_VERSION` chưa đảm bảo runtime thay.

Các test bổ sung: Java compiler output, Surefire test discovery, Failsafe/integration, Shade/Assembly packaging, source/Javadoc/manifest, installed POM, deployment repository metadata, signing/certificates, runtime container smoke. Với multi-module, kiểm reactor order, parent/BOM inheritance và artifacts từ từng module.

Không publish release thẳng từ lane thử nghiệm; chỉ sau khi compatibility và approvals hoàn tất mới chuyển pipeline production.

## 29. Xem từng hunk của công cụ, kể cả thay đổi không mong đợi

Ví dụ phiên bản plugin được tool tự cập nhật:

~~~diff
 <plugin>
     <artifactId>maven-surefire-plugin</artifactId>
-    <version>3.5.2</version>
+    <version>3.5.3</version>
 </plugin>
~~~

Đây là **diff mô phỏng**, không khẳng định 3.5.3 là version phù hợp hoặc đã xuất hiện trong project. Reviewer cần kiểm:

- Release này có tồn tại ở trusted repository, đủ Maven/JDK requirement?
- JUnit engine/test discovery có thay behavior?
- Có parameters deprecated hoặc default mới?
- Unit/integration tests có bị “0 tests run” trong khi exit 0?
- Test reports trong `target/surefire-reports` có hợp lệ?
- License/security advisories của plugin dependencies có đổi?

Một diff `<version>` nhỏ nhưng **tác động runtime** có thể lớn. Sau khi cập nhật, so số tests trước/sau, không chỉ nhìn BUILD SUCCESS.

**Đối với config tool tự xóa:** ghi bằng chứng nó thật sự redundant theo effective POM/official migration docs. Nếu không hiểu lý do, rollback hunk hoặc tách ticket. Công cụ không thể biết mọi custom CI release contract của tổ chức.

## 30. Cách ghi nhận change ledger để review có thể kiểm toán

Tạo một change ledger trong PR description (không cần file bắt buộc):

| # | File/hunk | Công cụ | Vì sao cần | Validation | Quyết định |
| --- | --- | --- | --- | --- | --- |
| 1 | `pom.xml` commons property 3.14→3.17 | Versions set-property | Scheduled upgrade demo | tree, JUnit, smoke | Giữ nếu pass. |
| 2 | `pom.xml` Enforcer Maven range | Manual/review | Cho Maven 4 lane | Maven3/4 matrix | Giữ sau approve. |
| 3 | `.mvn/wrapper/*` | Wrapper Plugin | Pin distribution | SHA, Unix/Windows wrapper | Giữ nếu trusted. |
| 4 | POM duplicate plugin removal | `mvnup` hoặc Rewrite | Maven4 compatibility | effective POM diff, full test | Chỉ giữ khi tương đương. |

**Mẫu ledger** không phải lịch sử thay đổi đã thực hiện. Mỗi thay đổi cần liên kết tới hunk cụ thể và test evidence, thay vì một mô tả “upgraded dependencies” quá chung.

Khi tool tạo hàng trăm hunk, cần chia theo loại: API compatibility, repository/security, plugin migration, formatting. Nếu không thể giải thích hết thay đổi, PR **chưa đạt điều kiện review**, dù build green.

## 31. Rollback đúng và không phá công việc người khác

Khi thay đổi vừa áp dụng gây lỗi, cách an toàn nhất là **revert commit riêng cho upgrade** hoặc restore **chỉ files/hunks của upgrade** sau khi xác nhận không có thay đổi khác.

Lệnh xem commit/working tree:

~~~bash
git status --short
git diff -- pom.xml
git log --oneline -5
~~~

Nếu một file trong dedicated demo branch **không có thay đổi người khác cần giữ**, có thể rollback chỉ file đó:

~~~bash
git restore -- pom.xml
~~~

**Cảnh báo:** `git restore` bỏ **mọi thay đổi chưa commit của file chỉ định**, bao gồm công việc không liên quan. Chỉ dùng khi có chủ đích và đã giữ lại bản cần thiết. Với commit đã merge, quy trình review là `git revert <commit-sha>` hoặc PR rollback thay vì rewrite shared history.

MojoHaus Versions Plugin có ``versions:revert` và `versions:commit` để quản lý files backup của chính plugin, nhưng **`versions:commit` không tạo Git commit**. Nếu đã chuyển sang Git-managed commit workflow, không dùng `versions:revert` mù quáng sau nhiều edits khác hoặc khi backup thuộc lần trước.

Không chạy `git reset --hard`, `git clean -fdx` hoặc xóa `target`/backup toàn repo trên workspace đang chia sẻ chỉ để “hoàn nguyên tool upgrade”.

## 32. Các lỗi thường gặp khi dùng công cụ nâng cấp

| Triệu chứng | Nguyên nhân cần xét | Hướng giải quyết |
| --- | --- | --- |
| `display-*` không thấy bản mới | Repo metadata, mirror, filter, profile, version rules | Kiểm release thực và tool config. |
| `set-property` sửa version nhưng build fail | API/binary incompatibility hoặc JDK minimum | Đọc changelog, test, rollback target. |
| `-DnewVersion` không tác động đúng property | Sai tên property hoặc POM ở module khác | Kiểm effective POM và `git diff`. |
| Tool đổi nhiều POM ngoài dự kiến | Parent/aggregator/reactor behavior | Xem từng hunk, chọn scope nhỏ hơn. |
| Có `pom.xml.versionsBackup` | Versions Plugin backup mặc định | Review, không commit backup như source. |
| `mvnup` command not found | Đang dùng Maven 3 hoặc distribution thiếu tool | Dùng Maven 4 phù hợp, không gọi như Maven 3 goal. |
| Maven 4 không chạy POM 4.1 bằng Maven 3 | Model 4.1 là Maven4-only | Giữ 4.0.0 trong giai đoạn dual-support. |
| Maven 4 lane fail Enforcer | Rule Maven3-only vẫn hoạt động | Review và điều chỉnh version policy. |
| Plugin goal biến mất | Version/plugin API/lifecycle thay đổi | Kiểm plugin release notes và effective bindings. |
| CI tests pass nhưng ít tests hơn | Surefire/Failsafe discovery/config thay đổi | So số tests và reports, không chỉ exit code. |
| Wrapper có URL lạ | Tool/scripts bị chỉnh ngoài policy | Dừng, kiểm SCM source và checksum. |
| CI dùng Maven cũ dù Wrapper đã đổi | Job gọi `mvn` thay `./mvnw` hoặc cache sai | Kiểm command và Maven version log. |
| OpenRewrite dryRun chỉ báo patch | Goal không sửa source | Review patch, chỉ run khi đã duyệt. |
| Recipe sửa repositories HTTP→HTTPS | Security/migration fix có thể đổi endpoint | Kiểm internal TLS/proxy/mirror policy. |
| Parent/BOM đổi một dòng kéo nhiều artifacts | Managed versions thay đổi | So dependency trees toàn reactor. |
| “Latest plugin” yêu cầu Maven 4 | Minimum Maven tăng | Chọn bản Maven3-compatible trước. |
| Native/image smoke test fail | JDK/native lib/container mismatch | Test actual target image/runtime. |
| Security scan pass nhưng CVE xuất hiện sau | Feed thay đổi theo thời gian | Scan định kỳ/release SBOM. |
| Generated Java source không được compiler thấy | Plugins/phase/source roots thay đổi | Kiểm generate-sources và compile inputs. |
| Changed output JAR nhưng tests pass | Packaging/plugins/manifest đã đổi | So artifact content/checksums/provenance. |
| Quá nhiều unrelated formatting diffs | Formatter/recipe reflow | Tách formatting commit để review semantics. |

## 33. Một PR nâng cấp tốt cần bằng chứng gì?

Một pull request nên có:

~~~text
Purpose: [specific dependency/plugin/Maven runtime change]
Baseline: Maven X + JDK Y, tests N passing
Scope: list of Maven modules and files changed
Tool/command: exact version-pinned command, check vs apply
Generated changes: git diff/stat, reviewed hunk explanations
Resolved graph: before vs after, direct/transitive changes
Compatibility: Maven/JDK matrix, plugin minimum requirements
Quality gates: compile, JUnit, integration, runtime smoke, SCA/license
Artifacts: POM/JAR/manifest/release metadata comparison as relevant
Security: repo URLs/credentials unchanged or approved
Rollback: revert isolated commit/restore approved artifact
Approval: owners for affected platform/modules
~~~

Đây là **template PR description**, không phải tự tạo log bằng chứng khi chưa chạy commands. Link tới CI run và artifacts **thực tế** sau khi người vận hành chạy, không gán “PASS” theo trí nhớ.

Chỉ khi có thể giải thích **từng file/hunk**, đã chạy tests phù hợp và có rollback path, mới coi upgrade đủ an toàn để merge.

## 34. Checklist vận hành từng bước

- [ ] Đã định nghĩa chính xác mục tiêu: Maven runtime, JDK, wrapper, BOM, dependency, plugin hay CI.
- [ ] Đã đọc official migration guide/changelog cho target version.
- [ ] Có clean baseline trong branch riêng, source commit đã ghi.
- [ ] Maven/JDK versions và baseline tests được ghi nhận thực tế.
- [ ] `versions:display-*` được dùng trước các goals sửa POM nếu thích hợp.
- [ ] Chọn một target version có rationale, không “latest mọi thứ” mù quáng.
- [ ] Lệnh write được pin tool version và chạy tách khỏi lifecycle verify.
- [ ] Sau mỗi write có `git status --short` và `git diff --check`.
- [ ] Đã đọc mọi changed hunk, kể cả POM/CI/wrapper ngoài scope mong đợi.
- [ ] Không có URLs/secrets/permissions thay đổi không được phê duyệt.
- [ ] Đã kiểm `help:effective-pom`, resolved dependency tree, profiles cần thiết.
- [ ] Đã kiểm transitive changes từ parent/BOM ở tất cả modules bị ảnh hưởng.
- [ ] Đã chạy compile/unit/integration/contract/runtime tests theo risk.
- [ ] Đã so test counts, test reports và artifact outputs trước/sau.
- [ ] Maven 3→4 có lane compatibility riêng, JDK17, Enforcer rule review.
- [ ] `mvnup check` hoặc `rewrite:dryRun` có patch được review trước `apply/run`.
- [ ] POM model 4.1.0 chỉ áp dụng khi chấp nhận Maven4-only.
- [ ] Wrapper distribution URL và checksum từ trusted source được kiểm.
- [ ] Không commit `pom.xml.versionsBackup`/temp patch hoặc generated cache ngoài policy.
- [ ] CVE/license/security alerts được kiểm theo data hiện tại.
- [ ] Có owner/approval/commit tách biệt/rollback plan.
- [ ] CI không lấy untrusted build inputs trong privileged release job.
- [ ] README/CI/release notes mô tả Maven/JDK minimum sau migration.

## 35. Câu hỏi tự kiểm tra

1. **Versions Plugin `display-dependency-updates` có sửa POM không?** Không; nó báo candidates.
2. **`set-property` có tự xác nhận version mới tương thích không?** Không; nó đặt property, cần test.
3. **`versions:commit` có tạo Git commit không?** Không; nó quản lý backup files của Versions Plugin.
4. **Tại sao phải nhìn `git status --short` sau update?** Để phát hiện cả backup/new/edited files.
5. **BOM nâng một dòng có thể kéo nhiều dependencies không?** Có; phải so effective graph.
6. **Nâng Compiler Plugin có tự nâng Maven distribution không?** Không.
7. **Thay `maven.compiler.release` có tự cài JDK mới không?** Không.
8. **`mvnup` có sẵn trên Maven 3.9.x không?** Không; nó nằm trong Maven 4 từ 4.0.0-rc-4.
9. **`mvnup check` và `apply` khác gì?** Check khảo sát; apply thay POM.
10. **`modelVersion 4.1.0` có còn build bằng Maven 3 không?** Không theo hướng dẫn Maven 4.
11. **OpenRewrite `dryRun` có sửa source không?** Không, nó tạo report/patch; `run` áp dụng.
12. **Nên chạy OpenRewrite và mvnup cùng lúc trên checkout bẩn không?** Không; tách branches/changes.
13. **Maven Wrapper Plugin có thể tạo nhiều files không?** Có; phải đọc diff cả scripts/config.
14. **Một plugin version mới nhất có luôn chạy Maven 3 không?** Không; kiểm minimum requirements.
15. **Build success có bảo đảm Surefire đã chạy đúng test suite không?** Không; so test counts/reports.
16. **Có thể rollback bằng `git restore -- pom.xml` mọi lúc không?** Không; nó bỏ mọi uncommitted edits trong file.
17. **Vì sao phải so artifact JAR/POM sau nâng build plugin?** Output packaging/metadata có thể đổi dù tests pass.
18. **Được thay toàn bộ security review bằng “latest dependency” không?** Không.
19. **CI Maven 4 lane fail Enforcer Maven3-only có phải Maven 4 bug?** Không nhất thiết; đó là rule policy.
20. **Khi nào chấp nhận thay đổi từ automation?** Khi biết lý do từng hunk, tests và compatibility pass, có rollback.

## 36. Tài liệu chính thức và nguồn hướng dẫn

- [Apache Maven — Starting with Maven 4](https://maven.apache.org/guides/mini/guide-migration-to-mvn4): trình tự prepare → test → migrate, JDK17, plugin compatibility và model 4.1.0.
- [Apache Maven — Maven Upgrade Tool (mvnup)](https://maven.apache.org/tools/mvnup.html): `check`/`apply`, `--model-version`, `--model`/`--plugins`/`--infer`.
- [Apache Maven — What's new in Maven 4](https://maven.apache.org/whatsnewinmaven4.html): Maven 4 features và compatibility changes.
- [Apache Maven — Maven Wrapper](https://maven.apache.org/tools/wrapper/): `mvnw`, `mvnw.cmd` và distribution pin.
- [Apache Maven Wrapper Plugin — wrapper:wrapper](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/wrapper-mojo.html): parameters, generated files và checksum support.
- [MojoHaus — Versions Maven Plugin](https://www.mojohaus.org/versions/versions-maven-plugin/): goals và version management.
- [MojoHaus — Versions Maven Plugin usage](https://www.mojohaus.org/versions/versions-maven-plugin/usage.html): read-only vs write goals, backup/commit/revert.
- [MojoHaus — versions:set-property](https://www.mojohaus.org/versions/versions-maven-plugin/set-property-mojo.html): `property`, `newVersion` và không tự sanity check.
- [MojoHaus — display-plugin-updates](https://www.mojohaus.org/versions/versions-maven-plugin/display-plugin-updates-mojo.html): available plugin versions và Maven version requirements.
- [OpenRewrite — Maven Plugin Configuration](https://docs.openrewrite.org/reference/rewrite-maven-plugin): `dryRun`/`run` và plugin setup.
- [OpenRewrite — Migrate to Maven 4 recipe](https://docs.openrewrite.org/recipes/maven/migratetomaven4): named recipe và biến đổi POM.
- [Apache Maven — Enforcer requireMavenVersion](https://maven.apache.org/enforcer/enforcer-rules/requireMavenVersion.html): range version gating.
- [Apache Maven — Enforcer requireJavaVersion](https://maven.apache.org/enforcer/enforcer-rules/requireJavaVersion.html): kiểm JDK chạy Maven.
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): transitive dependencies, BOM và management.
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): resolved graph.
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): effective configuration.
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phases và plugin executions.
- [Apache Maven — Maven POM Reference](https://maven.apache.org/pom.html): model/repositories/plugins/properties.
- [Git — git diff documentation](https://git-scm.com/docs/git-diff): diff options và patch review.
- [Git — git restore documentation](https://git-scm.com/docs/git-restore): khi nào restore gây mất uncommitted changes.

**Kết luận:** Công cụ hỗ trợ nâng cấp làm giảm thao tác thủ công, nhưng **không chịu trách nhiệm thay người review**. Bắt đầu từ baseline green, dùng Versions Plugin để đọc candidates, nâng một mục tiêu có lý do, review mọi Git hunk, kiểm effective POM/resolved graph/tests/artifact, rồi mới commit. Khi chuyển Maven 3→4, chuẩn bị JDK 17 và plugin compatibility, test song song rồi dùng `mvnup check/apply` hoặc OpenRewrite recipe có kiểm soát; chỉ áp model 4.1.0 khi chấp nhận Maven4-only. **Không merge bất kỳ thay đổi được tạo tự động nào mà không thể giải thích và xác minh.**
