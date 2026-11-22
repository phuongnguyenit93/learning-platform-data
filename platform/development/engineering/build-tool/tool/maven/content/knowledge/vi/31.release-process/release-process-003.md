# Maven Release Plugin: vai trò của release:prepare và release:perform

## 1. Tại sao Maven cần hai bước phát hành?

Trong chủ đề **Quy trình phát hành**, cần phân biệt hai việc thường bị gộp thành một:

- **Chốt chính xác nguồn phát hành:** kiểm tra trạng thái source control, chọn version phát hành, đổi Maven POM sang version ổn định, chạy kiểm thử, commit và tạo **SCM tag** để đánh dấu một phiên bản source không thay đổi.
- **Xuất bản artifact của nguồn đã chốt:** lấy đúng source từ SCM tag, build/test/package và **deploy** JAR/POM/attachments vào Maven artifact repository.

**Maven Release Plugin** điều phối hai việc đó bằng hai goal chính:

1. **`release:prepare`**: chuẩn bị phiên bản phát hành trong SCM; tạo release commits/tag, cập nhật nhánh làm việc sang development version tiếp theo. *Mặc định goal này không deploy artifact lên repository*.
2. **`release:perform`**: dựa trên tag/SCM information do prepare tạo, checkout source đã gắn tag rồi thực hiện Maven goals phát hành; thường có `deploy` để publish artifacts. *Goal này không đơn giản build trạng thái working tree hiện tại*.

Sơ đồ logic:

```text
Working tree, version 1.0.0-SNAPSHOT
          |
          v
    release:prepare
          |
          +-- check SCM clean / snapshot dependencies
          +-- set release version 1.0.0
          +-- run preparation goals (default: clean verify)
          +-- commit release POM(s)
          +-- create SCM tag release-lab-1.0.0
          +-- bump working branch to 1.0.1-SNAPSHOT
          +-- commit next development POM(s)
          +-- write local release.properties descriptor
          |
          v
    release:perform
          |
          +-- read SCM tag from release.properties
          +-- checkout tag into target/checkout
          +-- fork Maven against source in checkout
          +-- run perform goals (deploy by default;
          |   may include site-deploy with site config)
          +-- release JAR/POM goes to Maven repository
          |
          v
  Tag remains at 1.0.0
  Working branch remains at 1.0.1-SNAPSHOT
  Artifact coordinates: dev.course:release-lab:1.0.0
```

**Ba đối tượng khác nhau:** SCM tag = mốc source trong Git/SVN; Maven artifact version = tọa độ JAR/POM để consumer tải; `release.properties` = descriptor tạm của phiên release local. Không coi một trong ba là vật thay thế cho hai cái còn lại.

Bài này tham chiếu **Maven Release Plugin 3.3.1**, Maven 3.9.x và Java 17. Version được ghim cho ví dụ, không phải tuyên bố bản phát hành mới nhất. Đây là tài liệu kỹ thuật và bài thực hành **trên repository sandbox cục bộ**; không có lệnh nào cần thực hiện trên production SCM hoặc artifact repository.

## 2. So sánh release:prepare với release:perform

| Khía cạnh | `release:prepare` | `release:perform` |
| --- | --- | --- |
| Mục đích | Chốt POM version, tag source, chuẩn bị nhánh phát triển tiếp | Build và phát hành artifact từ SCM tag |
| Nguồn code chính | Working copy Git/SVN hiện tại | Checkout riêng của tag đã chốt |
| Kiểm tra working tree | Kiểm tra thay đổi chưa commit | Dùng checkout của source tag |
| Xử lý version | `x-SNAPSHOT → x → y-SNAPSHOT` | Giữ release version đã nằm trong tag |
| SCM side effects | Thông thường commit + tag và push (Git khi cấu hình cho phép) | Thông thường checkout; không cần commit đổi release version |
| Maven build | Preparation goals, mặc định `clean verify` | Perform goals, mặc định ít nhất `deploy` |
| Maven artifact publication | **Không phải mục đích mặc định** | **Có**, nếu goals/deploy config cho phép |
| File hỗ trợ | `release.properties`, POM backups/variants tùy phase | Dùng release descriptor và workspace checkout |
| Phụ thuộc quan trọng | Clean SCM, SCM write/tag permissions, version/dependency policy | SCM read/checkout, artifact repository write permissions, build environment |
| Kết quả chính | Một SCM tag + development branch mới | Release artifacts từ tag có thể được tiêu thụ qua repository |

**Cụm từ “prepare thành công” không có nghĩa đã deploy artifact.** Tương tự, build `mvn deploy` thủ công có thể upload JAR nhưng **không tạo release SCM tag** theo cơ chế Release Plugin.

## 3. Bức tranh lifecycle: release plugin không phải một phase

Maven có default lifecycle:

```text
validate -> compile -> test -> package -> verify -> install -> deploy
```

Còn `release:prepare`/`release:perform` là **goals của Maven Release Plugin**, điều phối những bước riêng qua SCM và các Maven invocations.

- `mvn clean verify` chỉ build/test project theo lifecycle, không tự tag Git.
- `mvn install` đặt artifact vào local Maven repository, không tự tag hay publish remote.
- `mvn deploy` đi tới deployment, có thể publish artifact từ current project version; không tự tạo release tag.
- `mvn release:prepare` chạy quy trình release SCM, trong đó **mặc định fork/chạy `clean verify`** sau khi tạm đổi POM sang release version.
- `mvn release:perform` checkout release tag và thực thi build release (thường là `deploy`).

Đặc biệt trong Maven Release Plugin 3.3.1, perform goals mặc định là:

- **`deploy`** khi project không có `distributionManagement/site`.
- **`deploy site-deploy`** khi có `distributionManagement/site` theo thông số goal của phiên bản này.

Nếu pipeline muốn goals khác, cần cấu hình `<goals>` hoặc `-Dgoals` có chủ đích, đảm bảo vừa test vừa publish đúng artifacts. **Không tự động thay perform goals bằng `package`** rồi tuyên bố hoàn tất phát hành; `package` không upload artifact.

### 3.1. Vì sao có thể test hai lần?

Thông thường:

1. Prepare chạy `clean verify` với version phát hành đã chuyển sang release để xác nhận nguồn và POM hợp lệ trước tag.
2. Perform checkout tag và chạy `deploy`; lifecycle deploy đi qua compile, test, package, verify, install rồi deploy.

Khi plugin/phases mặc định được giữ, việc tests xuất hiện **hai lần** trong release workflow không phải lỗi. Các executions chạy trên **hai ngữ cảnh khác nhau**: chuẩn bị tại working copy so với build từ release-tagged checkout. Nếu có lý do muốn giảm lặp, hãy cân nhắc caching/staging sau khi hiểu trade-off thay vì tự tắt tests ở perform.

## 4. Chuỗi thay đổi SCM và version qua prepare

Giả sử source đầu vào:

```xml
<groupId>dev.course</groupId>
<artifactId>release-lab</artifactId>
<version>1.0.0-SNAPSHOT</version>
```

Version phát hành mong muốn: `1.0.0`.

Next development version mong muốn: `1.0.1-SNAPSHOT`.

Tên tag dự kiến: `release-lab-1.0.0`.

Trình tự điển hình của `release:prepare`:

1. Kiểm tra POM, SCM connection, working tree clean và những yêu cầu chuẩn bị.
2. Kiểm tra dependency/plugin snapshot chưa được giải quyết theo release policy. Một release không nên phụ thuộc vào một external SNAPSHOT có thể thay đổi; trong multi-module build, plugin có cơ chế điều chỉnh các internal module versions.
3. Xác định release version, development version và tag name (prompt hoặc tham số non-interactive).
4. Đổi POM(s) từ `1.0.0-SNAPSHOT` sang `1.0.0`; cập nhật thông tin SCM tag.
5. Chạy preparation goals (default `clean verify`) với POM release version.
6. Commit release POM(s).
7. Tạo tag `release-lab-1.0.0` trong Git/SVN.
8. Đổi working branch POM(s) thành `1.0.1-SNAPSHOT`.
9. Commit development POM(s); lưu trạng thái release để perform dùng.
10. Với Git và cấu hình mặc định phù hợp, plugin có thể push commits/tags lên upstream; cần quyền và branch policy cho việc này.

Trạng thái có thể hình dung:

```text
Git branch:
  commit A: pom version 1.0.0-SNAPSHOT (trước release)
       |
  commit B: pom version 1.0.0  <-- tag release-lab-1.0.0
       |
  commit C: pom version 1.0.1-SNAPSHOT (working branch HEAD)

Release artifact build later:
  dev.course:release-lab:1.0.0
  source = commit B/tag release-lab-1.0.0
```

**Tuyệt đối không dùng working branch HEAD sau prepare để đại diện source release**: HEAD lúc này thường đã chứa **next development version**. Perform phải dùng tag.

### 4.1. Tag trong SCM khác artifact version

Git tag có thể được chọn theo convention tùy tổ chức (`v1.0.0`, `release-lab-1.0.0`...). Maven artifact GAV không tự biến thành Git tag.

Ví dụ:

```text
SCM tag:             release-lab-1.0.0
groupId:             dev.course
artifactId:          release-lab
artifact version:    1.0.0
release artifact:    release-lab-1.0.0.jar
next branch version: 1.0.1-SNAPSHOT
```

Tại thời điểm prepare, Git tag có thể đã tồn tại **nhưng artifact JAR chưa xuất bản**. Sau perform, cả SCM tag và artifact cần được đối chiếu về version/provenance.

## 5. release.properties, backup POM và thư mục checkout

Release Plugin sử dụng một **release descriptor** tên `release.properties` trong working copy để ghi thông tin phase, SCM/tag và các tham số cần thiết cho perform/resume. Các chi tiết keys thay đổi theo plugin version; **không tự tạo hoặc sửa file này bằng tay**.

Một số file sinh ra xung quanh prepare/dry-run có thể là:

```text
release.properties
pom.xml.releaseBackup
pom.xml.tag
pom.xml.next
pom.xml.backup  (tùy tình huống/version)
target/
    checkout/
```

Đây là những **tên/đường dẫn khả dĩ**, không phải cam kết mọi invocation đều tạo đủ những file trên. Trong dry-run, Maven Release Plugin thường tạo các variants POM để kiểm tra preview mà không commit/tag thật.

Thông tin cần nhớ:

- `release.properties` quan trọng để `release:perform` biết tag đã prepare.
- `target/checkout` là checkout mặc định của perform; không phải working tree đã đổi sang next development.
- Backup POM phục vụ quá trình phục hồi/rollback khi có lỗi.
- `release:clean` dọn các temporary release files/descriptors, **không thay thế rollback SCM**.
- **Không chạy `release:clean` giữa prepare thành công và perform** khi perform cần descriptor hiện tại.
- Descriptor là state local: nếu chạy perform trên máy khác, cần giữ/di chuyển descriptor đúng hoặc cung cấp SCM connection/tag bằng phương án được plugin hỗ trợ.

Không commit các file temporary release này vào Git. Chúng thường nên được ignore và chỉ tồn tại trong release workspace.

## 6. Cấu hình Maven Release Plugin trong POM

Một ứng dụng nhỏ chỉ cần Java source/JUnit, Maven Release Plugin, SCM metadata và distributionManagement để làm thí nghiệm full workflow. POM có thể đặt:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-release-plugin</artifactId>
    <version>3.3.1</version>
    <configuration>
        <tagNameFormat>@{project.artifactId}-@{project.version}</tagNameFormat>
        <preparationGoals>clean verify</preparationGoals>
        <goals>deploy</goals>
    </configuration>
</plugin>
```

Đây là **plugin snippet**, cần đặt dưới `<build><plugins>` của POM đầy đủ. Dùng tên placeholder `@{project.version}`, **không phải `${project.version}`**, trong `tagNameFormat` để Release Plugin tính version sau khi biến đổi POM. Mục `goals>deploy` là quyết định minh họa: chỉ publish Maven artifact, không cố chạy site-deploy.

### 6.1. Các điều kiện tiên quyết thường gặp

- Git hoặc SCM provider mà Maven Release Plugin hỗ trợ có trên PATH/đã cấu hình.
- Source đã commit, không có thay đổi chưa commit gây lỗi prepare.
- Có `<scm><connection>...` và thường `<developerConnection>...` hợp lệ; CI account có quyền tạo commits/tags/push.
- Nếu repository manager dùng HTTPS, cần settings credentials riêng với SCM authentication.
- POM version đang ở dạng phát triển `x-SNAPSHOT`; phiên release dự kiến hợp lệ và chưa trùng tag.
- Không có external SNAPSHOT dependencies trái policy.
- Build/test/quality gates sẵn sàng chạy non-interactive.
- Checkout/tag có thể đọc được bởi máy chạy perform.
- Đích `distributionManagement/repository` trỏ đến hosted release repository hoặc sandbox file transport, **không phải read-only mirror**.
- Thiết lập JDK/Maven/plugin versions thống nhất cho prepare và perform.
- Quy trình release CI có phê duyệt, kiểm soát protected branch/tag và release credentials.

**Quan trọng:** Maven Release Plugin **không tự cung cấp toàn bộ security/approval/provenance policy**. Nó giúp tự động hóa chuyển version/tag/build/deploy; trách nhiệm bảo vệ release còn thuộc CI và SCM/repository servers.

## 7. Bài thực hành an toàn: Maven Java 17 + Git local bare remote + file repository

Phần này giúp phân biệt rõ two stages mà **không chạm SCM hoặc Maven repository doanh nghiệp**. Các đường dẫn sandbox là của một ví dụ **POSIX Linux/macOS**; Windows cần thay bằng đường dẫn và file URI hợp lệ theo môi trường.

Chọn workspace dùng riêng:

```text
/tmp/mvn-release-sandbox/
├── remote.git/              (bare Git repository, đóng vai remote)
├── artifacts/
│   ├── releases/            (Maven file repository cho release)
│   └── snapshots/           (Maven file repository cho SNAPSHOT)
└── release-lab/             (working Git repository)
    ├── pom.xml
    ├── .gitignore
    └── src/
        ├── main/java/dev/course/
        │   ├── ReleaseMessage.java
        │   └── App.java
        └── test/java/dev/course/
            └── ReleaseMessageTest.java
```

**Yêu cầu:** JDK 17+, Maven 3.9.x, Git 2.28+ (cho option `--initial-branch`), Bash/zsh, quyền ghi vào `/tmp/mvn-release-sandbox` và khả năng tải Maven plugins/JUnit nếu cache chưa có.

Các lệnh trong phần này là **hướng dẫn người học tự chạy trong sandbox riêng**, không phải thao tác đã được thực thi ở workspace của bạn.

### 7.1. Tạo bare remote và working directory

Trên Bash/zsh:

```bash
mkdir -p /tmp/mvn-release-sandbox
cd /tmp/mvn-release-sandbox

git init --bare --initial-branch=main remote.git

mkdir -p release-lab/src/main/java/dev/course
mkdir -p release-lab/src/test/java/dev/course
mkdir -p artifacts/releases artifacts/snapshots

cd release-lab
git init --initial-branch=main
git config user.name "Maven Release Lab"
git config user.email "maven-release-lab@example.invalid"
git remote add origin file:///tmp/mvn-release-sandbox/remote.git
```

Đây là Git **local bare remote** để minh họa tác dụng commit/tag/push của prepare; không liên quan tài khoản GitHub/GitLab của tổ chức. Dùng tài khoản Git identity giả định chỉ trong repository lab này; không thay đổi global Git config.

Đừng lặp lệnh `git init` trong repository làm việc thật. Nếu đã có working copy và remote, hãy dùng một thư mục lab mới để tránh accidental commits/tags.

### 7.2. POM đầy đủ

Tạo `/tmp/mvn-release-sandbox/release-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.course</groupId>
    <artifactId>release-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <scm>
        <connection>scm:git:file:///tmp/mvn-release-sandbox/remote.git</connection>
        <developerConnection>scm:git:file:///tmp/mvn-release-sandbox/remote.git</developerConnection>
        <tag>HEAD</tag>
    </scm>

    <distributionManagement>
        <repository>
            <id>lab-releases</id>
            <url>file:///tmp/mvn-release-sandbox/artifacts/releases</url>
        </repository>
        <snapshotRepository>
            <id>lab-snapshots</id>
            <url>file:///tmp/mvn-release-sandbox/artifacts/snapshots</url>
        </snapshotRepository>
    </distributionManagement>

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
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-install-plugin</artifactId>
                <version>3.1.4</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-deploy-plugin</artifactId>
                <version>3.1.4</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-release-plugin</artifactId>
                <version>3.3.1</version>
                <configuration>
                    <tagNameFormat>@{project.artifactId}-@{project.version}</tagNameFormat>
                    <preparationGoals>clean verify</preparationGoals>
                    <goals>deploy</goals>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Giải thích POM:**

- `<version>1.0.0-SNAPSHOT</version>`: source đang phát triển, chuẩn bị chuyển thành release `1.0.0`.
- `<scm>`: Release Plugin biết Git URL để commit/tag/checkout. Đây là **file URL cố định của sandbox**, không phải domain/network repository.
- `<developerConnection>`: thông tin SCM hỗ trợ thao tác ghi; khác `<distributionManagement>`.
- `<distributionManagement>`: chứa hai Maven artifact repositories **trên cùng máy**, không chứa remote production.
- Release Plugin được ghim `3.3.1`; preparation goal là `clean verify`; perform goals là `deploy` để chỉ xuất bản artifact.
- Maven Deploy Plugin version `3.1.4` dùng file transport tới `artifacts/releases`.
- Surefire chạy JUnit Jupiter, Compiler dùng Java release 17.
- Cả `<scm>` lẫn `distributionManagement` **không chứa mật khẩu**.
- Project là một module JAR. Đa module có các cân nhắc riêng ở mục sau.

**Nếu muốn chạy trên Windows**, thay cả hai `scm:git:file:///...` và `file:///...` bằng file URI tuyệt đối hợp lệ như `file:///C:/path/...`, đồng thời thay các lệnh Bash bằng PowerShell/Windows equivalents; không dùng nguyên đường dẫn `/tmp` nếu máy không có POSIX filesystem.

### 7.3. Java source: ReleaseMessage.java

Tạo `src/main/java/dev/course/ReleaseMessage.java`:

```java
package dev.course;

public final class ReleaseMessage {
    private ReleaseMessage() {
    }

    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        return "Xin chào, " + name.strip() + "!";
    }
}
```

Sử dụng Java 17 API `String.isBlank` và `String.strip`, không cần dependency runtime bên ngoài JDK.

### 7.4. App.java

Tạo `src/main/java/dev/course/App.java`:

```java
package dev.course;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(
                "RELEASE_LAB: " + ReleaseMessage.greet(" Maven "));
    }
}
```

**Stdout chính xác do code Java in:**

```text
RELEASE_LAB: Xin chào, Maven!
```

### 7.5. ReleaseMessageTest.java

Tạo `src/test/java/dev/course/ReleaseMessageTest.java`:

```java
package dev.course;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ReleaseMessageTest {
    @Test
    void greetsVietnameseName() {
        assertEquals("Xin chào, Maven!",
                ReleaseMessage.greet(" Maven "));
    }

    @Test
    void rejectsBlank() {
        assertThrows(IllegalArgumentException.class,
                () -> ReleaseMessage.greet(" "));
    }

    @Test
    void rejectsNull() {
        assertThrows(IllegalArgumentException.class,
                () -> ReleaseMessage.greet(null));
    }
}
```

Đây là **3 JUnit 5 unit tests**. Release Plugin không làm test framework; nó kích hoạt Maven lifecycle đã cấu hình, trong đó Surefire chịu trách nhiệm chạy tests.

### 7.6. .gitignore cho build/release temporary files

Tạo `release-lab/.gitignore`:

```gitignore
target/
release.properties
pom.xml.releaseBackup
pom.xml.tag
pom.xml.next
pom.xml.branch
*.releaseBackup
*.tag
*.next
```

Mục đích là tránh commit Maven build outputs và release descriptors tạm. Không thêm chính `pom.xml` hoặc `src/` vào ignore.

Các file tạm có thể khác nhau tùy plugin/SCM/phase; sau dry-run, xem `git status --short` và các files thực. Nếu có file ngoài ý muốn chưa ignore, xem rõ nội dung trước khi chỉnh; đừng dùng `git add -A` mù vào một repository lẫn source với credentials.

## 8. Kiểm tra Java và tạo commit ban đầu

Ở `/tmp/mvn-release-sandbox/release-lab`:

```bash
mvn -version
git --version

mvn clean verify
java -cp target/classes dev.course.App
```

Expected Java stdout:

```text
RELEASE_LAB: Xin chào, Maven!
```

Kết quả unit tests mong đợi:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Hai dòng trên chỉ là **các dấu hiệu rút gọn** trong Maven output, không phải log nguyên văn.

Sau đó commit và push source demo **tới local bare remote**:

```bash
git add pom.xml .gitignore src
git commit -m "Initial Maven release lab"
git push -u origin main

git status --short
git log --oneline -1
```

`git status --short` kỳ vọng **không in dòng nào** sau commit/push nếu những file tạm đã được ignore đúng. SCM clean là điều kiện quan trọng để `release:prepare` làm việc theo mặc định.

**Git commit/push ở đây là trên repository test riêng**. Trên project thật, chúng là thay đổi SCM có thể ảnh hưởng cộng tác viên; không được thực hiện chỉ để “thử xem release plugin chạy thế nào”.

## 9. Bước kiểm tra an toàn nhất: prepare dry-run

Trước khi tạo tag và push thật, dùng:

```bash
mvn -B -DdryRun=true \
    -DreleaseVersion=1.0.0 \
    -DdevelopmentVersion=1.0.1-SNAPSHOT \
    -Dtag=release-lab-1.0.0 \
    release:prepare
```

Hoặc dùng một dòng trên shell phù hợp:

```bash
mvn -B -DdryRun=true -DreleaseVersion=1.0.0 -DdevelopmentVersion=1.0.1-SNAPSHOT -Dtag=release-lab-1.0.0 release:prepare
```

- `-B` là Maven batch mode, không hỏi câu hỏi tương tác.
- `-DreleaseVersion=1.0.0` chọn Maven release version.
- `-DdevelopmentVersion=1.0.1-SNAPSHOT` chọn version tiếp theo của nhánh làm việc.
- `-Dtag=release-lab-1.0.0` chỉ định SCM tag, tránh phụ thuộc default naming.
- `-DdryRun=true` yêu cầu preview các bước release; **không commit/tag SCM và không sửa checkout thực theo nghĩa một release thật**.
- Prepare vẫn có thể thực hiện preparation goals/kiểm tra và tạo các POM variants/temp files để xem; nó không phải lệnh hoàn toàn không có tác động filesystem.

Kiểm tra:

```bash
git status --short
git tag --list "release-lab-*"
git log --oneline -3
```

Kỳ vọng dry-run **không tạo tag phát hành mới**, không tạo release commits mới trên Git. Lệnh này cũng **không deploy artifact** vào Maven repository. Hãy quan sát những file preview mà plugin tạo ra để hiểu version replacement trước khi release thật.

Sau khi kiểm tra, có thể dọn file tạm:

```bash
mvn release:clean
```

**`release:clean` chỉ dọn release descriptors/backup trong working directory, không hoàn tác các commit/tag SCM của một release thật**. Trong bài, dùng nó sau dry-run để tránh descriptor/preview cũ ảnh hưởng lần prepare thực tế.

### 9.1. dry-run không đủ chứng minh perform sẽ deploy được

Dry-run prepare giúp phát hiện:

- Lỗi SCM connection/plugin config ở mức kiểm tra.
- Version kế tiếp không hợp lý.
- SNAPSHOT dependency vi phạm policy.
- Release POM transform không đúng.
- Build/test ở version phát hành thất bại.

Nhưng dry-run **không bảo đảm**:
- Git remote sẽ chấp nhận push tag/commits thật khi protected branch/tag rules có hiệu lực.
- Artifact repository cho phép publish release và credentials đúng.
- Perform checkout/build trên môi trường release CI có cùng JDK/plugins/permissions.
- Artifact sau deploy đã được ký, scan hoặc approved.

Vì vậy pipeline vẫn phải có kiểm tra release thật và repository metadata/provenance.

## 10. release:prepare thật trong sandbox

**Chỉ chạy phần này trong local Git sandbox**, sau khi đã kiểm tra POM URLs và remote. Lệnh này **có side effects SCM thật** ngay cả khi URLs đều ở local filesystem.

```bash
mvn -B \
    -DreleaseVersion=1.0.0 \
    -DdevelopmentVersion=1.0.1-SNAPSHOT \
    -Dtag=release-lab-1.0.0 \
    release:prepare
```

Lệnh một dòng tương đương:

```bash
mvn -B -DreleaseVersion=1.0.0 -DdevelopmentVersion=1.0.1-SNAPSHOT -Dtag=release-lab-1.0.0 release:prepare
```

Khi thành công:

1. Preparation goals mặc định/config `clean verify` chạy với POM `1.0.0`.
2. Maven commit release version POM.
3. SCM tag `release-lab-1.0.0` trỏ tới mã nguồn version `1.0.0`.
4. Maven cập nhật working branch sang `1.0.1-SNAPSHOT` và commit.
5. Thông tin thực hiện được lưu trong `release.properties` để perform dùng.
6. Git provider có thể push commits/tags lên local bare remote đã cấu hình (mặc định pushChanges là true trên Git).

Kiểm tra:

```bash
git tag --list "release-lab-*"
git log --oneline --decorate -4
git show release-lab-1.0.0:pom.xml
git show HEAD:pom.xml
git status --short
```

Điểm cần nhìn:

```text
Tagged pom.xml:
  <version>1.0.0</version>

Current branch HEAD pom.xml:
  <version>1.0.1-SNAPSHOT</version>

Artifact repository:
  Chưa có release artifact từ riêng bước prepare
```

Bảng trên là **trạng thái kỳ vọng**, không phải Git/Maven raw log. Nếu Maven release plugin fail giữa chừng, không chạy lại ngay bằng một lệnh có thể tạo commit/tag khác; xem trạng thái SCM, descriptor và mục xử lý lỗi bên dưới.

### 10.1. Chuẩn bị release không phải publish

Sau `release:prepare` thành công, **đừng báo rằng artifact đã available cho consumers** chỉ vì có tag. Tag trong Git là source; JAR/POM phải được build và deploy ở bước perform hoặc một workflow phát hành khác.

Git tag có thể công khai cho người xem source, nhưng không mặc định làm Maven repository có `release-lab-1.0.0.jar`.

## 11. release:perform: checkout tag rồi deploy

Sau prepare thành công, từ **cùng working directory** còn `release.properties`:

```bash
mvn -B release:perform
```

Các bước chính:

1. Plugin đọc descriptor/release tag và SCM connection.
2. Checkout tag `release-lab-1.0.0` vào working directory mặc định của perform, thường `target/checkout`.
3. Fork một Maven instance mới để build project **từ tag**, không từ branch HEAD đã tăng version.
4. Chạy perform goals `deploy` (POM lab đã ghi cụ thể).
5. Default Maven deploy lifecycle đi qua compile, test, package, verify, install rồi upload artifact tới `distributionManagement/repository` đã nằm trong tagged POM.
6. Vì tagged version là release `1.0.0`, Maven Deploy Plugin chọn file repository `lab-releases`.

Đường dẫn sau perform dự kiến:

```text
/tmp/mvn-release-sandbox/artifacts/releases/
    dev/course/release-lab/1.0.0/
        release-lab-1.0.0.jar
        release-lab-1.0.0.pom
        ... metadata/checksum files if emitted ...
```

Trong sandbox này, file repository không có remote credentials; **đây vẫn là một tác vụ deploy do Maven thực hiện**, nhưng chỉ ghi vào filesystem cục bộ.

Kiểm tra:

```bash
find /tmp/mvn-release-sandbox/artifacts/releases -type f
git show release-lab-1.0.0:pom.xml
```

Nếu repository có đúng JAR/POM release và log Maven `Uploading to lab-releases` cho thấy deploy thành công, chứng minh **perform đã dùng tagged release version**.

**Không chạy `java -jar release-lab-1.0.0.jar` và kết luận JAR hỏng**: POM mẫu tạo ordinary JAR không khai báo Main-Class. Muốn chạy demo, dùng classes đã compile của working copy, hoặc kiểm tra artifact contents với `jar tf`.

### 11.1. Làm thế nào xác minh artifact chứa code từ tag?

- Xem Git tag SHA, source và POM release version.
- Kiểm tra SHA/checksum của artifact publish nếu repository xuất thông tin.
- Nếu cần kiểm tra classes, dùng `jar tf` trên JAR đã download ở staging hoặc local file repo.
- Khi muốn replay build, checkout tag ở workspace mới và chạy cùng JDK/Maven/plugin config.
- Không so sánh bytes trong hai builds khác môi trường mà tuyên bố chắc chắn đã reproducible; timestamps/manifest/generated files có thể làm bytes khác dù source giống.

Một workflow release nghiêm túc thường ghi provenance: SCM revision, tag, build run ID, tool versions, artifact GAV, checksums và approvals.

## 12. release:perform mặc định và cấu hình <goals>

Theo tài liệu Maven Release Plugin 3.3.1:

- Khi không có cấu hình site deployment, perform thường chạy `deploy`.
- Nếu project có `distributionManagement/site`, default perform goals có thể là `deploy site-deploy`.
- Trong POM lab, `<goals>deploy</goals>` **ghi rõ chính sách** không triển khai website/site.

Nếu muốn chạy thêm goals:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-release-plugin</artifactId>
    <version>3.3.1</version>
    <configuration>
        <goals>deploy</goals>
        <releaseProfiles>release</releaseProfiles>
    </configuration>
</plugin>
```

Đây là snippet tùy chọn, không phải POM hoàn chỉnh. `releaseProfiles` chỉ có ý nghĩa nếu bạn **đã định nghĩa Maven profile tên release** với cấu hình mong muốn.

**Khác biệt phiên bản quan trọng:** Maven Release Plugin **3.x không tự kích hoạt release profile mặc định theo kiểu từng xảy ra ở 2.x**. Nếu tổ chức có bước ký artifact, source/javadoc JAR, site publish hoặc vulnerability check trong release profile, phải kích hoạt profile rõ ràng và xác minh build hiệu lực. Không đặt `releaseProfiles` theo thói quen mà chưa có profile tương ứng.

Không dùng `-Dgoals=deploy` để vô hiệu hóa required security checks đã được bind trong normal lifecycle; `deploy` vẫn đi qua các phases, nhưng profile/skip flags có thể thay đổi kết quả.

## 13. Chạy trong CI non-interactive và vai trò version inputs

Khi release tự động, Maven cần biết release version, next development version và SCM tag mà không hỏi tương tác:

```bash
mvn -B \
    -DreleaseVersion=1.0.0 \
    -DdevelopmentVersion=1.0.1-SNAPSHOT \
    -Dtag=release-lab-1.0.0 \
    release:prepare
```

Sau đó:

```bash
mvn -B release:perform
```

Nếu SCM/CI policy cho phép, các tham số này làm workflow có thể lặp lại trong cùng cấu hình. Tuy nhiên **lặp lại cùng tag/version trên remote Git hoặc immutable artifact repository không phải lúc nào cũng hợp lệ**. Dùng version chính xác, uniqueness checks, approvals và state reconciliation, không retry mù.

### 13.1. Những tham số nên hiểu

| Parameter/option | Goal | Vai trò |
| --- | --- | --- |
| `-B` | Maven CLI | Batch mode; tránh prompts |
| `releaseVersion` | prepare | Version phát hành sẽ ghi trong POM/tag |
| `developmentVersion` | prepare | Next development version sau release |
| `tag` | prepare | SCM tag name |
| `tagNameFormat` | prepare plugin config | Pattern tên tag với `@{project.version}` |
| `preparationGoals` | prepare | Goals chạy để kiểm tra release POM; mặc định `clean verify` |
| `autoVersionSubmodules` | prepare | Giảm số prompts/đồng bộ version multi-module theo parent |
| `dryRun` | prepare/perform | Preview, không tạo SCM/tag/deploy thật theo goal |
| `resume` | prepare | Tiếp tục một release attempt đã dừng; mặc định true |
| `pushChanges` | prepare (Git) | Có push changes lên upstream hay không; mặc định true |
| `connectionUrl` | perform | Cho SCM URL nếu không lấy được từ descriptor/POM |
| `workingDirectory` | perform | Checkout dir, mặc định `target/checkout` |
| `goals` | perform | Goals dùng trong forked Maven release build |
| `arguments` | forked invocations | Tham số bổ sung cần chuyển xuống Maven build |
| `releaseProfiles` | perform | Profiles bổ sung cho release build, nếu cấu hình |
| `localCheckout` | perform | Local checkout mode trong SCM hỗ trợ, không phải default |
| `maven.repo.local` | Maven | Local artifact cache; không phải release repository đích |

**Lưu ý về Git `pushChanges=false`:** nó có thể giữ tag/commits chỉ trên local repository; một perform thực hiện checkout từ upstream sẽ có nguy cơ **không nhìn thấy tag**. Không tắt pushChanges khi chưa tính rõ SCM URL, remote visibility và execution environment.

### 13.2. Non-interactive không tự giải quyết authentication

- Git SCM push cần credentials/quyền ghi và tag policies.
- Checkout ở perform cần quyền đọc Git tag.
- Maven Deploy Plugin cần quyền ghi artifact repository.
- Những credentials này có thể nằm ở **các hệ thống khác nhau**.
- Không nhúng passwords/tokens vào POM, các lệnh hiển thị trên CI logs hoặc `release.properties`.
- Với Maven repository, `settings.xml/servers/server/id` phải khớp `distributionManagement/repository/id` của tagged POM.
- CI nên dùng bot account/short-lived token với quyền tối thiểu; release tags/branches cần protected policies phù hợp.

Ở sandbox file:// lab, không cần network credentials; đây chỉ là một minh họa lifecycle, **không đánh giá được auth policies của production server**.

## 14. SNAPSHOT dependencies và multi-module release

Một release có external SNAPSHOT dependencies là rủi ro vì nội dung các dependencies có thể thay đổi theo thời gian, khiến cùng release tag build lại ra kết quả khác.

Theo tài liệu, `release:prepare` kiểm tra SNAPSHOT dependencies và thường yêu cầu chúng được xử lý trước release (có các tùy chọn chuyên biệt cho snapshot resolution). Phân biệt:

- **External SNAPSHOT dependencies:** thư viện từ project khác với version mutable. Thường nên chuyển sang release version đã publish trước khi chốt release.
- **Internal modules trong cùng reactor:** có thể cùng `x-SNAPSHOT` trước release; Release Plugin điều chỉnh version chúng theo release transaction của reactor nếu cấu hình tương thích.
- **SNAPSHOT plugin/report/extension deps:** có thể cũng bị kiểm tra theo loại, cần xác nhận policy của plugin version.
- **Timestamped SNAPSHOT:** dù có timestamp cụ thể, vẫn cần cân nhắc tính bất biến, repository retention và policy. Không bật `allowTimestampedSnapshots` để bỏ qua mọi review.

Ví dụ multi-module:

```text
platform-parent 2.0.0-SNAPSHOT
├── platform-api  2.0.0-SNAPSHOT
└── platform-app  2.0.0-SNAPSHOT
         |
         +-- dependency platform-api 2.0.0-SNAPSHOT
```

Prepare của **reactor root** có thể đồng bộ POM parent/modules và internal dependencies sang release version `2.0.0`, rồi next development `2.0.1-SNAPSHOT` theo version inputs/policy.

Để tránh hàng loạt prompts trong reactor dùng chung version:

```bash
mvn -B -DautoVersionSubmodules=true -DreleaseVersion=2.0.0 -DdevelopmentVersion=2.0.1-SNAPSHOT -Dtag=platform-2.0.0 release:prepare
```

**Ví dụ này dành cho một project multi-module khác**, không phải chạy được trực tiếp bằng single-module POM lab. Phải có root aggregator, parent inheritance, SCM và module dependencies đúng.

Khi dùng multi-module:

1. Chạy Release Plugin từ root aggregator theo cấu hình.
2. Xem effective POM và dependency version references giữa modules.
3. Đảm bảo internal modules không trở thành external unresolved SNAPSHOT dependencies sau version transition.
4. Test full reactor ở version release.
5. Tránh partial deploy: một module thành công và module sau thất bại có thể để lại artifact publish không đồng bộ.
6. Nếu cần đảm bảo phát hành theo nhóm, ưu tiên staging repository/promotion policy hoặc công cụ release manager tương ứng.
7. Không cho developer chỉ release một submodule gây khác version lineage nếu cả hệ thống được quản lý theo một release train.

**release:perform không phải transaction atomic.** Ngay cả khi có deployAtEnd ở Deploy Plugin, một loạt upload vẫn có thể bị lỗi giữa chừng và cần staging/cleanup theo chính sách của repository manager.

## 15. Phân biệt SCM <scm> với distributionManagement

Cả prepare và perform có thể cần Git/SCM; chỉ perform theo default goals mới cần artifact deployment.

| Cấu hình | Ai sử dụng | Chức năng |
| --- | --- | --- |
| `<scm><connection>` | SCM read/check | Repo/branch/tag source |
| `<scm><developerConnection>` | SCM write khi cần | Commit/tag/push theo quyền |
| `<scm><tag>HEAD</tag>` | Release SCM metadata | Chỉ dấu development HEAD trước prepare |
| `<distributionManagement><repository>` | Maven Deploy Plugin | Upload release JAR/POM |
| `<distributionManagement><snapshotRepository>` | Maven Deploy Plugin | Upload development SNAPSHOT |
| `<repositories>` | Maven dependency resolver | Download dependencies, không phải upload destination |
| `<pluginRepositories>` | Plugin resolver | Download plugins |
| `settings.xml/servers` | Repository auth | Credentials theo server ID |
| `release.properties` | Maven Release Plugin | Lưu descriptor thông tin SCM/tag/steps |

Maven artifact repository không phải Git repository. Một SCM tag tên `release-lab-1.0.0` được tạo dưới Git remote, không nằm ở `artifacts/releases`; JAR/POM version `1.0.0` được deploy tới artifact repository, không nằm trong Git tag object.

### 15.1. Release repo nên immutable

Trong môi trường thực:

- Release artifact GAV đã publish nên **không được ghi đè**.
- SNAPSHOT repository có thể cho nhiều builds/metadata updates nhưng cần retention và rules.
- Server phải từ chối publishing sai loại artifact (release vs snapshot).
- Bot CI release nên có quyền ghi riêng, không dùng token thường trực trên pull requests không đáng tin.
- Release artifacts có thể cần signing, source/Javadoc JAR, SBOM, scans và provenance tùy yêu cầu.

Maven Release Plugin **không tự bật** tất cả security gates hoặc cryptographic signing. Những bước đó phải được bind vào Maven build/CI/release profiles một cách có kiểm chứng.

## 16. Rollback, clean và resume: không đồng nghĩa nhau

Một release thất bại giữa chừng có thể để lại POM đã sửa, descriptor, tag, SCM commits hoặc artifact đã publish. Cần phân loại lỗi **theo giai đoạn**.

### 16.1. release:rollback

Theo tài liệu Maven Release Plugin 3.3.1, `release:rollback` có thể dùng các POM backups/descriptor để đưa POMs trở lại trạng thái trước release và xử lý rollback các SCM modifications/tags trong phạm vi plugin hỗ trợ.

```bash
mvn release:rollback
```

Nhưng:

- Goal cần state/backup còn tồn tại (không được clean trước).
- Tùy SCM/version/permission, rollback có thể tác động tag/commits; cần **xem kỹ trạng thái SCM và team policy** trước khi chạy trên repository dùng chung.
- Nếu artifact đã deploy lên remote repository, rollback SCM **không tự xóa hoặc thu hồi artifact**.
- Một public release tag đã được tiêu thụ có thể không nên xóa/rewrite tùy ý; đánh giá bằng release governance.
- Không hứa rollback luôn “tự đảo ngược mọi thứ” sau perform.

**Đây không phải nút undo toàn bộ release.**

### 16.2. release:clean

```bash
mvn release:clean
```

Clean dọn temporary release descriptor/POM backup. **Nó không xóa artifacts đã deploy và không revert SCM commits/tags**. Không dùng clean khi đang cần rollback state hoặc perform dựa vào descriptor.

### 16.3. prepare resume

Mặc định prepare có thể **resume** từ phase dừng nếu descriptor còn. Vì thế khi job fail:

1. Xác định phase gần nhất thành công trong log.
2. Kiểm tra Git status, tag/commit đang có và `release.properties`.
3. Xác nhận release artifact chưa bị publish ở repository ngoài ý muốn.
4. Nếu muốn tiếp tục cùng attempt, cân nhắc `mvn release:prepare` theo resume policy.
5. Nếu muốn bắt đầu một attempt hoàn toàn khác, đọc hướng dẫn `-Dresume=false` và xem xét rollback/clean đúng thứ tự.
6. Không chạy lại mù một prepare có thể tạo tag trùng hoặc commit không mong đợi.

Lệnh `-Dresume=false` không phải công tắc xóa mọi tag cũ hay deployed artifact; nó chỉ ảnh hưởng logic resume của Release Plugin. Cần phối hợp với SCM và repository state thực tế.

### 16.4. Phân biệt giai đoạn lỗi

| Lỗi phát sinh | Tình trạng có thể đã xảy ra | Hành động đầu tiên |
| --- | --- | --- |
| Prepare fail ở dirty working tree | Chưa tag/commit release | Commit/stash hoặc sửa source state rồi thử có kiểm soát |
| Prepare fail do SNAPSHOT dependency | Chưa chốt release đúng policy | Chuyển external deps sang released versions |
| Prepare fail ở verify tests | POM đã được biến đổi tạm, chưa tag | Sửa tests/config; kiểm tra backups |
| Prepare fail khi push | Local commits/tag có thể đã có, remote chưa đồng bộ | Kiểm tra cả local/remote refs, tránh duplicate |
| Prepare thành công, perform chưa chạy | SCM tag/next dev commit tồn tại; chưa publish artifact từ perform | Kiểm tra descriptor và quyền checkout/deploy |
| Perform checkout fail | SCM tag không nhìn thấy từ perform environment | Kiểm tra remote, tag, read permissions/connection URL |
| Perform build/test fail | Tag tồn tại, artifact có thể chưa publish | Không sửa trực tiếp tag; tạo release mới sau fix |
| Perform deploy fail giữa upload | Có thể đã publish một phần artifacts | Kiểm tra repository manager và staging/cleanup policy |
| Perform thành công, consumer không tìm thấy | Download repo policy/credentials/GAV sai | Kiểm tra artifact URL, metadata, consumer repositories |
| Release đã publish bị phát hiện lỗi | Bản release bất biến đã có downstream users | Phát hành version sửa lỗi mới/thu hồi theo quy trình |

**Không chạy `git reset --hard`, xóa remote tags hoặc xóa repository artifacts như một bước xử lý mặc định**. Những thao tác này có thể phá dữ liệu/công việc của người khác; trước tiên phải đọc state và thông báo người quản trị release.

## 17. CI pipeline: hai giai đoạn và điều kiện bảo vệ

Một pipeline release đáng tin thường cần hai loại trách nhiệm:

**Prepare job:**

- Chạy trên commit/branch được phê duyệt với Git write permissions thích hợp.
- Kiểm tra working tree sạch, POM version/version policy và required quality gates.
- Ghim SCM tag name, releaseVersion, developmentVersion.
- Có quyền tạo commits/tags; không cấp repository publish token cho các job không cần.
- Lưu descriptor/tag ID/SCM revision để job perform sử dụng, tránh để state local mất giữa CI workers.

**Perform job:**

- Checkout từ release tag đã chốt (không lấy HEAD nhánh phát triển).
- Dùng release build toolchain và repository credentials phù hợp.
- Chạy required tests/static analysis/signing/scans tùy policy.
- Publish tới **staging/release repository** được cấp phép.
- Xác minh remote artifacts và thông tin GAV/checksums.
- Báo release complete sau khi upload/verification thật sự thành công.

Sơ đồ chính sách:

```text
Git approved source + version policy
            |
            v
   prepare (SCM write/tag)
            |
            +-- fail -> stop, reconcile Git state
            |
            +-- pass -> record tag/SHA + descriptor
                         |
                         v
                 perform from SCM tag
                         |
                         +-- tests/quality/security gates
                         +-- deploy to authorized repo
                         +-- verify artifact/provenance
                         |
                         +-- pass -> release complete
                         +-- fail -> reconcile repository state
```

Trên CI thật, hai jobs có thể nằm ở runners khác nhau. Nếu không giữ `release.properties`, perform cần đủ SCM URL/tag parameters để lấy đúng source. Không tuyên bố jobs độc lập hoàn toàn khi descriptor/state chưa được truyền.

### 17.1. Ví dụ command CI, không tự upload production

Ở một môi trường **đã được cấp quyền**, lệnh có thể là:

```bash
mvn -B -ntp clean verify
mvn -B -DdryRun=true -DreleaseVersion=1.0.0 -DdevelopmentVersion=1.0.1-SNAPSHOT -Dtag=release-lab-1.0.0 release:prepare
```

Đây là **preflight**, không SCM tag/deploy thật.

Chỉ sau approval và xác nhận tags/repositories:

```bash
mvn -B -ntp -DreleaseVersion=1.0.0 -DdevelopmentVersion=1.0.1-SNAPSHOT -Dtag=release-lab-1.0.0 release:prepare
mvn -B -ntp release:perform
```

Hai dòng cuối **có side effects thật**: Git commits/tags và artifact deploy. Chúng chỉ được chạy tại sandbox hoặc release pipeline được phê duyệt, tuyệt đối không chạy tự động trong một bài học hay pull request không được tin cậy.

## 18. Những hiểu lầm thường gặp

| Hiểu lầm | Giải thích đúng |
| --- | --- |
| “`release:prepare` đã upload JAR” | Prepare chủ yếu tạo release SCM state; publish mặc định nằm ở perform |
| “`release:perform` build branch HEAD” | Perform checkout **SCM tag**, không lấy next development HEAD |
| “Tag Git và Maven artifact là một” | Tag là SCM ref; artifact là JAR/POM tọa độ GAV |
| “Chạy `mvn deploy` cũng tự tag” | Deploy không tự làm version/SCM release process |
| “Chỉ cần `mvn install` để consumer từ máy khác tải” | Install vào local repo; muốn remote consumer cần deploy/publish |
| “Sau prepare nhánh chính vẫn là release version” | Working branch thường được nâng lên next development `-SNAPSHOT` |
| “`release:clean` rollback SCM” | Clean chỉ xóa temporary local release files |
| “`release:rollback` xóa luôn JAR đã deploy” | Không có rollback artifact repository tự động |
| “Dry-run hoàn toàn không tạo file” | Có thể tạo file preview/temp artifacts trong working directory |
| “Release Plugin tự bật profile release ở bản 3.x” | Phải kiểm tra/đặt releaseProfiles rõ |
| “Cứ gọi lại prepare sau lỗi là an toàn” | Resume/tag/commits có trạng thái; phải kiểm tra trước retry |
| “Test một lần trong prepare là đủ, skip perform” | Perform build từ tag; cần chạy required checks trên code được publish |
| “POM cần biết username/password của Git” | SCM credentials/CI secrets quản lý riêng, không hardcode POM |
| “POM repository URL dùng để clone Git” | SCM URL và distributionManagement URL là hai mục riêng |
| “Git tag đã push nghĩa là Maven Central có artifact” | Repository publication là bước khác |
| “deployAtEnd khiến multi-module publish atomic” | Không có transaction/rollback toàn bộ theo mặc định |
| “Bản release có thể ghi đè cùng version tùy ý” | Nên immutable; dùng version mới và approval |

## 19. Công cụ và lệnh kiểm tra đúng giai đoạn

Trước prepare (không publish):

```bash
git status --short
git branch --show-current
git remote -v
git tag --list
mvn -version
mvn help:effective-pom
mvn clean verify
```

Sau prepare:

```bash
git log --oneline --decorate -5
git tag --list
git show release-lab-1.0.0:pom.xml
git show HEAD:pom.xml
```

Sau perform, kiểm tra local file-based release repo của bài:

```bash
find /tmp/mvn-release-sandbox/artifacts/releases -type f
jar tf /tmp/mvn-release-sandbox/artifacts/releases/dev/course/release-lab/1.0.0/release-lab-1.0.0.jar
```

Nếu chạy trên remote repository thật, dùng repository manager UI/API được cấp phép để xác nhận artifacts, SCM provenance và checksums; không đoán từ `BUILD SUCCESS` nếu deploy goal bị skip hoặc uploads chưa thực hiện đúng URL.

### 19.1. Kiểm tra archive không đồng nghĩa chạy executable JAR

POM ví dụ tạo ordinary JAR, không khai báo `Main-Class`. Vì vậy:

```bash
java -cp target/classes dev.course.App
```

là lệnh chạy chắc chắn phù hợp với project source sau `verify`, in:

```text
RELEASE_LAB: Xin chào, Maven!
```

Còn:

```bash
java -jar target/release-lab-1.0.0-SNAPSHOT.jar
```

không được bảo đảm chạy vì thiếu Main-Class. Khi học release plugin, hãy tách “artifact đã được phát hành đúng” khỏi “artifact đã được đóng executable/fat JAR”. Đó là các cấu hình build khác.

## 20. Hỏi đáp nhanh

**Q1. Có thể bỏ qua prepare và chỉ chạy perform không?**

Có một số cách invoke perform với SCM connection URL/tag tường minh theo plugin docs; nhưng **mặc định perform dựa trên descriptor do prepare tạo**. Nếu bỏ prepare, bạn phải tự bảo đảm tag/release POM đã tồn tại đúng cách và cung cấp SCM info phù hợp. Không coi đây là lối tắt an toàn cho release thông thường.

**Q2. Khi nào chuẩn bị release được coi là thành công?**

Khi plugin hoàn thành các checks, version transformations, preparation goals, SCM commits/tag và trạng thái next development cần thiết. Cần kiểm tra remote visibility nếu pushChanges true.

**Q3. Khi nào perform hoàn tất?**

Khi checkout tag/build/deploy được thực hiện thành công và artifacts ở đúng repository; trong release pipeline nghiêm túc còn có verification/approval sau deploy.

**Q4. Tại sao release version ở tag khác working tree sau prepare?**

Prepare chốt release tag ở version cố định rồi tăng working copy sang version phát triển kế tiếp, giúp team tiếp tục phát triển mà release artifact vẫn truy vết được về tag cũ.

**Q5. Tại sao prepare fail nếu uncommitted changes?**

Vì source chưa rõ ràng để tái lập và tag; mặc định plugin kiểm tra working copy clean. Cần commit/sửa source trước, không tự bypass để “cho qua”.

**Q6. Vì sao external SNAPSHOT dependency thường không được chấp nhận khi release?**

Vì nó có thể thay đổi nội dung sau khi release tag được tạo. Cần thay bằng dependency release ổn định hoặc cơ chế policy/version pinning được kiểm chứng.

**Q7. Multi-module prepare khác gì single module?**

Nó phải đồng bộ versions/POM dependencies giữa các modules và chốt tag cho source reactor nhất quán; sử dụng autoVersionSubmodules khi thích hợp và review effective POM.

**Q8. Có bắt buộc deploy lên Maven Central?**

Không. Release Plugin có thể deploy tới file repository lab, hosted internal repository hoặc staging repository được cấu hình. Central publication là workflow có thêm yêu cầu quyền, chữ ký và policy.

**Q9. Có cần chạy `release:clean` trước mọi perform?**

Không. Clean có thể xóa descriptor mà perform cần. Chỉ dọn khi hiểu state release và không còn cần thông tin đó.

**Q10. Tại sao SCM tag tồn tại nhưng perform vẫn fail?**

Tag có thể chưa push lên remote, SCM URL/credentials sai, code ở tag không build được trên perform runner hoặc artifact repository từ chối deploy. Cần đọc chính xác step fail.

**Q11. Có thể build trực tiếp từ tag bằng Git + Maven mà không dùng Release Plugin không?**

Có, nhưng khi đó pipeline tự chịu trách nhiệm version bump, SCM/tag integrity, release.properties/state, tests, deploy và rollback policy. Plugin là một workflow chuẩn hóa, không phải điều kiện bắt buộc để mọi dự án Maven phát hành.

**Q12. Các lệnh release của bài có an toàn chạy trên project hiện tại không?**

Chỉ các lệnh kiểm tra như `mvn clean verify`/`git status` là không chủ động tạo release. `release:prepare` và `release:perform` **có side effects**; chỉ dùng trên sandbox đã chỉ rõ hoặc pipeline đã được cấp quyền.

## 21. Bài tập thực hành

1. Giải thích tại sao `release:prepare` không đồng nghĩa publish JAR.
2. Với POM version `1.0.0-SNAPSHOT`, dự đoán tagged POM version và next development version.
3. So sánh SCM tag, Maven artifact GAV và `release.properties`.
4. Chạy project Java 17 và xác nhận 3 tests PASS, stdout `RELEASE_LAB: Xin chào, Maven!`.
5. Chuẩn bị bare Git remote của sandbox, commit/push source lần đầu; xác minh working tree clean.
6. Chạy prepare dry-run, liệt kê các POM variants hoặc descriptor do plugin tạo. Có Git release tag thật chưa?
7. Dùng `mvn release:clean` sau dry-run. Vì sao không coi đó là SCM rollback?
8. Chạy prepare thật trong sandbox, tìm Git tag `release-lab-1.0.0`. Tag trỏ đến POM version nào?
9. Kiểm tra current branch HEAD sau prepare, version có còn `1.0.0` không?
10. Trước perform, Maven artifact repository đã chắc có release JAR chưa?
11. Chạy perform trong sandbox, xem `target/checkout` và `artifacts/releases`. Artifact version là gì?
12. Vì sao perform không nên build từ working branch HEAD sau prepare?
13. Xóa thử `release.properties` **chỉ trong sandbox thử nghiệm đã backup**; perform thiếu thông tin gì, có cách explicit SCM URL/tag nào?
14. Giải thích khác biệt của `preparationGoals=clean verify` với `goals=deploy`.
15. Theo tài liệu 3.3.1, khi POM có `distributionManagement/site` thì default perform goals có thể thay đổi ra sao?
16. Tại sao Maven Release Plugin 3.x cần cấu hình releaseProfiles rõ nếu yêu cầu signing/extra release checks?
17. Một external SNAPSHOT dependency có thể gây rủi ro gì cho release reproducibility?
18. `autoVersionSubmodules=true` giúp gì trong multi-module release?
19. Nếu Git push tag fail nhưng local tag đã tồn tại, có nên chạy lại prepare không kiểm tra state?
20. Nếu perform publish được một JAR rồi fail phần còn lại, rollback SCM có thu hồi JAR đó không?
21. So sánh `release:rollback`, `release:clean` và `resume=false`.
22. Khi SCM tag được tạo nhưng artifact repository trả HTTP 403, phần nào đã thành công, phần nào chưa?
23. Vì sao nên có staging/approval/immutability khi release multi-module?
24. Tại sao không hardcode Git hoặc repository credentials vào POM?
25. Nêu checklist tối thiểu để xác nhận một release hoàn tất theo tag, artifact version và repository URL.

## 22. Checklist trước khi release

- [ ] Source đã được review, Git working tree sạch và commit được phê duyệt.
- [ ] SCM URL, developerConnection, branch/tag permissions được xác nhận.
- [ ] Version đang là development SNAPSHOT; releaseVersion và developmentVersion được chọn có chủ đích.
- [ ] Không có external SNAPSHOT dependencies không được policy cho phép.
- [ ] Plugin Maven Release Plugin version được ghim và hiểu hành vi release profiles của phiên bản đó.
- [ ] JDK, Maven, Compiler/Surefire/Deploy Plugin versions được kiểm soát.
- [ ] `mvn clean verify` và các quality/security gates bắt buộc PASS.
- [ ] Artifact repository được cấu hình qua distributionManagement (release hosted/staging URL).
- [ ] SCM auth và Maven repository auth được tách, không hardcode secrets.
- [ ] Dry-run đã được xem và không tạo tag/push không chủ đích.
- [ ] Prepare thật có approval rõ; Git commit/tag/version transitions đúng.
- [ ] release.properties còn sẵn khi perform cần dùng.
- [ ] Perform checkout **đúng SCM tag** và build release source.
- [ ] Perform goals gồm deploy và những kiểm tra/đóng gói cần thiết.
- [ ] Artifact JAR/POM được publish đúng GAV/repository, không bị skip.
- [ ] Release repo enforce immutable versions và version policies.
- [ ] Nếu multi-module, có phương án staging/promotion và partial failure.
- [ ] Checksums/provenance/tag SHA/CI run ID được ghi nhận.
- [ ] Consumer resolution từ release repository được kiểm tra khi cần.
- [ ] Không báo hoàn tất trước khi thực sự xác nhận artifact đã publish.

## 23. Tóm tắt

**`release:prepare` chuẩn bị và đánh dấu phát hành trong SCM:** từ `x-SNAPSHOT` đổi sang version release, chạy validation/test, commit/tag source, rồi chuyển nhánh về next development version.

**`release:perform` phát hành từ đúng SCM tag:** checkout tag vào workspace riêng, chạy Maven build/deploy goals và publish artifact release JAR/POM tới Maven repository đã cấu hình.

Hai bước này là **hai cam kết khác nhau**:

- **Nguồn phát hành được chốt:** tag + release POM + kiểm thử ở prepare.
- **Artifact đã phát hành thực sự:** build từ tag + deploy + xác minh repository ở perform.

Không coi SCM tag là artifact, không coi JAR trong `target/` là đã publish, không coi `release:clean` là rollback toàn bộ và không coi `BUILD SUCCESS` là bằng chứng release đã được approval/provenance đầy đủ.

Trong ví dụ sandbox Java 17, chương trình in chính xác **`RELEASE_LAB: Xin chào, Maven!`**, 3 JUnit tests đi qua lifecycle. Git local bare remote cho phép quan sát release tag mà không đụng source server thật; Maven file repository cho phép quan sát perform publish release mà không upload lên repository doanh nghiệp.

## 24. Tài liệu tham khảo chính thức

- [Apache Maven Release Plugin — Overview](https://maven.apache.org/maven-release/maven-release-plugin/)
- [Apache Maven Release Plugin 3.3.1 — Prepare a Release](https://maven.apache.org/maven-release/maven-release-plugin/usage/prepare-release.html)
- [Apache Maven Release Plugin 3.3.1 — Perform a Release](https://maven.apache.org/maven-release/maven-release-plugin/usage/perform-release.html)
- [Apache Maven Release Plugin 3.3.1 — release:prepare parameters](https://maven.apache.org/maven-release/maven-release-plugin/prepare-mojo.html)
- [Apache Maven Release Plugin 3.3.1 — release:perform parameters](https://maven.apache.org/maven-release/maven-release-plugin/perform-mojo.html)
- [Apache Maven Release Plugin — Rollback a Release](https://maven.apache.org/maven-release/maven-release-plugin/usage/rollback-release.html)
- [Apache Maven Release Plugin — Clean a Release](https://maven.apache.org/maven-release/maven-release-plugin/usage/clean-release.html)
- [Apache Maven Release Plugin — Non-interactive Release](https://maven.apache.org/maven-release/maven-release-plugin/usage/non-interactive-release.html)
- [Apache Maven — Releasing Projects](https://maven.apache.org/guides/mini/guide-releasing.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
