# Chuẩn bị phiên bản, kiểm thử và kiểm tra kho mã trước phát hành bằng Maven

## 1. Release readiness khác với thao tác xuất bản

Một dự án Java chạy được trên máy developer chưa chắc đã sẵn sàng phát hành. Cùng một source tree có thể tạo artifact khác nhau vì parent/BOM/plugin versions, JDK, profile, dependency SNAPSHOT hoặc tài nguyên được filter. Ngay cả khi `mvn test` xanh, commit được dùng có thể chưa được phê duyệt, tên Git tag đã tồn tại, integration tests bị skip, hoặc JAR phát hành thiếu manifest/resource cần chạy.

**Chuẩn bị phát hành** (*release readiness*) là một bộ điều kiện phải được xác nhận **trước khi** tạo release commit/tag hoặc đưa artifact lên kho chính thức. Nó xoay quanh ba câu hỏi:

1. **Phiên bản có đúng không?** Project GAV, release version, next development version, parent/child versions và dependencies có phù hợp chính sách?
2. **Chất lượng đã được kiểm chứng không?** Unit tests, integration tests, package smoke tests, dependency/security/license checks đã chạy thật trên đúng source/JDK?
3. **Source có thể truy vết không?** Git branch, SHA, remote, working tree và tag tương ứng với commit được duyệt?

Các bước cần phân biệt:

| Bước | Ví dụ | Thay đổi trạng thái |
| --- | --- | --- |
| Quan sát | `git status`, `help:effective-pom` | Chủ yếu đọc; Maven có thể tạo file báo cáo/tải plugin. |
| Kiểm thử | `mvn clean verify` | Tạo outputs trong `target`, không tự upload artifact. |
| Dry-run release | `release:prepare -DdryRun=true` | Mô phỏng đổi POM/tag, có thể tạo file tạm và chạy verify goals; không commit/tag SCM theo plugin. |
| Prepare thực | `release:prepare` | Có thể sửa POM, commit, tag và **push Git remote**. |
| Perform/publish | `release:perform` | Checkout source tag, build và có thể **deploy** ra remote repository. |

**Quy tắc:** không dùng `release:prepare` thật hay `release:perform` chỉ để “xem thử”. Chúng là những thao tác có side effects, cần quyền phát hành riêng. Bài này chủ yếu thực hiện kiểm tra và mô tả dry-run an toàn trên môi trường được phép.

## 2. Hợp đồng của một release

Trước khi phát hành, lập bản ghi release candidate chứa:

~~~text
Project:            vn.example.release:release-readiness-demo
Current version:    1.0.0-SNAPSHOT
Approved release:   1.0.0
Next development:   1.0.1-SNAPSHOT
Planned Git tag:    v1.0.0
Source repository:  Git repository do tổ chức quản lý
Source commit:      SHA đầy đủ đã được review
Build baseline:     Maven 3.9+ / JDK 17+
Verify command:     mvn -B -ntp clean verify
Publish decision:   Chỉ sau phê duyệt và các gates đều PASS
~~~

Các giá trị trên là **mẫu minh họa**, không phải metadata của một release có thật. Version `1.0.1-SNAPSHOT` là lựa chọn trong ví dụ; một team có thể dùng `1.1.0-SNAPSHOT` hoặc convention khác.

Hợp đồng cần nêu rõ ai được phép review, commit, tạo tag, push, deploy, kiểm tra sau phát hành và xử lý rollback. Không nên tự chốt release version từ “phiên bản mới nhất” của dependency hoặc thay đổi version policy chỉ vì một công cụ gợi ý như vậy.

### Những đầu vào khác phải được ghi nhận

- Branch và commit SHA được chấp thuận.
- Parent/BOM dependency versions và plugin versions được sử dụng.
- JDK/Maven thực tế của CI; Maven Wrapper nếu có.
- Mục tiêu Java runtime tối thiểu.
- Các profiles/feature flags cần bật trong bản release.
- Định dạng đầu ra (`jar`, `war`, shaded JAR, distribution ZIP, image).
- Đích publish theo `<distributionManagement>` và policy release immutable.
- Những tests/gates bắt buộc, các ngoại lệ có phê duyệt.
- Changelog, migration notes và compatibility requirements.

## 3. SNAPSHOT của project khác SNAPSHOT dependency

Bản project đang phát triển thường có:

~~~xml
<groupId>vn.example.release</groupId>
<artifactId>release-readiness-demo</artifactId>
<version>1.0.0-SNAPSHOT</version>
~~~

**Đây là trạng thái bình thường trước release**. Maven Release Plugin sẽ chuyển POM sang release version ở bước chuẩn bị. Nhưng một dependency ngoài project như:

~~~xml
<dependency>
    <groupId>vn.example.library</groupId>
    <artifactId>external-api</artifactId>
    <version>2.4.0-SNAPSHOT</version>
</dependency>
~~~

có thể khiến bản phát hành không tái lập được. Đó là **đoạn minh họa**, không phải dependency của ví dụ runnable trong mục 10.

Để quản lý rủi ro, cần xem:

1. Project dependencies trực tiếp và bắc cầu.
2. Parent POM, imported BOM, `dependencyManagement`.
3. Build plugins, plugin dependencies, reporting plugins, extensions.
4. Những dependencies chỉ có khi bật profile release.
5. SNAPSHOT trong reactor: có thuộc những modules được release cùng nhau không?
6. Version ranges/dynamic selection khiến lần resolve sau chọn file/version khác.

**Không kiểm tra bằng cách cấm mọi chuỗi `SNAPSHOT` trong POM trước prepare**: khi đó chính `project/version` đang phát triển sẽ bị chặn. Thay vào đó kiểm tra loại tham chiếu, cách nó được sử dụng, và cơ chế Maven Release Plugin giải quyết các module nội bộ.

### “Đã pin” không đồng nghĩa “tương thích”

Một dependency release cố định vẫn có thể yêu cầu JDK cao hơn, thay API hoặc chứa lỗ hổng. Cần đọc release notes và kiểm thử đúng đường sử dụng. `dependencyManagement` kiểm soát version khi dependency được dùng, nhưng **không tự khai báo một dependency thực sự**.

## 4. Maven Release Plugin xử lý những gì?

Apache Maven Release Plugin 3.3.1 tổ chức release thành hai mốc chính:

- **`release:prepare`**: kiểm tra working copy và SNAPSHOT references, chọn versions/tag, biến đổi POM sang release version, chạy preparation goals, tạo commit/tag, chuyển lại sang next development version và commit.
- **`release:perform`**: checkout SCM tag đã chuẩn bị vào workspace riêng, build và thực hiện các Maven goals xuất bản, thường có `deploy`.

Các goals liên quan:

| Goal | Vai trò | Khi nào nên dùng |
| --- | --- | --- |
| `release:prepare` | Chuẩn bị SCM release: POM version transform, test, commit, tag. | Sau approval rõ ràng. |
| `release:perform` | Build từ tag, publish artifacts theo cấu hình. | Khi đã cho phép deploy. |
| `release:clean` | Dọn file tạm/metadata do quá trình prepare tạo theo plugin. | Sau khi xác nhận không cần resume/rollback. |
| `release:rollback` | Thử đảo thay đổi POM/SCM dựa vào backups/release descriptor còn tồn tại. | Theo runbook, sau khi xác minh Git/tag state. |
| `release:prepare-with-pom` | Chuẩn bị và sinh POM release đã resolve theo nhu cầu. | Dự án có policy cần resolved release POM. |
| `release:stage` | Phát hành theo kịch bản staging được hỗ trợ. | Khi dùng staging repository theo cấu hình. |
| `release:update-versions` | Cập nhật POM versions. | Workflow quản lý version có chủ đích. |

Đối với **Release Plugin 3.3.1**, `preparationGoals` mặc định là **`clean verify`**. Git provider có `pushChanges` mặc định là **`true`**. Vì vậy **prepare thực không phải dry-run** và có thể thay đổi remote.

Đừng nhầm `release:clean` với `git clean`: cái thứ nhất dọn release metadata/temporary files theo Maven plugin, cái thứ hai là công cụ Git với khả năng xóa files không được track.

## 5. Release version, next dev version và tag phải nhất quán

Giả sử đang ở `1.0.0-SNAPSHOT`, kế hoạch:

~~~text
POM trước prepare:          1.0.0-SNAPSHOT
POM ở release commit/tag:   1.0.0
Git tag:                    v1.0.0
POM sau prepare ở branch:   1.0.1-SNAPSHOT
~~~

**Tag phải trỏ vào source ở release version `1.0.0`, không phải commit phát triển tiếp theo.** Sau prepare thành công, branch HEAD có thể đã chuyển sang `1.0.1-SNAPSHOT`. Vì vậy không thể kiểm tra release tag bằng cách chỉ mở `pom.xml` ở HEAD hiện tại.

Tham số batch-mode phổ biến:

~~~text
-DreleaseVersion=1.0.0
-DdevelopmentVersion=1.0.1-SNAPSHOT
-Dtag=v1.0.0
~~~

Với multi-module cùng version, plugin có `autoVersionSubmodules`; còn modules release độc lập có thể cần kế hoạch per-module. **Không ép mọi module dùng chung version chỉ vì chúng nằm cùng `<modules>`.**

## 6. Git preflight: nhận diện commit và working tree

Từ checkout dự định release:

~~~bash
git status --short
git status --porcelain=v1 --untracked-files=all
git branch --show-current
git rev-parse --verify HEAD
git log -1 --format="%H%n%s"
git remote -v
~~~

Giải thích:

- `git status --porcelain=v1 --untracked-files=all`: output dễ phân tích cho những thay đổi tracked/untracked thông thường. Nếu rỗng, working tree nhìn chung sạch theo Git nhưng **ignored files vẫn có thể tồn tại**.
- `git branch --show-current`: trả branch name nếu đang gắn với branch. Trong **detached HEAD** (phổ biến ở CI) có thể rỗng.
- `git rev-parse --verify HEAD`: SHA đầy đủ của current commit.
- `git log -1`: xác minh commit đang được check out và commit subject.
- `git remote -v`: endpoints fetch/push được cấu hình; không chứng minh HEAD đã được review, tag chưa tồn tại hoặc bạn có quyền push.

**Không suy ra source đã được duyệt chỉ vì `git status` sạch.** Một commit có thể mới được merge sau khi release plan chốt, hoặc checkout đang ở ref khác. So SHA với hệ thống phê duyệt/release record.

### Không hủy dữ liệu để ép Git sạch

Tránh:

~~~text
git reset --hard
git clean -fdx
git restore .
~~~

Đây là **những lệnh rủi ro không được yêu cầu thực thi**, có thể xóa thay đổi chưa lưu. Thay vì xóa workspace dùng chung, tạo **checkout/worktree/CI runner riêng** được cho phép. Nếu có file dirty, xác định owner và commit/stash theo quy trình; mọi thay đổi version cần review lại SHA.

## 7. Kiểm tra diff, commit và tập file release

Các lệnh chỉ đọc/kiểm tra:

~~~bash
git diff --check
git diff --cached --check
git diff --stat HEAD
git show --stat --oneline HEAD
git log --oneline -5
~~~

- `git diff --check` và `git diff --cached --check` giúp phát hiện lỗi whitespace ở diff unstaged/staged.
- `git diff --stat HEAD` tóm tắt những thay đổi so với HEAD.
- `git show --stat --oneline HEAD` cho biết file được commit gần nhất thay đổi.
- `git log --oneline -5` cung cấp bối cảnh lịch sử ngắn để đối chiếu review, không thay code review đầy đủ.

Trước release nên rà ít nhất:

- Root POM và child POMs.
- Maven Wrapper và `.mvn/maven.config`.
- CI configs, pipeline secrets usage, scripts.
- `src/main/resources`, resource filters, migration files.
- Documentation/changelog/license/NOTICE.
- Assembly/shade/source/javadoc plugin configurations.
- Container manifests/Helm charts nếu sản phẩm có deploy dưới dạng khác.

Đừng tự thêm file sinh ra (`target`, test reports) vào commit vì muốn `git status` trông sạch. Khi cần đính kèm báo cáo vào release evidence, để chúng ở CI artifacts hoặc hệ thống audit riêng.

## 8. Kiểm tra local và remote tag trước release

Với tag dự kiến `v1.0.0`:

~~~bash
git tag --list "v1.0.0"
git tag --points-at HEAD
~~~

Cả hai lệnh chỉ đọc **local tags**. Nếu không thấy tag ở local vẫn chưa chứng minh remote trống. Khi policy cho phép truy vấn Git server:

~~~bash
git ls-remote --tags origin refs/tags/v1.0.0
~~~

Lệnh này **không tạo tag**; nó yêu cầu remote cung cấp ref. Nếu gặp authentication/network lỗi, không đánh dấu “tag chưa tồn tại”; trạng thái là **chưa xác minh**.

**Không force-push, xóa hoặc di chuyển tag release đã công bố** để dùng lại tên. Với release repository immutable, một tag trùng hoặc trỏ tới SHA khác là xung đột cần escalation. Tổ chức có thể yêu cầu annotated/signed tags; cấu hình Release Plugin/SCM provider phải đáp ứng điều đó.

## 9. POM SCM và Git remote là hai góc nhìn khác nhau

`git remote -v` cho biết remote hiện tại của working copy, còn `<scm>` trong POM cung cấp metadata/connection cho Maven SCM và Release Plugin.

Ví dụ:

~~~xml
<scm>
    <connection>scm:git:https://git.example.invalid/team/release-readiness-demo.git</connection>
    <developerConnection>scm:git:ssh://git@git.example.invalid/team/release-readiness-demo.git</developerConnection>
    <url>https://git.example.invalid/team/release-readiness-demo</url>
    <tag>HEAD</tag>
</scm>
~~~

Đây là **SCM giả định trên domain `.invalid`**, không phải repository thật. Với project thật:

- `<connection>`: connection dùng để truy cập SCM, thường có thể đọc.
- `<developerConnection>`: kết nối có khả năng commit/tag theo SCM provider và authentication.
- `<url>`: trang web xem source, không tự thay một SCM URL hợp lệ.
- `<tag>`: thông tin tag/revision; khi phát triển có thể là `HEAD`, ở release POM cần phản ánh tag đúng.

SCM URL phải có prefix **`scm:git:`** nếu dùng Maven Git provider. Phần transport thường là HTTPS hoặc SSH. Xác minh POM SCM connection có trỏ tới **cùng repository đã được duyệt** với Git remote release; không đổi sang personal fork để né quyền protected tags.

## 10. Dự án Java 17 runnable dành cho release readiness

Ví dụ tạo một ứng dụng Java 17 nhỏ, có thể:

1. Build và chạy bằng `mvn clean verify`.
2. Đọc version từ resource được Maven filter, tránh hardcode dev version trong Java tests.
3. Chạy **1 unit test** bằng Surefire.
4. Chạy **1 integration test `*IT`** bằng Failsafe sau phase `package`.
5. Kiểm tra JAR đã đóng gói thật có Main-Class, resource version và chạy `java -jar`.
6. Tách rõ POM có SCM/deploy URLs **minh họa `.invalid`**, nên không được dùng để thực hiện release thật.

Cây thư mục:

~~~text
release-readiness-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/vn/example/release/ReleaseReadiness.java
    │   └── resources/release-info.properties
    └── test/
        └── java/vn/example/release/
            ├── ReleaseReadinessTest.java
            └── ReleaseArtifactIT.java
~~~

Yêu cầu: **Maven 3.9+**, **JDK 17+**, kho dependency/plugin được phép truy cập. Không cần Docker, DB hoặc Git remote để chạy `clean verify`. Không chạy `release:prepare`/`perform` với SCM và distributionManagement `.invalid`.

### 10.1. pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example.release</groupId>
    <artifactId>release-readiness-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <name>Release Readiness Demo</name>
    <description>Kiểm chứng version, tests và SCM trước phát hành</description>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <scm>
        <connection>scm:git:https://git.example.invalid/team/release-readiness-demo.git</connection>
        <developerConnection>scm:git:ssh://git@git.example.invalid/team/release-readiness-demo.git</developerConnection>
        <url>https://git.example.invalid/team/release-readiness-demo</url>
        <tag>HEAD</tag>
    </scm>

    <distributionManagement>
        <repository>
            <id>example-releases</id>
            <url>https://repo.example.invalid/repository/releases/</url>
        </repository>
        <snapshotRepository>
            <id>example-snapshots</id>
            <url>https://repo.example.invalid/repository/snapshots/</url>
        </snapshotRepository>
    </distributionManagement>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>true</filtering>
                <includes>
                    <include>release-info.properties</include>
                </includes>
            </resource>
        </resources>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.5.0</version>
                <executions>
                    <execution>
                        <id>require-platform</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <requireJavaVersion>
                                    <version>[17,)</version>
                                </requireJavaVersion>
                                <requireMavenVersion>
                                    <version>[3.9,)</version>
                                </requireMavenVersion>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
                <configuration>
                    <delimiters>
                        <delimiter>@</delimiter>
                    </delimiters>
                    <useDefaultDelimiters>false</useDefaultDelimiters>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.release.ReleaseReadiness</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.2.5</version>
                <executions>
                    <execution>
                        <id>verify-final-jar</id>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                    <systemPropertyVariables>
                        <release.jar>${project.build.directory}/${project.build.finalName}.jar</release.jar>
                    </systemPropertyVariables>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-release-plugin</artifactId>
                <version>3.3.1</version>
                <configuration>
                    <tagNameFormat>v@{project.version}</tagNameFormat>
                    <preparationGoals>clean verify</preparationGoals>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### Giải thích các lựa chọn

- Project version là literal `1.0.0-SNAPSHOT`, nên việc chuyển sang `1.0.0` theo Release Plugin dễ theo dõi.
- URLs `.invalid` dùng để chứng minh sự phân biệt **readiness và deploy**. `mvn clean verify` không thử ghi tới chúng.
- `maven-enforcer-plugin` đảm bảo JDK/Maven đáp ứng baseline trước compile.
- `maven-resources-plugin` filter riêng `release-info.properties` với token `@project.version@`, không filter bừa file khác.
- `maven-jar-plugin` đặt `Main-Class`; JAR chạy được với `java -jar` vì ứng dụng không cần dependency runtime ngoài JDK.
- Surefire và Failsafe được pin cùng version `3.2.5`; Failsafe có executions để thực sự chạy ở `integration-test` và đánh giá ở `verify`.
- Release Plugin 3.3.1 có `tagNameFormat` dùng **`@{project.version}`**, không dùng `${project.version}` để tránh interpolation xảy ra khi POM còn development version.
- POM chưa chứa deployment credentials; chúng thuộc CI secret store và Maven `settings.xml` khi thực sự phát hành.

## 11. Resource metadata version, Java main và unit test

### 11.1. src/main/resources/release-info.properties

~~~properties
project.version=@project.version@
release.demo=true
~~~

Sau `mvn clean verify` ở `1.0.0-SNAPSHOT`, nội dung trong JAR kỳ vọng:

~~~properties
project.version=1.0.0-SNAPSHOT
release.demo=true
~~~

Khi Release Plugin biến POM sang `1.0.0` và chạy preparation goals, resource cũng được build với `project.version=1.0.0`. **Không đưa secrets vào resource được package**, vì người nhận JAR có thể đọc chúng.

### 11.2. src/main/java/vn/example/release/ReleaseReadiness.java

~~~java
package vn.example.release;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class ReleaseReadiness {
    private ReleaseReadiness() {
    }

    public static String greeting() {
        return "RELEASE PRECHECK: OK";
    }

    public static String buildVersion() throws IOException {
        Properties properties = new Properties();
        try (InputStream in =
                ReleaseReadiness.class.getResourceAsStream(
                        "/release-info.properties")) {
            if (in == null) {
                throw new IOException("Missing release-info.properties");
            }
            properties.load(in);
        }

        String version = properties.getProperty("project.version");
        if (version == null || version.isBlank()
                || version.contains("@")) {
            throw new IllegalStateException(
                    "Unresolved project.version");
        }
        return version;
    }

    public static String message() throws IOException {
        return greeting() + " | version=" + buildVersion();
    }

    public static void main(String[] args) throws IOException {
        System.out.println(message());
    }
}
~~~

### 11.3. src/test/java/vn/example/release/ReleaseReadinessTest.java

~~~java
package vn.example.release;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReleaseReadinessTest {
    @Test
    void messageMatchesFilteredProjectVersion() throws Exception {
        assertEquals("RELEASE PRECHECK: OK",
                ReleaseReadiness.greeting());

        String version = ReleaseReadiness.buildVersion();
        assertTrue(version.matches(
                "\\d+\\.\\d+\\.\\d+(?:-SNAPSHOT)?"));
        assertFalse(version.contains("@"));
        assertEquals("RELEASE PRECHECK: OK | version=" + version,
                ReleaseReadiness.message());
    }
}
~~~

**Điểm thiết kế quan trọng:** test **không hardcode `1.0.0-SNAPSHOT`**. Nếu hardcode, nó có thể fail khi Release Plugin tạm đổi POM sang `1.0.0` rồi chạy `clean verify`. Test xác minh format version của ví dụ và nội dung resource; nếu dự án dùng CalVer hoặc SemVer pre-release khác, phải sửa regex theo version policy thật.

## 12. Integration test chạy JAR cuối bằng Java process độc lập

Tạo **src/test/java/vn/example/release/ReleaseArtifactIT.java**:

~~~java
package vn.example.release;

import org.junit.jupiter.api.Test;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Properties;
import java.util.concurrent.TimeUnit;
import java.util.jar.Attributes;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

class ReleaseArtifactIT {
    @Test
    void packagedJarHasVersionAndRuns() throws Exception {
        String configured = System.getProperty("release.jar");
        assertNotNull(configured, "Missing release.jar system property");

        Path jarPath = Path.of(configured).toAbsolutePath();
        assertTrue(Files.isRegularFile(jarPath));

        String version;
        try (JarFile jar = new JarFile(jarPath.toFile())) {
            assertNotNull(jar.getManifest());
            assertEquals("vn.example.release.ReleaseReadiness",
                    jar.getManifest().getMainAttributes().getValue(
                            Attributes.Name.MAIN_CLASS));

            assertNotNull(jar.getEntry(
                    "vn/example/release/ReleaseReadiness.class"));

            JarEntry resource = jar.getJarEntry(
                    "release-info.properties");
            assertNotNull(resource);

            Properties data = new Properties();
            try (InputStream in = jar.getInputStream(resource)) {
                data.load(in);
            }
            version = data.getProperty("project.version");
            assertNotNull(version);
            assertTrue(version.matches(
                    "\\d+\\.\\d+\\.\\d+(?:-SNAPSHOT)?"));
        }

        String executable = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win")
                ? "java.exe" : "java";
        Path java = Path.of(System.getProperty("java.home"),
                "bin", executable);

        Process process = new ProcessBuilder(
                java.toString(), "-jar", jarPath.toString())
                .redirectErrorStream(true)
                .start();

        if (!process.waitFor(15, TimeUnit.SECONDS)) {
            process.destroyForcibly();
            process.waitFor(5, TimeUnit.SECONDS);
            fail("Packaged Java process timed out");
        }

        String output = new String(
                process.getInputStream().readAllBytes(),
                StandardCharsets.UTF_8).strip();
        assertEquals(0, process.exitValue(),
                "Child output: " + output);
        assertEquals("RELEASE PRECHECK: OK | version="
                + version, output);
    }
}
~~~

Integration test này chứng minh:

1. File JAR do `package` tạo tồn tại.
2. Manifest có đúng `Main-Class`.
3. Class Java và release metadata có trong JAR.
4. Version đã được Maven filter và khớp định dạng được chấp nhận.
5. Một JVM mới chạy **`java -jar` đúng JAR cuối**.
6. Child process thoát exit code 0 và stdout khớp metadata trong JAR.

Bài này chỉ in một dòng ngắn nên có thể đọc process output sau `waitFor`. Với chương trình ghi nhiều log, hãy tiêu thụ output song song hoặc redirect vào file để tránh deadlock do buffer đầy. Test cần timeout hữu hạn; giá trị 15 giây chỉ là mức ví dụ cho ứng dụng nhỏ.

**Không đánh đồng JAR demo với sản phẩm có DB/network/container.** Dự án thật cần thêm integration tests trên những thành phần bên ngoài và smoke tests cho artifact format thực tế.

## 13. Chạy baseline và đối chiếu stdout

Từ thư mục dự án:

~~~bash
mvn --version
mvn -B -ntp clean verify
java -jar target/release-readiness-demo-1.0.0-SNAPSHOT.jar
~~~

Trong trạng thái development version, **stdout chính xác của lệnh `java -jar` cuối cùng**:

~~~text
RELEASE PRECHECK: OK | version=1.0.0-SNAPSHOT
~~~

Trong Maven logs, Surefire dự kiến chạy **1 unit test**, Failsafe chạy **1 integration test**. Dạng thông báo, timestamps và thời gian chạy có thể khác nhau theo môi trường, nên không so cả Maven console output với một transcript cố định.

**Vì sao `mvn test` chưa đủ?** Surefire test chạy trên `target/classes` và test classpath, nhưng `ReleaseArtifactIT` chỉ chạy khi Failsafe ở phase `integration-test`/`verify`, sau khi JAR được package.

**Vì sao `mvn package` chưa đủ?** JAR được tạo nhưng không tự động chạy Failsafe verification. Lệnh preflight chuẩn của ví dụ là:

~~~bash
mvn -B -ntp clean verify
~~~

Tập đầu ra cần quan sát:

~~~text
target/release-readiness-demo-1.0.0-SNAPSHOT.jar
target/surefire-reports/...
target/failsafe-reports/...
~~~

Dấu `...` chỉ các file report tùy Maven/JUnit version, không phải tên file literal.

## 14. Kiểm tra nội dung JAR sau package

Có thể liệt kê:

~~~bash
jar tf target/release-readiness-demo-1.0.0-SNAPSHOT.jar
~~~

Các entry quan trọng:

~~~text
META-INF/MANIFEST.MF
vn/example/release/ReleaseReadiness.class
release-info.properties
~~~

Maven Jar Plugin thường thêm metadata POM dưới `META-INF/maven/...`. Tuy nhiên test quan trọng nhất ở đây là entrypoint và resource version mà ứng dụng thực dùng.

Nếu `jar tf` có class nhưng `java -jar` báo `no main manifest attribute`, hãy kiểm tra `<archive><manifest><mainClass>...` của Jar Plugin. Nếu class xuất hiện trong `target/classes` nhưng không có trong JAR, phải điều tra packaging, resource includes/excludes hoặc wrong artifact selection.

Không khắc phục lỗi bằng cách chạy main với **Maven test classpath** rồi kết luận JAR phát hành đúng. Luôn kiểm chứng artifact cuối từ thư mục build sạch.

### Checksum và provenance

Linux/macOS:

~~~bash
shasum -a 256 target/release-readiness-demo-1.0.0-SNAPSHOT.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash target\release-readiness-demo-1.0.0-SNAPSHOT.jar -Algorithm SHA256
~~~

Hash phải được tính từ bytes thực, không có một SHA-256 cố định được bịa cho bài. Để truy nguyên release, ghi cùng hash: project GAV, SCM tag SHA, Maven/JDK versions, build CI run ID và source commit.

## 15. Kiểm tra effective POM và selected dependencies

POM nguồn có thể kế thừa parent, BOM, pluginManagement và profiles. Vì vậy `grep` một dòng `<version>` trong root chưa đủ. Xuất effective POM sau build:

~~~bash
mvn -B -ntp help:effective-pom -Doutput=target/effective-pom.xml
~~~

Đọc riêng:

~~~text
project/groupId, project/artifactId, project/version
project/parent
project/dependencyManagement/dependencies
project/dependencies
project/build/plugins
project/scm
project/distributionManagement
~~~

Đây là **các vị trí XML để định hướng đọc**, không phải các lệnh XPath. Nếu muốn quan sát dependency graph được giải quyết:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
~~~

- `dependencyManagement` là catalogue/quy tắc, không tự thêm dependency vào classpath.
- Dependency tree thể hiện graph đang được dùng, gồm đường transitive.
- Parent, plugin hoặc BOM mới có thể thay version selected dù child POM không đổi trực tiếp.
- Với multi-module, cần quan sát các modules đại diện. Một goal chạy ngoài reactor đầy đủ có thể thiếu sibling artifact khi local repo chưa chứa nó.

Nếu plugin versions bị thay do parent update, phải review cả cách Surefire/Failsafe/Resources/JAR plugins hoạt động. Release readiness không nên lẫn với PR thay hàng loạt dependencies chưa kiểm chứng.

## 16. Kiểm tra JDK, Maven và build reproducibility

Chạy:

~~~bash
mvn --version
java -version
git rev-parse --verify HEAD
~~~

`mvn --version` cho thấy Maven và Java JVM đang chạy Maven; `java -version` cho thấy `java` từ PATH và có thể in vào stderr. Hai Java paths có thể khác nhau nếu `JAVA_HOME`, toolchains hoặc CI runner cấu hình không nhất quán.

Trước release:

- Pin Maven version bằng Maven Wrapper nếu team đã chọn.
- Pin plugin versions hoặc kiểm tra effective pluginManagement.
- Đảm bảo `maven.compiler.release` tương ứng Java runtime hỗ trợ.
- Xác nhận toolchains/annotation processors nếu dự án cần.
- Kiểm tra settings mirrors/repositories và khóa nguồn tải dependencies được phép.
- Không dựa vào `target/` cũ hoặc một local `.m2` chứa artifacts chưa publish.
- Với sản phẩm hỗ trợ nhiều JDK/OS, chạy test matrix đúng cam kết.
- Ghi thông tin build environment vào release evidence.

**`BUILD SUCCESS` không chứng minh artifact bytes tái lập**. Nếu yêu cầu reproducible builds, kiểm soát timestamps (`project.build.outputTimestamp` và khả năng hỗ trợ từ plugins), file order, line endings và inputs không xác định. Build hai lần trên môi trường tương đương rồi so SHA-256.

## 17. Test gate nào bắt buộc với bản phát hành?

| Gate | Ví dụ | Tại sao cần |
| --- | --- | --- |
| Unit | Surefire/JUnit | Phát hiện regression logic ở chức năng nhỏ. |
| Integration | Failsafe + test DB/service | Phát hiện lỗi kết nối và hành vi liên module. |
| Artifact smoke | `java -jar`, `JarFile` | Phát hiện thiếu resource, manifest, dependency runtime. |
| Contract/API | Kiểm thử tương thích consumers | Quan trọng khi phát hành library dùng bởi nhiều dự án. |
| Security/license | Scan dependency, secrets, SBOM | Bảo vệ supply chain và tuân thủ. |
| Migration | DB/schema/config migration tests | Giảm rủi ro khi deploy qua môi trường. |
| Quality | Enforcer/Checkstyle/static analysis | Chặn những violations mà team quy định. |
| Reproducibility | SHA/provenance | Gắn artifact với đúng source/version. |

**Không đánh dấu PASS chỉ vì một job xanh.** Cần kiểm tra suites nào được discovery và có bao nhiêu tests thực chạy. Các flags như `-DskipTests`, `-Dmaven.test.skip=true` hoặc skip parameter của từng plugin có thể làm nhiều checks không chạy.

Follows-fail nếu integration tests không được bind đúng: một project có `ExampleIT` nhưng chỉ chạy Surefire chưa chắc test đó được thực thi. Với test DB/network, dùng môi trường staging/test cô lập, timeout, resource cleanup và credentials không phải production.

## 18. Quality gate không phải chỉ là HTML report

Một website Maven Site hoặc coverage report có thể trông đầy đủ nhưng không làm build fail khi threshold không đạt, trừ khi plugin/gates được cấu hình. Một số lựa chọn:

- Maven Enforcer `requireMavenVersion` và `requireJavaVersion`.
- Enforcer `dependencyConvergence` hoặc `requireUpperBoundDeps` nếu dependency graph yêu cầu.
- JaCoCo `check` nếu team có coverage threshold.
- Checkstyle/PMD/SpotBugs với check goals theo mức độ chất lượng.
- SBOM generation/secret scanning/vulnerability scanning trong pipeline chính thức.
- License/NOTICE verification trên artifact được phát hành.

**Enforcer không chứng minh API/ABI compatibility**; một set dependencies hội tụ vẫn có thể lỗi runtime. Cần tests theo bề mặt ảnh hưởng và release notes.

## 19. Khi Git đang ở detached HEAD trong CI

Nhiều CI providers checkout commit SHA vào trạng thái **detached HEAD**. `git branch --show-current` có thể rỗng nhưng `git rev-parse HEAD` vẫn trả commit. Điều này không phải lỗi Git.

Tuy nhiên, Maven Release Plugin có thể cần **working copy/branch đủ quyền** để tạo release commits và push. Không chạy prepare thật trực tiếp trong detached-HEAD PR job và mong nó tự chọn đúng branch/tag. Quy trình release phải:

1. Chốt approved SHA.
2. Dùng checkout/branch phù hợp theo CI release design.
3. Xác minh HEAD trùng approved SHA.
4. Xác nhận remote push target và permissions.
5. Bảo vệ môi trường để chỉ một release job cho mỗi version.
6. Không dùng credentials release trên PR không tin cậy.

Nếu `git remote -v` trỏ tới mirror read-only trong khi POM `<developerConnection>` trỏ upstream, cần kiểm tra quyền và cơ chế release chính thức, không đổi URL sang personal fork để vượt hạn chế.

## 20. SCM và distributionManagement không thay nhau

Trong Maven:

- `<scm>` cho biết source repository và cách plugin truy cập source để commit/tag/checkout.
- `<distributionManagement>` cho biết nơi **artifact của project** được deploy, thường gồm release repository và snapshotRepository.
- `<repositories>` hoặc settings mirrors cho biết nơi **tải dependencies/plugins**.

Một tag tạo đúng trong Git **không có nghĩa** JAR đã được gửi lên Maven repository. Và một JAR upload thành công **không bảo đảm** nó được build từ tag được duyệt.

Bản preflight cần kiểm tra **cả ba**: source SHA, project GAV và remote artifact destination. `settings.xml` thường cung cấp credentials dựa trên `<server><id>` khớp deployment repository ID; không hardcode token vào POM.

**Lưu ý an ninh:** một URL/ID có thể bị chỉnh qua POM hoặc CLI. Không cấp token release vào job dùng POM từ PR chưa được review; dùng URL allowlist và protected environments.

## 21. Dry-run của release:prepare sau khi SCM đã đúng

Khi đã có **Git working copy sạch, SCM URL thật và quyền thực thi kiểm tra**, có thể thử:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-release-plugin:3.3.1:prepare \
    -DdryRun=true \
    -DreleaseVersion=1.0.0 \
    -DdevelopmentVersion=1.0.1-SNAPSHOT \
    -Dtag=v1.0.0
~~~

PowerShell (một dòng vì PowerShell 5.1 không dùng `\` để nối lệnh):

~~~powershell
mvn -B -ntp org.apache.maven.plugins:maven-release-plugin:3.3.1:prepare -DdryRun=true -DreleaseVersion=1.0.0 -DdevelopmentVersion=1.0.1-SNAPSHOT -Dtag=v1.0.0
~~~

**Không chạy lệnh trên POM ví dụ `.invalid`**: cấu hình SCM giả sẽ không thể checkout/commit theo như dự án thật.

### Dry-run cho thấy điều gì?

- Dự kiến chuyển POM sang `1.0.0`.
- Tag dự kiến `v1.0.0`, next dev version `1.0.1-SNAPSHOT`.
- SCM actions được mô phỏng, không tạo commit/tag thật theo Release Plugin.
- `preparationGoals` có thể được thực thi để kiểm chứng.
- Có thể tạo file mô phỏng như `pom.xml.tag`, `pom.xml.next` và release metadata theo plugin version.

**`dryRun` không có nghĩa không xảy ra mọi side effect.** `clean verify` vẫn có thể tạo test results/artifacts; một plugin tùy biến bên trong lifecycle có thể gọi API, sửa DB hoặc ghi file ngoài nếu được cấu hình kém. Hãy chạy bằng môi trường sandbox và POM đáng tin.

Sau dry-run, đọc các POM mô phỏng và kiểm tra có giữ đúng parent/dependency versions, SCM connection và modules không. Không đưa file `.tag`/`.next` vào release commit.

## 22. `release:prepare` thực thay đổi Git như thế nào?

Sau approval, một release operator mới được gọi prepare thật, ví dụ:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-release-plugin:3.3.1:prepare \
    -DreleaseVersion=1.0.0 \
    -DdevelopmentVersion=1.0.1-SNAPSHOT \
    -Dtag=v1.0.0
~~~

Theo workflow mặc định, Release Plugin:

1. Kiểm tra thay đổi trong SCM working copy.
2. Kiểm tra SNAPSHOT references.
3. Chuyển project POM từ development sang release version.
4. Điều chỉnh SCM tag metadata.
5. Chạy preparation goals (mặc định `clean verify`).
6. Commit trạng thái release vào SCM.
7. Tạo tag release.
8. Đổi POM sang next development version.
9. Commit next development state.
10. Có thể push thay đổi với Git provider do `pushChanges` mặc định `true`.

Không coi đây là phép thử. **Có thể ghi commit/tag vào upstream ngay trong chuẩn bị**. Cần chốt bản phát hành, khóa CI concurrency và quyền SCM trước.

### Cần kiểm tra gì sau prepare?

- Tag có tồn tại và trỏ đúng release commit không.
- POM ở tag có version `1.0.0`, không còn development version.
- Branch HEAD hiện tại có thể đã ở `1.0.1-SNAPSHOT`; đây là trạng thái bình thường nếu plugin hoàn tất.
- `release.properties`/logs cho biết release plan nào đã được áp dụng.
- Tag và commits đã được push đúng remote chưa.
- Chưa có artifact deploy nhầm chỉ vì source tag đã có.
- SCM audit/provenance được ghi lại theo policy.

Không dùng `git rev-parse HEAD` sau prepare làm SHA của release nếu HEAD đã ở next development commit. Hãy kiểm tra **tag SHA**.

## 23. `release:perform` là bước publish, không phải test thông thường

Sau prepare, `release:perform` thường checkout source từ tag vào thư mục khác (ví dụ `target/checkout`) rồi chạy perform goals. Mặc định của Plugin 3.3.1 là **`deploy`**, hoặc có thể thêm `site-deploy` nếu POM có `<distributionManagement><site>`.

Lệnh sau **chỉ dành cho release operator đã được cấp quyền**:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-release-plugin:3.3.1:perform
~~~

Nó có thể upload artifact tới remote repository. **Không chạy trong bài demo** vì `distributionManagement` trỏ `.invalid`, không có server/credentials thật và chưa có release approval.

**Vì sao checkout tag quan trọng?** Tránh build từ HEAD sau prepare đã đổi sang next development version. Dù build từ tag, vẫn phải kiểm tra artifact hash, POM GAV, dependencies, JDK/Maven versions và nơi deploy để bảo đảm provenance.

## 24. release.properties, resume, rollback và clean

Các file release workflow có thể bao gồm:

~~~text
release.properties
pom.xml.releaseBackup
pom.xml.tag
pom.xml.next
~~~

Tập file thực tế thay đổi theo plugin version và dry-run/prepare state; không coi danh sách trên là bắt buộc cho mọi lần chạy. `release.properties` là release descriptor quan trọng để resume/perform/rollback theo workflow.

### Khi prepare lỗi

**Không chạy lại mù.** Một prepare thất bại có thể đã:

- Sửa một số POM.
- Commit release state.
- Tạo tag local.
- Push một phần lên remote.
- Chuyển một số POM sang next development version.

Cần đọc Git status/log/tag, release.properties và backups, xác định phase nào đã hoàn thành rồi mới quyết định resume hay rollback.

Release Plugin có `resume=true` mặc định và tham số `-Dresume=false` để chạy lại từ đầu theo semantics của plugin. **`resume=false` không tự xóa remote tag, commit hay artifact đã ghi**.

### Phân biệt rollback và clean

| Goal | Tác dụng | Giới hạn quan trọng |
| --- | --- | --- |
| `release:clean` | Dọn temp/metadata release trong working copy. | Không tự rollback remote history. Có thể làm mất state cần phục hồi. |
| `release:rollback` | Dựa vào backups/release descriptor để đảo các thay đổi từ prepare, bao gồm SCM actions theo khả năng plugin/provider. | Không xóa artifact đã publish; có thể ảnh hưởng Git remote/tag và những edits mới nếu dùng sai. |

Nếu artifact release đã xuất bản, “rollback” thường phải xử lý bằng **version mới, quarantine hoặc thông báo consumers**, không đơn giản xóa tag hay cố overwrite release JAR immutable.

## 25. Multi-module release cần kiểm tra thêm

Với reactor:

~~~text
platform/                    parent POM + aggregator
├── pom.xml                  2.0.0-SNAPSHOT
├── api/pom.xml              parent platform
├── engine/pom.xml           depends on api
└── cli/pom.xml              depends on engine
~~~

Đây là sơ đồ minh họa, không phải phần của demo runnable. Preflight cần:

1. `<modules>` liệt kê đúng toàn bộ modules phải release.
2. Parent references, dependency versions và artifacts nội bộ khớp release plan.
3. Đồ thị Reactors dựa trên **actual dependencies**, không chỉ `dependencyManagement`.
4. `-pl`/profiles không vô ý loại module phải kiểm thử/phát hành.
5. Unit/integration tests của tất cả modules liên quan chạy thật.
6. Không có SNAPSHOT ngoại lai chưa xử lý.
7. Nếu dùng `autoVersionSubmodules`, tất cả modules được phép cùng release cadence.
8. Artifact classifier/attachments (sources/javadoc/shaded/ZIP) được tạo và attached đúng.
9. Release tag chứa tất cả sources để build lại, không chỉ một module.
10. Deploy nhiều module có thể lỗi một phần; `deployAtEnd` không biến upload thành transaction atomic.

Một module độc lập có version khác **không nên bị ép đổi** chỉ để trông đồng bộ. Tùy dự án cần tách release trains hoặc cấu hình multi-module version policy riêng.

## 26. CI-friendly `${revision}` cần quy trình phù hợp

Maven 3 hỗ trợ những version placeholders đặc biệt:

~~~text
${revision}
${sha1}
${changelist}
~~~

Ví dụ một cách thiết kế khác:

~~~xml
<version>${revision}</version>
<properties>
    <revision>1.0.0-SNAPSHOT</revision>
</properties>
~~~

Đoạn POM này **không áp dụng cho ví dụ literal-version mục 10**. Không dùng property bất kỳ như `${myVersion}` thay `project.version` rồi mặc định Maven hỗ trợ giống `${revision}`.

Khi dùng CI-friendly versions trên Maven 3:

- Internal dependency references thường phải dùng `${project.version}` theo hướng dẫn Maven.
- Khi install/deploy POM cho consumers, **Flatten Maven Plugin** có thể cần thiết để POM đã publish không chứa unresolved placeholders.
- Maven Release Plugin có logic biến đổi literal versions; phối hợp nó với `${revision}` phải được thiết kế và kiểm chứng riêng, không áp dụng nguyên lệnh `release:prepare` của demo rồi đoán sẽ đúng.
- Test POM thực xuất bản, không chỉ POM trong workspace nguồn.

## 27. Security, supply chain và provenance

Một release là hành động làm artifact có thể được sử dụng lâu dài. Trước publish:

- Scan source và packaged artifact để tránh nhúng private key, token, `.env`, credential hoặc dữ liệu cá nhân.
- Đánh giá dependency vulnerabilities theo policy và khả năng khắc phục.
- Kiểm tra license/NOTICE; đặc biệt nếu dùng shaded JAR.
- Sinh/kiểm tra SBOM khi organization yêu cầu.
- Xem API/ABI compatibility cho library public.
- Chốt build provenance: SCM commit/tag SHA, GAV, plugin/JDK versions, artifact digest.
- Chỉ dùng remote repository hosting/credential IDs do tổ chức quản trị.
- Hạn chế quyền publish đến protected branches/tags; không đưa release secrets vào untrusted pull request workflows.
- Nếu dùng staging, promote **đúng bytes đã được duyệt**, không build lại phiên bản mới rồi gọi cùng GAV.

**SHA-256 chứng minh hai file có cùng bytes, nhưng không tự chứng minh file xuất phát từ source đã duyệt.** Phải liên kết checksum với source SHA, builder identity và audit trail.

## 28. Bảng lỗi thường gặp khi chuẩn bị phát hành

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Working copy dirty | POM/source uncommitted hoặc untracked file. | `git status` và owner của từng file; không reset bừa. |
| Release tag đã có | Tag collision local/remote. | `git tag -l` và `git ls-remote`, đối chiếu SHA. |
| SCM không thể commit/tag | `developerConnection` sai hoặc thiếu quyền push. | So POM/remote và protected tag policy. |
| Dry-run fail mặc dù test baseline pass | POM release version làm đổi filtering/test; profiles khác. | Đọc simulated POM và preparation goals logs. |
| Snapshot dependency error | Artifact bên ngoài chưa có release hoặc plugin/report dependency snapshot. | Xem effective POM và selected dependency graph. |
| Parent POM không resolve | Parent GAV, repository, relativePath sai. | Kiểm tra SCM/repo settings và parent version. |
| Build local xanh, CI đỏ | JDK/Maven/cache/settings/profiles khác. | Đối chiếu `mvn --version` và môi trường CI. |
| `release:prepare` fail nhưng tag xuất hiện | Lỗi ở phase sau khi tag hoặc push partial. | Kiểm tra tag/commits/descriptor, không resume mù. |
| Unit test xanh nhưng artifact lỗi | JAR thiếu resource, Main-Class, runtime dependency. | Smoke test đúng JAR/WAR cuối. |
| Tests skipped | `-DskipTests`, profiles hoặc discovery names sai. | Đọc Surefire/Failsafe reports. |
| `release:perform` không thấy release.properties | Prepare chưa có hoặc metadata bị xóa. | Xác minh tag và descriptor trước perform. |
| Deploy HTTP 401/403 | Credential ID/scope hoặc policy sai. | So settings/server ID, token scope và URL. |
| Deploy HTTP 409 | Release version đã tồn tại/immutable. | Xác minh repository state; không retry overwrite. |
| Deploy timeout | Có thể upload một phần rồi client mất response. | Kiểm tra remote repository trước khi quyết định retry. |
| HEAD sau prepare có next dev version | Hành vi bình thường của Release Plugin. | Đối chiếu release tag SHA, không dùng HEAD thay tag. |
| `release:clean` rồi rollback không được | Descriptor/backup đã bị xóa. | Dùng release recovery runbook, không rewrite tags tùy tiện. |

## 29. Bài tập thực hành

**Bài 1 — dựng project.** Tạo POM, resource, hai classes test và main class trong mục 10–12. Chạy `mvn -B -ntp clean verify`; nêu vì sao có **1 unit test** và **1 artifact IT**.

**Bài 2 — stdout.** Chạy `java -jar target/release-readiness-demo-1.0.0-SNAPSHOT.jar`; đối chiếu chính xác **RELEASE PRECHECK: OK | version=1.0.0-SNAPSHOT**.

**Bài 3 — source identity.** Trong một repo Git thử nghiệm, chạy `git status`, `git rev-parse HEAD`, `git remote -v`, `git tag --list`. Ghi bản phát hành được duyệt phải có những field nào ngoài version.

**Bài 4 — thay version khi test.** Trên một bản sao được phép, đổi project version sang `1.0.0` và chạy `clean verify`. Chứng minh unit test không phụ thuộc hardcoded development version; resource trong JAR ghi đúng `1.0.0`. Không deploy bản demo.

**Bài 5 — dependency snapshot.** Vẽ một dependency graph có một external `2.4.0-SNAPSHOT`. Giải thích vì sao version của project đang là SNAPSHOT trước prepare được phép, còn external snapshot có thể bị gate release từ chối.

**Bài 6 — tag collision.** Nêu khác biệt giữa kết quả `git tag --list v1.0.0` tại local và `git ls-remote --tags origin refs/tags/v1.0.0`. Khi remote không truy cập được, trạng thái gate phải là gì?

**Bài 7 — dry-run.** Trên **repository thử nghiệm với SCM URL thật và có quyền**, chạy dry-run với `releaseVersion`, `developmentVersion`, `tag` đã xác định. Đọc POM `.tag`/`.next`; giải thích vì sao không được mặc định dry-run là không có side effects ngoài SCM.

**Bài 8 — phân biệt prepare và perform.** Lập bảng commit/tag/upload nào có thể diễn ra ở mỗi goal. Tại sao không dùng `release:perform` chỉ để xác minh build?

**Bài 9 — thất bại và phục hồi.** Giả lập mô tả một prepare fail sau khi tag đã được tạo. Liệt kê Git status/tag/release.properties checks trước khi chọn resume hoặc rollback; không chạy các lệnh ghi/xóa tag thật.

**Bài 10 — thiết kế release CI.** Cho PR build quyền đọc, protected release job quyền SCM tag/push, deployment job quyền upload. Ghi rõ gates, concurrency control, hash/provenance và cách xác minh artifact sau publish.

## 30. Checklist cuối cùng trước khi bấm phát hành

1. Project GAV và release version được duyệt.
2. Next development version và tag name được chốt.
3. Full Git commit SHA khớp source đã review.
4. Working tree sạch, không có chỉnh sửa chưa kiểm soát.
5. SCM developerConnection và Git remote trỏ đúng repository.
6. Tag chưa tồn tại local/remote theo chính sách.
7. POM parent/child/internal dependency versions nhất quán.
8. Không có SNAPSHOT/dynamic dependency trái chính sách.
9. Plugin/BOM/parent updates được review và pin version thích hợp.
10. Maven/JDK/Toolchain đáp ứng requirements.
11. Unit tests đã thực thi, không bị skip.
12. Integration/Failsafe tests đã thực thi, không bị skip.
13. Artifact smoke test chạy đúng JAR/WAR/ZIP cuối.
14. Metadata, manifest, resource filtering và runtime deps hợp lệ.
15. Security/license/secret checks được thông qua.
16. Changelog, migration docs và release notes đã sẵn sàng.
17. CI pipeline tách verify khỏi SCM/tag/publish.
18. Release credentials chỉ dành cho môi trường protected.
19. Deployment target và hosted repo policy đúng release/snapshot.
20. Dry-run đã được review nếu release workflow dùng nó.
21. Approval của release owner đã có.
22. Sau prepare, tag SHA/POM release version được đối chiếu.
23. Sau perform, artifact trên remote được kiểm chứng GAV/hash.
24. Có kế hoạch ứng phó nếu tag/deploy fail một phần.

### Kết luận

**Chuẩn bị phát hành Maven là xác minh đầy đủ version, tests và nguồn SCM chứ không chỉ chạy một Maven goal.** `1.0.0-SNAPSHOT` có thể hợp lệ cho development branch trước prepare; release target, tag và next development version phải thống nhất. Bản kiểm chứng có giá trị phải chạy `mvn clean verify`, kiểm tra unit/integration reports, manifest và runtime artifact cuối, đồng thời xác định source commit SHA và Git trạng thái sạch.

**Release Plugin tự động hóa những thao tác có tác động lớn**: `release:prepare` có thể commit/tag/push; `release:perform` có thể deploy. Dry-run là bước thử hữu ích nhưng không biến mọi plugin khác thành vô hại. Chỉ chuyển từ preflight sang chuẩn bị thật và xuất bản khi có approval, source provenance, quyền SCM/repository đúng và kế hoạch phục hồi cho trường hợp thất bại.

### Tài liệu chính thức

- [Apache Maven — Releasing Projects](https://maven.apache.org/guides/mini/guide-releasing.html)
- [Maven Release Plugin 3.3.1 — Introduction](https://maven.apache.org/maven-release/maven-release-plugin/)
- [Maven Release Plugin 3.3.1 — release:prepare](https://maven.apache.org/maven-release/maven-release-plugin/prepare-mojo.html)
- [Maven Release Plugin 3.3.1 — Prepare a Release](https://maven.apache.org/maven-release/maven-release-plugin/usage/prepare-release.html)
- [Maven Release Plugin 3.3.1 — release:perform](https://maven.apache.org/maven-release/maven-release-plugin/perform-mojo.html)
- [Maven Release Plugin — Non-interactive Release](https://maven.apache.org/maven-release/maven-release-plugin/usage/non-interactive-release.html)
- [Maven Release Plugin — Rollback](https://maven.apache.org/maven-release/maven-release-plugin/usage/rollback-release.html)
- [Maven Release Plugin — Clean a Release](https://maven.apache.org/maven-release/maven-release-plugin/usage/clean-release.html)
- [Apache Maven — SCM URLs](https://maven.apache.org/pom-scm-urls.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — CI-friendly Versions](https://maven.apache.org/guides/mini/guide-maven-ci-friendly.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/)
