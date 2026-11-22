# Cấu hình SCM và quyền truy cập cần cho quy trình release trong Maven

> Chủ đề thuộc nhóm **Quy trình phát hành** của **Build Tool Maven**. Bài phân biệt khai báo nguồn Git trong POM, quyền **đọc/ghi Git** cho thao tác commit/tag và quyền **publish artifact** lên Maven repository. Các ví dụ phát hành dùng hostnames `example.invalid` (chỉ là mẫu); không chạy lệnh phát hành thật cho đến khi tổ chức cấp quyền và phê duyệt.

## 1. Vì sao release cần nhiều quyền hơn một bản build thông thường?

Một lệnh `mvn clean verify` thường chỉ cần quyền **đọc source đã checkout** và **tải dependencies/plugins**. Nó biên dịch, chạy tests và đóng gói kết quả ở workspace cục bộ.

Ngược lại, một quy trình Maven Release Plugin truyền thống có thể:

1. Kiểm tra Git working tree sạch và không có SNAPSHOT dependencies không được phép.
2. Thay POM từ `1.0.0-SNAPSHOT` thành `1.0.0`.
3. Chạy preparation goals/tests.
4. **Commit** các POM release vào nhánh phát triển.
5. **Tạo Git tag** đại diện cho phiên bản được phát hành.
6. Thay POM trên nhánh phát triển sang `1.0.1-SNAPSHOT` và commit.
7. **Push** những commits/tags lên remote Git (theo cấu hình/provider).
8. Checkout code từ tag đó ở một working directory riêng.
9. Build và **deploy JAR/WAR/POM** vào Maven artifact repository.
10. Có thể deploy thêm site nếu `perform` được cấu hình hoặc POM có site destination.

Do vậy **một tài khoản chỉ có quyền clone** thường **không thể hoàn thành `release:prepare`**. Và một credential có thể push Git **chưa chắc** được phép upload lên Nexus/Artifactory/Maven repository.

```text
                      Source Git repository
                               |
              Git fetch/clone | read permission
                               v
                        CI/workspace
                               |
                   mvn clean verify
                               |
            mvn release:prepare (SCM write)
               |       |       |
               v       v       v
             commit  create   commit next
             release  tag     development
               |       |       |
               +-------+-------+
                       |
                   push to Git
                       |
           mvn release:perform (read tag)
                       |
           checkout tag -> build -> deploy
                                      |
                              Maven repository
                              write credentials
```

**Ba ranh giới riêng** cần xác nhận trước release: (a) quyền **đọc/ghi SCM**, (b) quyền **publish Maven artifacts**, (c) quyền bổ sung như **signing, site publication, staging approval** nếu policy yêu cầu. Không gộp ba việc vào một “token Maven”.

### Hành vi phải nói rõ

- `release:prepare` là một thao tác **thay đổi Git/POM**, không chỉ “kiểm tra”.
- `release:perform` dùng **tag đã chuẩn bị** và thường chạy `deploy` trong checkout mới.
- `mvn deploy` thuộc **default lifecycle**, publish Maven artifacts; không thay thế việc commit/tag Git.
- `release:prepare -DdryRun=true` là cách kiểm tra an toàn hơn trước khi cấp quyền ghi; không phải là một release đã hoàn tất.
- Các lệnh thực hành đầy đủ bên dưới chỉ được dùng với **repository và quyền thuộc tổ chức bạn**, không phải repo của người khác.

## 2. Maven cần khai báo SCM ở đâu?

POM có phần `<scm>` để Maven và các plugin biết project được quản lý bởi VCS nào và tìm source ở đâu.

```xml
<scm>
    <connection>scm:git:https://git.example.invalid/team/release-scm-demo.git</connection>
    <developerConnection>scm:git:git@git.example.invalid:team/release-scm-demo.git</developerConnection>
    <url>https://git.example.invalid/team/release-scm-demo</url>
    <tag>HEAD</tag>
</scm>
```

Các hostnames `git.example.invalid` và paths trên là **placeholder**, không phải Git server hoạt động. Trước khi thực thi release, thay chúng bằng repository thật đã được cho phép.

### Ý nghĩa từng element

| POM element | Vai trò | Điều cần kiểm tra |
| --- | --- | --- |
| `scm.connection` | SCM URL dùng cho truy xuất source (thường đọc), ví dụ Git HTTPS | Đúng repository/path, provider `git`, có quyền fetch |
| `scm.developerConnection` | SCM URL phục vụ tác vụ của developer/release, đặc biệt **commit và tag** | Transport dùng được để push, credential phù hợp, không phải URL read-only |
| `scm.url` | URL website của repository để người dùng xem source | Không phải Git SCM provider URL; không đủ cho commit/tag |
| `scm.tag` | Tên revision/tag được project báo cáo; trong development thường `HEAD` | Release Plugin có thể cập nhật giá trị trong tagged POM để trỏ tag release |

**Maven Release Plugin cần ít nhất `developerConnection` chính xác** cùng với cấu hình plugin/version. `connection` không được dùng thay cho URL write-capable nếu nó chỉ cho phép clone.

### Tại sao có prefix `scm:git:`?

Maven SCM sử dụng mẫu:

```text
scm:<provider-id>:<provider-specific-url>
```

- `scm:git:...`: Git provider dùng Git executable.
- `scm:jgit:...`: JGit provider, triển khai Git bằng Java.
- `scm:svn:...`: SVN provider, có cú pháp URL/quy trình tag khác.

Không dùng URL thuần `https://...git` trong `developerConnection` khi goal cần SCM provider. Maven phải phân biệt **Git URL** với **Maven SCM URL**. Git hỗ trợ thêm `|` làm delimiter khi URL chứa dấu hai chấm gây khó phân tích; xem Maven SCM URL guide.

### Ví dụ Git URL hợp lệ

**HTTPS:**

```text
scm:git:https://git.example.invalid/team/release-scm-demo.git
```

**SSH dạng SCP-like phổ biến:**

```text
scm:git:git@git.example.invalid:team/release-scm-demo.git
```

**SSH URL có scheme:**

```text
scm:git:ssh://git@git.example.invalid/team/release-scm-demo.git
```

Git server thực tế có thể yêu cầu path/port/user khác. Đừng gán thêm dấu hai chấm hoặc slash theo cảm tính. Hãy thử với native `git ls-remote` và `git clone` bằng **URL Git thực** (bỏ prefix `scm:git:`) trước khi đưa vào POM.

## 3. Cấu hình `developerConnection` không tự cấp quyền

Điền đúng URL trong POM chỉ giải quyết **“Maven phải kết nối tới đâu?”**. Quyền thực sự còn phụ thuộc:

- Git identity và credential: **SSH key/agent**, Git credential helper hoặc **HTTPS token**.
- Repository permissions: được đọc, được push nhánh, được **tạo/push tag**.
- Branch policies: protected branch, required pull request approvals, required status checks, signed commits, restrictions với bot/service accounts.
- Tag protection: hạn chế ai được tạo, cập nhật hoặc xóa tags có prefix `v*`.
- Network: DNS, proxy, firewall, SSH port, host key trust, CI runner access.
- Git toolchain: Git executable cài đặt, version phù hợp, `user.name` và `user.email` cho commit.
- CI checkout: không ở trạng thái detached HEAD không phù hợp, không shallow/incomplete history khiến release không tìm được branch/tag, có remote Git hợp lệ.

**Một lần `git clone` thành công chỉ chứng minh quyền đọc.** Nó không chứng minh có thể commit lên protected branch hoặc đẩy `refs/tags/v1.0.0`.

### Phân biệt quyền

| Hành động | Quyền tối thiểu mang tính khái niệm | Ví dụ |
| --- | --- | --- |
| `git fetch`/`clone` | Read repository | CI build PR |
| `git commit` local | Có working tree và Git author config | Sửa POM release trong workspace |
| `git push` branch | Repository write + branch policy cho phép | Release Plugin đẩy commit cập nhật version |
| `git push` tag | Repository write + tag policy cho phép | Phát hành `v1.0.0` |
| Checkout tag trong `perform` | Read repository/tag | Tạo clean checkout để build |
| `mvn deploy` | Quyền publish artifact repository | Upload JAR/POM đến endpoint release |
| `site-deploy` nếu cấu hình | Quyền publish website/docs | Transfer HTML site |
| Signing release | Quyền sử dụng signing key/service | GPG/Sigstore theo policy |

**Không nên cấp quyền admin Git hoặc repository manager chỉ để release.** Một service identity có phạm vi tối thiểu, auditable và được bảo vệ bằng branch/tag rules an toàn hơn.

## 4. Luồng mặc định của Maven Release Plugin

Hai goals chính của Maven Release Plugin **3.3.1**:

### 4.1. `release:prepare` — chuẩn bị và ghi dấu release vào SCM

Trong release tiêu chuẩn, plugin thường:

1. Kiểm tra working tree **không có uncommitted changes**.
2. Kiểm tra SNAPSHOT dependencies theo quy tắc release.
3. Chọn release version và next development version (tương tác hoặc qua batch properties).
4. Biến đổi POMs sang release version, cập nhật SCM tag.
5. Chạy preparation goals, mặc định thường là `clean verify` (theo cấu hình).
6. Commit trạng thái release version.
7. Tạo SCM tag như `v1.0.0` (nếu định dạng tag đã cấu hình).
8. Đổi POMs trên nhánh về next development version `1.0.1-SNAPSHOT`.
9. Commit lại bản phát triển và thực hiện SCM push theo provider/configuration.
10. Lưu thông tin phiên release như `release.properties` để dùng khi `perform`.

```text
Trước prepare:
main -> commit A (pom.xml: 1.0.0-SNAPSHOT)

Sau prepare thành công:
main -> commit B (pom.xml: 1.0.0 release)
         |
         +--- tag v1.0.0
         |
         v
       commit C (pom.xml: 1.0.1-SNAPSHOT)
```

Sơ đồ mô tả logic trên nhánh, không bảo đảm thứ tự SHA/tác vụ giống nhau trong mọi Git SCM provider/version. Chính sách branch protected có thể chặn việc plugin push hai commits dù build/test trên máy local thành công.

### 4.2. `release:perform` — build/publish từ tag

`release:perform` thường:

1. Đọc thông tin tag/SCM từ `release.properties` được tạo bởi `prepare` (hoặc dùng `connectionUrl` và `tag` đã cấp theo cơ chế plugin).
2. Checkout source **tại tag release**, thông thường dưới `target/checkout`.
3. Fork một Maven invocation mới trong checkout đã tạo.
4. Chạy các goals phát hành: thường `deploy`, hoặc thêm `site-deploy` nếu project có site distribution config và không override goals.
5. Upload Maven artifacts/POM tương ứng với release version tới repository.

**Hệ quả về quyền:** `perform` cần **Git read** để checkout tag và **artifact repository write** để upload. Nó không tự sửa branch version như `prepare`, nhưng có thể cần quyền signing/site nếu release goals sử dụng các chức năng đó.

### 4.3. Lý do phải build từ tag, không phải “working tree hiện tại”

Một source tree sau prepare thường đã ở next `-SNAPSHOT`. Nếu lập tức chạy `mvn deploy` ở thư mục đó, bạn có thể publish **snapshot** chứ không phải binary của release tag. `release:perform` checkout đúng tag để tránh nhầm source/revision.

Do đó **tag phải thực sự tồn tại và fetch được** trong environment nơi `perform` chạy. Một local-only tag chưa push có thể làm CI job khác báo `Could not checkout tag`.

### 4.4. `release.properties` và trạng thái bước giữa

`release.properties` là release descriptor cục bộ do plugin tạo, chứa thông tin cần để tiếp tục/perform release. Không mặc nhiên coi đây là một file source cần commit. Khi plugin bị lỗi giữa chừng, nó có thể dùng descriptor để **resume**. Nếu dọn descriptor trước khi phân tích lỗi, có thể làm mất ngữ cảnh để phục hồi.

Các file như `pom.xml.releaseBackup`, `pom.xml.tag`, `pom.xml.next` và `release.properties` có thể xuất hiện tùy phiên plugin/chế độ dry-run. Cần review/snapshot theo quy trình; **không đẩy các file tạm đó lên Git chỉ vì chúng được tạo ở workspace**.

## 5. Ví dụ Maven Java 17 đầy đủ để chuẩn bị release

Dùng một project độc lập tên `release-scm-demo`. **Java code và Maven build có thể chạy ngay** trong project đã tạo; **release thật chưa thể chạy** cho đến khi bạn thay URL placeholder, khởi tạo đúng Git repository và được cấp quyền.

### 5.1. Yêu cầu

- JDK 17+.
- Maven 3.9.x (hoặc phiên bản phù hợp với Maven Release Plugin 3.3.1).
- Git executable đã cài đặt, có thể truy cập từ terminal/CI agent.
- Maven có thể tải plugins/JUnit từ Maven Central hoặc mirror của tổ chức.
- Repository Git thật có quy trình cấp quyền commit/tag.
- Maven repository release/snapshot thật có quyền publish riêng nếu chạy `perform`.
- Không nhét token/password vào file POM hay Git URL.

### 5.2. File tree

```text
release-scm-demo/
├── pom.xml
├── .gitignore
└── src/
    ├── main/java/dev/lesson/release/ReleaseApp.java
    └── test/java/dev/lesson/release/ReleaseAppTest.java
```

### 5.3. `pom.xml` hoàn chỉnh

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>release-scm-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <name>Release SCM Demo</name>
    <description>Java 17 project for studying Maven SCM release permissions</description>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <scm>
        <connection>scm:git:https://git.example.invalid/team/release-scm-demo.git</connection>
        <developerConnection>scm:git:git@git.example.invalid:team/release-scm-demo.git</developerConnection>
        <url>https://git.example.invalid/team/release-scm-demo</url>
        <tag>HEAD</tag>
    </scm>

    <!-- Replace placeholder endpoints only with approved destinations. -->
    <distributionManagement>
        <repository>
            <id>release-artifacts</id>
            <url>https://repo.example.invalid/repository/releases/</url>
        </repository>
        <snapshotRepository>
            <id>snapshot-artifacts</id>
            <url>https://repo.example.invalid/repository/snapshots/</url>
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
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>dev.lesson.release.ReleaseApp</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-release-plugin</artifactId>
                <version>3.3.1</version>
                <configuration>
                    <tagNameFormat>v@{project.version}</tagNameFormat>
                    <preparationGoals>clean verify</preparationGoals>
                    <goals>deploy</goals>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Giải thích các phần release:**

1. `<version>1.0.0-SNAPSHOT</version>` là version phát triển. Release Plugin có thể đề xuất release `1.0.0` và next dev `1.0.1-SNAPSHOT`, nhưng ví dụ sau **truyền rõ** các giá trị để không phụ thuộc phiên policy.
2. `scm.connection` dùng read URL; `scm.developerConnection` dùng SSH write URL. Cả hai đang trỏ host **.invalid**, phải thay trước khi phát hành.
3. `scm.url` dùng hiển thị project source, không thay cho developerConnection.
4. `scm.tag=HEAD` biểu thị trạng thái phát triển; tagged POM khi prepare sẽ được cập nhật phù hợp tag.
5. `distributionManagement.repository.id=release-artifacts` phải khớp `settings.servers.server.id` tương ứng với quyền artifact release upload.
6. `snapshotRepository` có server id khác để tách quyền SNAPSHOT. Đừng cho build release vô tình upload lên snapshots endpoint.
7. Plugin version **3.3.1** được pin, không dùng magic `LATEST` hoặc release plugin version mặc định theo máy.
8. `tagNameFormat=v@{project.version}` sử dụng **`@{...}`**, không phải `${project.version}`. Plugin trì hoãn nội suy cho tới khi biết **release version**. Ví dụ tạo `v1.0.0`.
9. `preparationGoals=clean verify` bảo đảm có bước QA Maven trước khi thay đổi SCM được coi là release-ready.
10. `goals=deploy` làm `perform` chỉ dùng Maven artifact deploy trong ví dụ, tránh tự đưa thêm `site-deploy` ngoài phạm vi.
11. Không có cấu hình GPG signing/staging trong POM: ví dụ học tập **chưa phải release configuration production đầy đủ**.
12. Không có credentials thực trong source.

**Cần thay URLs nhưng không thay các API Java/versions để chạy build local.** Nếu một project công ty có parent POM, module versions hoặc build profiles riêng, cấu hình phải được điều chỉnh theo hệ thống đó.

### 5.4. `src/main/java/dev/lesson/release/ReleaseApp.java`

```java
package dev.lesson.release;

public final class ReleaseApp {

    private ReleaseApp() {
    }

    public static int sum(int a, int b) {
        return Math.addExact(a, b);
    }

    public static void main(String[] args) {
        System.out.println("SCM RELEASE DEMO: 2+3=" + sum(2, 3));
    }
}
```

`Math.addExact` ném `ArithmeticException` nếu `int` addition overflow; đây là một hành vi Java 17 tiêu chuẩn để unit test kiểm tra được.

### 5.5. `src/test/java/dev/lesson/release/ReleaseAppTest.java`

```java
package dev.lesson.release;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ReleaseAppTest {

    @Test
    void addsTwoNumbers() {
        assertEquals(5, ReleaseApp.sum(2, 3));
    }

    @Test
    void rejectsOverflow() {
        assertThrows(
                ArithmeticException.class,
                () -> ReleaseApp.sum(Integer.MAX_VALUE, 1)
        );
    }
}
```

Suite có **hai tests**, không cần network/SCM để thực thi. Đây là ví dụ tối thiểu về quality gate trước release; dự án thật cần coverage theo requirements, security checks, integration tests và governance riêng.

### 5.6. `.gitignore`

```gitignore
target/
release.properties
pom.xml.releaseBackup
pom.xml.tag
pom.xml.next
pom.xml.backup
release-pom.xml
```

Đây là **file .gitignore minh họa**, không phải command. Gitignore phải được commit **trước** khi chạy Release Plugin; nếu các file tạm đã được track trước đó, chỉ thêm vào `.gitignore` không tự bỏ chúng khỏi Git index.

Không ignore `pom.xml` hoặc các Java sources, vì đó là phần release plugin cần commit/tag.

## 6. Build Java local: xác nhận code trước khi chạm SCM

Tại project root:

```bash
mvn -version
java -version
git --version
mvn -B -ntp clean verify
```

Khi dependencies/plugins resolve và tests pass, file đáng chú ý:

```text
target/release-scm-demo-1.0.0-SNAPSHOT.jar
target/surefire-reports/
```

Chạy:

```bash
java -jar target/release-scm-demo-1.0.0-SNAPSHOT.jar
```

**Stdout chính xác của `ReleaseApp.main`:**

```text
SCM RELEASE DEMO: 2+3=5
```

Bạn cũng có thể kiểm tra riêng Java mà không dùng Maven:

```bash
javac --release 17 -d target/manual-classes src/main/java/dev/lesson/release/ReleaseApp.java
java -cp target/manual-classes dev.lesson.release.ReleaseApp
```

Kết quả stdout vẫn là:

```text
SCM RELEASE DEMO: 2+3=5
```

**Cảnh báo về trạng thái:** Java/Maven build pass **không** chứng minh Git write access hoặc Maven repository deploy access. Các quyền này phải kiểm tra riêng với đúng identity được pipeline sử dụng.

## 7. Kiểm tra Git trước release bằng lệnh chỉ đọc

Cần checkout đúng branch/repo đã được phê duyệt. Tại project root:

```bash
git status --porcelain
git branch --show-current
git remote -v
git log -n 3 --oneline
git config --get user.name
git config --get user.email
```

Diễn giải:

- `git status --porcelain` không có dòng nào thường nghĩa là working tree/index sạch. Nếu có thay đổi, phải review/commit hợp lệ trước; không tùy tiện `git reset --hard` để xóa dữ liệu của người khác.
- `git branch --show-current` phải cho biết nhánh hợp lệ. Nếu kết quả rỗng, CI có thể đang checkout **detached HEAD**.
- `git remote -v` cho biết fetch/push URLs. **Kiểm tra URL trước khi chia sẻ log** vì một số môi trường không an toàn nhúng token vào URL.
- `git log` cho thấy commit hiện tại, giúp ghép release với source revision.
- `user.name`/`user.email` phải phù hợp identity được phép ký/commit, theo repo policy.

Kiểm tra remote Git read access (thay URL/remote đúng Git project):

```bash
git ls-remote --heads origin
git ls-remote --tags origin
```

Nếu lệnh thành công, Git có thể truy vấn refs; **chưa chứng minh quyền push**.

### Preflight tag trùng

Trước release version dự kiến `1.0.0`:

```bash
git tag -l v1.0.0
git ls-remote --tags origin refs/tags/v1.0.0
```

Nếu tag đã tồn tại ở local/remote, **không tự xóa hoặc overwrite**. Hãy kiểm tra chủ sở hữu, tag commit, release artifact đã phát hành và version policy. Reusing tag làm mất tính truy vết.

### Kiểm tra quyền write như thế nào cho an toàn?

- Ưu tiên kiểm tra Git hosting **repository permissions, branch rules, tag rules** trong tổ chức.
- Có thể dùng một **repo/branch thử nghiệm được cấp phép**, không thử push vào production branch.
- `git push --dry-run` chỉ kiểm tra một phần client/server interaction, **không đảm bảo một push thực sự sẽ qua branch protection/rules hoặc hooks**.
- Không nhầm quyền tạo PR với quyền push trực tiếp.
- Nếu main branch bắt buộc PR, Release Plugin default strategy có thể không phù hợp; thiết kế workflow release bằng bot/branch đặc biệt hoặc sửa policy có kiểm soát, **không tự tắt bảo vệ branch** để chạy được.

## 8. Dry run của `release:prepare` — có tác dụng gì?

**Bước thử an toàn hơn** sau khi đã commit sạch POM và chỉnh SCM URLs đúng:

```bash
mvn -B -ntp release:prepare -DdryRun=true -DreleaseVersion=1.0.0 -DdevelopmentVersion=1.0.1-SNAPSHOT -Dtag=v1.0.0
```

Theo tài liệu Maven Release Plugin:

- Kiểm tra điều kiện chuẩn bị như status, dependencies theo cấu hình.
- Tính toán release/next development versions và mô phỏng SCM changes.
- Có thể tạo bản POM tạm với hậu tố `.tag`/`.next` để xem trước khác biệt.
- Chạy preparation goals/tests theo cấu hình, có thể tốn thời gian/download dependencies.
- **Không commit/tag thật lên SCM** và không cố ý thay checkout gốc thành trạng thái release.
- Không publish artifact qua `release:perform` khi mới dry-run prepare.

**Dry run không mô phỏng hoàn hảo quyền push remote hoặc quyền upload artifact.** Nó giúp bắt phần lớn lỗi về POM/version/model trước khi cho phép side effects thực.

Sau dry-run, kiểm tra file output tạm/logs với quy trình review; khi cần dọn các file do plugin tạo:

```bash
mvn -B -ntp release:clean
```

Goal `release:clean` dọn working-copy release files; **không** dùng để “quay lui mọi thay đổi đã push lên remote”. Với run thật đã đẩy Git, phải audit và rollback theo đúng trạng thái hiện tại.

### Khi nào dùng `-Dresume=false`?

Nếu lần `prepare` trước bị lỗi, plugin có thể **resume** từ `release.properties`. Nếu muốn chạy quy trình mới từ đầu và đã kiểm tra thật kỹ trạng thái Git/remote, có thể truyền:

```bash
mvn -B -ntp release:prepare -Dresume=false
```

Không dùng câu này như cách xử lý lỗi cơ học. Nếu tag/commit đã được tạo trước đó, bắt đầu lại mà không kiểm tra có thể gây duplicate tag hoặc conflicts. Cần đánh giá bước nào đã hoàn tất trước khi quyết định resume, rollback hoặc thao tác Git thủ công có approval.

## 9. Prepare thật: side effects cần được phê duyệt

**Đoạn lệnh này là tài liệu hướng dẫn, không phải thao tác được thực hiện trong bài học.** Chỉ chạy khi quyền branch/tag đã được kiểm tra và tổ chức phê duyệt:

```bash
mvn -B -ntp release:prepare -DreleaseVersion=1.0.0 -DdevelopmentVersion=1.0.1-SNAPSHOT -Dtag=v1.0.0
```

Lệnh có thể:

- Đổi POMs, chạy `clean verify`.
- Ghi release commit, tag `v1.0.0` và next-development commit.
- Đẩy commits và tag lên Git remote theo provider/config.
- Ghi `release.properties` và các file release tạm.

Trước khi chạy thật, cần trả lời đủ:

1. Repository và branch hiện tại là gì?
2. Có ai khác đang release version này không?
3. Service account có quyền **commit/push branch** và **create/push tag `v1.0.0`** không?
4. Tag có bị chặn bởi protection rules hoặc required signing không?
5. Những changes trong POM làm ảnh hưởng downstream modules/BOM/parent không?
6. Preparation goals/test suite có đủ theo release policy?
7. Chúng ta định **publish artifact ngay sau prepare** hay qua staging/approval?
8. Nếu release fail sau khi tag được tạo, quy trình khôi phục và liên lạc với team là gì?

### Kiểm chứng sau prepare

Chỉ khi prepare đã hoàn tất thành công:

```bash
git status --porcelain
git log -n 4 --oneline
git tag -l v1.0.0
git show v1.0.0:pom.xml
git ls-remote --tags origin refs/tags/v1.0.0
```

Kết quả kỳ vọng về mặt logic:

- Working copy trở về next development version `1.0.1-SNAPSHOT`.
- Tag `v1.0.0` trỏ tới POM có `<version>1.0.0</version>`.
- Remote có tag tương ứng nếu push thành công.
- SCM commits được ghi với identity/metadata đúng theo governance.

Đây là **các điều kiện cần xác minh**, không phải output nguyên văn cố định của mọi Git host/provider.

## 10. Perform thật: Git checkout rồi deploy Maven artifact

Sau khi `prepare` thành công và artifact repository credentials đã sẵn sàng:

```bash
mvn -B -ntp release:perform
```

Trong POM demo, `<goals>deploy</goals>` được đặt tường minh để `perform` không tự gọi site deployment. Plugin sẽ checkout tag rồi fork Maven build và deploy các Maven artifacts.

### Những điều kiện riêng của `perform`

- Git **read access** vào tag, kể cả khi chạy ở worker/runner khác với job prepare.
- Nếu `release.properties` không được chuyển sang job khác, `perform` có thể cần cung cấp `connectionUrl` và tag rõ ràng, hoặc thiết kế publish job checkout tag theo workflow phù hợp. Không giả định file từ laptop tồn tại trên CI runner mới.
- Maven repository URL phải đúng loại **release repository**, không phải snapshot staging URL.
- `settings.xml`/credential store phải chứa token upload tương ứng với `distributionManagement.repository.id`.
- Forked Maven process phải dùng JDK/Maven distribution và profiles phù hợp, có thể truy cập dependencies.
- Có thể cần signing keys/staging credentials nếu project có release profiles/goals bổ sung.
- Không nên dùng `-DskipTests` chỉ để đẩy một release không qua QA.

### Phân biệt hai repository

**Git repository** chứa:

```text
Git branch: main
Git tag:    v1.0.0
Files:      pom.xml, src/main/java/..., src/test/java/...
```

**Maven artifact repository** chứa logic tương tự:

```text
dev/lesson/release-scm-demo/1.0.0/
    release-scm-demo-1.0.0.jar
    release-scm-demo-1.0.0.pom
    ...checksums/metadata tùy repository
```

Một remote Git tag có mặt **không** chứng minh artifact được upload. Một file JAR tại `target/checkout/target` (hoặc workspace) cũng chưa chứng minh consumer download được nó.

### Chính xác goal publish nào được chạy?

Theo tham số Release Plugin 3.3.1, `release:perform` sử dụng `goals`; mặc định thường là `deploy`, hoặc thêm `site-deploy` nếu POM có `distributionManagement.site`, tùy version/config.

Trong POM demo khai **`<goals>deploy</goals>`** để đảm bảo intent publish artifact. Nếu tổ chức muốn site phát hành cùng release, hãy cấu hình cụ thể `goals` và site destination, rồi cấp **site credentials riêng**. Không cấp quyền web hosting cho mọi job chỉ vì Maven repository deploy.

## 11. Hai hệ thống xác thực — Git và Maven artifact repository

### 11.1. Git SCM authentication

Với `developerConnection=scm:git:git@host:...`, Git provider thường sử dụng **native Git + SSH**.

Các thành phần:

- Một private SSH key được cấp cho automation identity (không lưu trong POM/Git).
- SSH agent hoặc Git/SSH client được cấu hình để dùng key đúng.
- Host key trust được quản lý an toàn; không bỏ qua host key verification bằng một flag global thiếu kiểm soát.
- Account/service key được cấp **read/write branch và create tag** theo policy.
- CI runner có network tới Git host, không bị firewall/proxy chặn SSH.
- Git `user.name`/`user.email` phù hợp commit identity.

Với HTTPS, Git executable có thể dùng credential helper/CI token, với scopes tương ứng. **Không nhúng token trong `scm:git:https://user:token@host/...`** — URL có thể lộ qua POM, logs, Git config và process list.

**Cảnh báo quan trọng:** Maven `settings.xml` có `servers` nhưng **Git executable provider không nhất thiết lấy credentials giống Maven Deploy Plugin**. Release Plugin 3.2.0+ có `serverId`/`project.scm.id` để tra SCM credentials trong settings theo provider; tuy nhiên việc credential thực sự được Git/SSH executable dùng như thế nào phụ thuộc provider và environment. Trước production, kiểm tra cơ chế cụ thể (native credential helper/SSH agent hoặc Maven SCM authentication) thay vì mặc định một `<server>` bất kỳ sẽ làm Git push được.

### 11.2. Maven artifact repository authentication

POM đã khai:

```xml
<distributionManagement>
    <repository>
        <id>release-artifacts</id>
        <url>https://repo.example.invalid/repository/releases/</url>
    </repository>
    <snapshotRepository>
        <id>snapshot-artifacts</id>
        <url>https://repo.example.invalid/repository/snapshots/</url>
    </snapshotRepository>
</distributionManagement>
```

`release-artifacts` và `snapshot-artifacts` là **server IDs**. Với Maven Deploy Plugin, credentials của Maven settings được tìm theo **id** khớp, **không** theo hostname tùy ý.

Ví dụ **cấu trúc settings.xml không chứa secrets**:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <servers>
        <server>
            <id>release-artifacts</id>
            <username>ci-release-publisher</username>
        </server>
        <server>
            <id>snapshot-artifacts</id>
            <username>ci-snapshot-publisher</username>
        </server>
    </servers>
</settings>
```

Tệp này **chỉ minh họa ánh xạ id**, không phải cấu hình login hoàn chỉnh. Với repository thật, CI phải cấp password/token an toàn qua cơ chế tổ chức (encrypted settings, CI secret store, short-lived token, credential provider...), và đảm bảo không ghi bí mật vào source hoặc console.

### 11.3. Phân biệt credentials theo mục đích

| Secret/identity | Chỉ dùng ở đâu | Mục tiêu |
| --- | --- | --- |
| Git SSH key/HTTPS credential | `release:prepare` và `perform` Git checkout | Fetch, commit/tag/push theo quyền |
| Maven repository publisher token | Maven `settings.xml` cho `deploy` | Upload JAR/POM tới repository release |
| GPG/signing key | Release-signing execution nếu có | Ký artifacts/tags theo policy |
| Site publishing credential | Site Plugin nếu `site-deploy` được bật | Upload HTML docs |
| CI runner identity | Pipeline orchestration, artifact metadata | Gắn commit/tag, audit/approval |

Đừng tái sử dụng cùng một token toàn quyền cho Git, repository manager, site host và signing nếu policy có thể tách quyền.

## 12. `project.scm.id` và việc tra SCM credentials trong Release Plugin

Một tình huống nâng cao: Release Plugin hỗ trợ tham số `serverId` (since 3.2.0), user property `project.scm.id`, để chọn `<server>` trong Maven settings. Nếu không đặt, plugin có logic suy server id từ SCM host/port.

Ví dụ cú pháp **khái niệm**:

```bash
mvn -B -ntp -Dproject.scm.id=git-release-credentials release:prepare -DdryRun=true
```

Điều này **không tự tạo credentials**. Bạn vẫn cần cấu hình `settings.xml` có server id tương ứng, và cần kiểm tra phương thức SCM provider sử dụng credentials. Với Git executable/SSH, nhiều hệ thống thực tế dựa vào `ssh-agent` hoặc Git credential helper thay vì tin rằng mọi provider sẽ lấy password từ Maven settings.

**Không đẩy `-Dpassword=...` trong logs hoặc shell history.** Nếu dùng HTTPS token, ưu tiên native CI credential integration và hạn chế thời gian tồn tại/permissions. Không trình bày cách vô hiệu hóa security hooks/branch protection như biện pháp thông thường.

## 13. CI: vì sao protected branch/tag làm `prepare` fail?

Một cấu hình Git server phổ biến:

- Nhánh `main` yêu cầu Pull Request và 2 reviewers, cấm direct push kể cả từ developer.
- Tags `v*` chỉ release bot hoặc người quản trị được phép tạo.
- Commits cần chữ ký hoặc status checks trước khi được chấp nhận.
- Service account chỉ có quyền `contents:read` nếu CI chạy trên PR.

`release:prepare` theo strategy truyền thống muốn **commit trực tiếp vào branch** và tạo tag. Khi branch không cho direct push, plugin có thể fail ở bước SCM push mặc dù POM/test đều đúng.

**Không kết luận “chỉ thiếu username/password”.** Cần kiểm tra policy trong Git host. Cách xử lý phù hợp có thể là:

1. Sử dụng **release bot** được cấp quyền rõ ràng và được giám sát; có exception/policy định nghĩa trước, không tắt bảo vệ toàn repository.
2. Đổi workflow sang **PR-based version bumps**: người hoặc bot tạo PR cập nhật release/next version, sau approvals mới gắn tag; không dùng `release:prepare` mặc định nếu nó mâu thuẫn governance.
3. Dùng **tag-driven release pipeline** được tổ chức kiểm soát, build từ immutable tag rồi publish artifacts sau approval, thay vì yêu cầu plugin commit vào branch.
4. Tách task chuẩn bị version khỏi Git tag creation nếu policy đòi chữ ký/approval độc lập.
5. Thử mọi quyền trên sandbox repository/branch được phép trước.

**Điều quan trọng:** Plugin là công cụ tự động hóa nhưng **không được quyền vượt Git permissions/hook policies**. Nếu tổ chức cấm direct push vào main, cần thiết kế release flow tôn trọng điều đó.

### CI checkout đặc biệt

Hầu hết CI checkout PR/commit SHA với **detached HEAD**, có thể fetch depth=1 hoặc không fetch tags. Release Plugin lại cần biết nhánh để push commits và xác định tag/version.

Preflight:

```bash
git status --porcelain
git branch --show-current
git remote -v
git fetch --tags
git tag -l v1.0.0
```

`git fetch --tags` đọc Git remote và làm thay đổi local refs; chỉ thực hiện khi repo/runner đó là workspace được phép. Nó **không push** hay tạo remote release nhưng có thể cần authentication. Với Git hosts/CI khác nhau, cách tạo non-detached checkout và fetch history sẽ khác; cấu hình trên đúng nền tảng.

**Không thiết kế release trong untrusted pull request có quyền deploy.** PR có thể sửa POM/plugins, khiến job có secrets chạy code không tin cậy.

## 14. Kịch bản CI an toàn theo hai mức quyền

### Job A — verify / dry-run (không có quyền publish)

```text
Trigger: Pull Request hoặc trusted branch
Credentials:
    - Git read-only
    - Maven dependency download permissions
Actions:
    - checkout commit
    - mvn -B -ntp clean verify
    - kiểm tra POM/SCM config, reports
    - optional release:prepare -DdryRun=true trên trusted branch
Outputs:
    - build/test reports
    - review comments, proposed versions/tags
Forbidden:
    - release:prepare thật
    - release:perform thật
    - git push/tag
    - remote artifact deploy
```

Nếu `dryRun` vẫn cần Git provider đọc một private repo, cung cấp read-only credential. Đừng cấp production repository publisher token cho job này.

### Job B — release (sau approval)

```text
Trigger: Protected tag hoặc release approval từ trusted branch
Credentials:
    - Git identity được phép tạo/push tag và (nếu prepare) branch commits
    - Artifact repository publisher token
    - Signing key nếu policy yêu cầu
Actions:
    - checkout full history / correct branch
    - xác minh clean tree, no duplicate version/tag
    - mvn release:prepare (nếu workflow dùng Release Plugin prepare)
    - kiểm tra remote tag/SCM commits
    - mvn release:perform hoặc publish-from-tag được phê duyệt
    - kiểm tra artifact repository và consumer resolution
Outputs:
    - Git tag + commit SHA
    - Release artifact GAV/checksums
    - CI build id, audit trail, signer/approver
Forbidden:
    - tự sửa protected branch policy
    - publish từ unreviewed PR
    - ghi secrets vào POM/logs
```

**Pseudo-workflow này chỉ mô tả các bước và quyền**; không phải YAML hoàn chỉnh của một CI provider. Đừng ghép copy/paste vào GitHub Actions/GitLab/Jenkins nếu chưa kiểm tra rule, syntax, secrets và checkout mechanism tương ứng.

### Tránh quyền write trong job chạy code không đáng tin

Maven lifecycle/plugin executions có thể chạy mã trong quá trình build/test. Nếu job chạy source/POM từ PR chưa review với publisher token trong environment, có nguy cơ lộ secrets. Nên phân tách jobs/agents và bảo vệ release secret bằng environment approvals/branch restrictions/credential scoping.

## 15. Multi-module release và version coordination

Một reactor Maven:

```text
platform-parent/
├── pom.xml               # parent + aggregator
├── api/pom.xml
└── cli/pom.xml
```

Nếu tất cả modules cùng version, Release Plugin có thể được cấu hình `autoVersionSubmodules=true` để tránh nhập từng version lẻ. Trong Maven Release Plugin:

```xml
<configuration>
    <autoVersionSubmodules>true</autoVersionSubmodules>
    <tagNameFormat>v@{project.version}</tagNameFormat>
</configuration>
```

Đây là **plugin configuration fragment** đặt vào Maven Release Plugin trong POM parent, không phải file POM đầy đủ.

Các lưu ý:

- `release:prepare` thường chạy ở reactor root/aggregator.
- Parent, child modules và intra-reactor dependencies có thể cần cập nhật versions đồng bộ.
- Nếu BOM, parent POM hoặc dependency management dùng các chính sách version khác nhau, phải review generated release POMs trước khi commit.
- Với non-interactive release có nhiều versions riêng, tài liệu Maven hỗ trợ properties dạng `project.rel.<groupId>:<artifactId>` và `project.dev.<groupId>:<artifactId>`; thường phải quote chúng đúng shell syntax.
- CI-friendly versions (`${revision}`, `${sha1}`, `${changelist}`) có các quy tắc riêng; không giả định plugin release prepare truyền thống và Flatten Plugin tự động phối hợp đúng trong mọi POM. Kiểm thử trên sandbox trước khi đổi project dùng CI-friendly.
- `release:perform` checkout toàn bộ tag, vì vậy mọi module và external parent/BOM/dependencies phải resolve trong **clean checkout**, không lệ thuộc artifact chỉ tồn tại ở local repository trên máy developer.

### Tag naming và tính bất biến

Nếu dùng `v1.0.0`, hãy quy định rõ:

- Prefix/case/version format, không tạo cả `release-1.0.0` và `v1.0.0` lẫn lộn.
- Tag được tạo một lần, không force-push khi artifact đã publish.
- Tag phải trỏ đúng release commit/SHA và có audit record.
- Protected tags, signed tags nếu policy yêu cầu.
- Repository release phải không cho overwrite cùng version.

Tag **không phải artifact**. Kiểm tra đồng thời Git tag SHA và Maven artifact checksum/provenance để có khả năng truy vết nguồn phát hành.

## 16. Lỗi hay gặp và cách phân biệt nguồn lỗi

| Triệu chứng | Nguyên nhân thường gặp | Cách chẩn đoán/khắc phục |
| --- | --- | --- |
| `No SCM URL was provided` | Thiếu `developerConnection`, SCM URL sai | Kiểm tra `<scm>` trong effective POM |
| `No such SCM provider` | URL thiếu `scm:git:` hoặc provider không hỗ trợ | Xem Maven SCM URL syntax/provider |
| `git clone` được nhưng `release:prepare` không push được | Có quyền đọc nhưng không có branch/tag write | Xem Git hosting permissions và branch/tag rules |
| `Permission denied (publickey)` | SSH key/agent/known_hosts sai hoặc account thiếu quyền | Kiểm tra SSH identity và host key trust |
| `Authentication failed` với HTTPS | Token sai/hết hạn/scope thiếu, credential helper sai | Kiểm tra CI secret mapping và token scope |
| `protected branch hook declined` | Git host chặn direct push | Thiết kế PR/release-bot workflow có approval |
| `tag v1.0.0 already exists` | Version/tag đã được tạo | Không xóa mù; audit existing tag/artifact/version |
| `Working copy has modifications` | File đã sửa/chưa commit, generated files tracked | `git status --porcelain`; review/commit hoặc clean hợp lệ |
| `Cannot prepare ... SNAPSHOT dependency` | External SNAPSHOT dependency chưa xử lý theo policy | Chọn dependency release/approved version |
| `Git author identity unknown` | Thiếu `user.name`/`user.email` | Cấu hình CI release bot identity phù hợp |
| `release:prepare` pass local, CI perform không checkout tag | Tag chỉ local/chưa push, wrong remote/auth, shallow fetch | Kiểm tra remote tag bằng `git ls-remote` |
| `release:perform` lỗi dù prepare đã pass | Thiếu repository deploy credentials hoặc clean checkout resolve lỗi | Xem deploy server ID, forked Maven logs, dependencies |
| `401 Unauthorized` khi deploy | Credentials trong settings sai/expired | Khớp `distributionManagement.repository.id` với `settings.servers` |
| `403 Forbidden` khi deploy | Account không có quyền publish hoặc repository policy cấm | Kiểm tra ACL/version immutability |
| `release:perform` dùng wrong Maven/JDK | Forked invocation khác environment | Pin toolchain/Maven Wrapper, xem runtime logs |
| `release:perform` tự chạy site-deploy | POM có site distribution và goals default | Khai explicit `<goals>deploy</goals>` nếu không muốn publish site |
| `release:rollback` không xóa remote tag | Rollback có giới hạn và remote state | Audit state, theo approved remediation thay vì giả định revert toàn bộ |
| `mvn deploy` phát hành SNAPSHOT thay vì release | Chạy từ next-development working tree, không checkout tag | Dùng perform/tag checkout và kiểm tra project.version |
| `release.properties` bất ngờ trong git status | File tạm không ignore, hoặc tracked | Điều chỉnh .gitignore phù hợp, không commit secrets |
| Git remote URL lộ token trong logs | Token nhúng vào URL | Rotate/revoke token và chuyển sang credential helper |
| CI chạy PR có publisher secret | Scope secrets không tách trust boundary | Restrict trusted branches/environments và access |

### Lệnh debug không làm Git remote thay đổi

```bash
mvn help:effective-pom
mvn -B -ntp clean verify
git status --porcelain
git branch --show-current
git remote -v
git ls-remote --tags origin
```

`git ls-remote` truy vấn remote nhưng không push. `mvn help:effective-pom` giúp xem SCM URL, plugin version và distributionManagement. Trước khi chia sẻ log, **redact repository internal hostnames, URLs nhúng token và secret environment values**.

Khi cần biết mục tiêu và tham số goal:

```bash
mvn -B -ntp release:help -Ddetail=true -Dgoal=prepare
mvn -B -ntp release:help -Ddetail=true -Dgoal=perform
```

Không debug bằng `mvn -X release:prepare` thật trên protected branch nếu chưa phê duyệt; goal đó **có thể tạo Git commits/tags** dù bạn chỉ muốn xem log. Với quyền hạn an toàn, dùng `-DdryRun=true` trước.

## 17. Phục hồi lỗi: rollback không phải nút “Undo” toàn hệ thống

### 17.1. Lỗi trước commit/tag

Nếu `prepare` fail sớm khi working tree dirty hoặc no SCM URL, chưa chắc remote có thay đổi. Xem logs và `git status`. Có thể sửa cấu hình rồi dry-run lại sau review.

### 17.2. Lỗi sau release commit/tag nhưng trước next-dev commit

Remote có thể đã nhận một phần commits hoặc tag. Trước khi thực hiện thao tác khác:

```bash
git status --porcelain
git log -n 5 --oneline
git tag -l v1.0.0
git ls-remote --tags origin refs/tags/v1.0.0
```

Không chạy lại prepare mù, không force-push/delete remote tag nếu chưa biết ai đang dùng. `release:rollback` có thể revert một số thay đổi từ lần prepare nhưng **không bảo đảm xóa artifacts đã upload hoặc hoàn tác mọi remote side effect**; quy trình chính thức cần review cụ thể theo plugin/provider state.

### 17.3. Lỗi sau upload artifact

Một release JAR/POM đã publish có thể bị mirror/CDN/consumer cache. Không xem “xóa Git tag” là rollback artifact. Với repository release bất biến, thường cần **phát hành version sửa mới** hoặc thực hiện repository administrator-approved recovery, không ghi đè `1.0.0` bằng bytes khác.

### 17.4. Vai trò của `release:clean`

`release:clean` dọn các file tạm liên quan release trong working copy; nó **không tự xóa/undo mọi Git tag, commits hoặc remote Maven repository uploads**. Đừng nhầm nó với Maven lifecycle `clean` (xóa `target`) hay với `release:rollback`.

## 18. Một checklist quyền đầy đủ trước production release

- [ ] Project đã build `mvn clean verify` với JDK/Maven được policy cho phép.
- [ ] Working tree/index sạch, không có generated files tracked bất ngờ.
- [ ] Source commit/branch đúng, không detached HEAD không được xử lý.
- [ ] Remote `origin` và `scm.developerConnection` trỏ tới **cùng repository được phê duyệt**.
- [ ] `<scm>` có provider prefix hợp lệ `scm:git:`.
- [ ] `connection` read path, `developerConnection` write path rõ ràng.
- [ ] Git identity/SSH agent/credential helper được cấp qua CI secrets, không trong POM.
- [ ] CI bot có quyền read, push branch commits và create/push protected tags theo policy.
- [ ] Đã kiểm tra branch protection, tag protection và required approvals.
- [ ] Tag/version chưa tồn tại trong Git và repository release.
- [ ] Đã xác định releaseVersion, developmentVersion, tagNameFormat nhất quán.
- [ ] Release Plugin pinned version, kiểm tra `release:help` trên đúng plugin.
- [ ] `release:prepare -DdryRun=true` được thực hiện trong môi trường phù hợp trước lần release đầu.
- [ ] Preparation goals/tests thực sự chạy, không `-DskipTests` ngoài phê duyệt.
- [ ] Repository `distributionManagement.repository.id` đúng với Maven `settings.xml` server id.
- [ ] Release repository token có quyền upload tối thiểu và không dùng credential SNAPSHOT để publish release.
- [ ] Nếu có site/goals khác, đã cấp và review quyền riêng.
- [ ] `release:perform` checkout tag fetch được từ remote; không lệ thuộc local-only tag.
- [ ] Toolchain và Maven profiles trong checkout forked phù hợp.
- [ ] CI chỉ cấp secrets cho trusted release jobs, không để PR tùy ý chạy code với secrets.
- [ ] Có kế hoạch fail/retry/rollback cụ thể, không force-push hoặc xóa release tùy tiện.
- [ ] Sau prepare đã kiểm tra Git commit/tag và POM tagged version.
- [ ] Sau perform đã kiểm tra Maven artifact GAV/POM/checksums/consumer resolution.
- [ ] Release có audit record: Git SHA, tag, CI run, approver, package versions, signatures nếu yêu cầu.

**Điểm mấu chốt:** Release Plugin xử lý **quy trình**, còn Git server và artifact repository **quyết định quyền**. Một release đúng phải vừa ghi được tag/commits theo chính sách SCM, vừa xuất bản đúng artifacts từ tag ở repository đích, chứ không chỉ có dòng `BUILD SUCCESS`.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** `mvn clean verify` thành công có chứng minh `release:prepare` sẽ push Git thành công?

**Đáp án:** Không. Build thường không cần branch/tag write; prepare có side effects lên SCM và phải chịu branch/tag policy.

**Câu 2.** `scm.connection` và `scm.developerConnection` khác nhau gì?

**Đáp án:** Connection là SCM URL cho truy cập source (thường đọc). DeveloperConnection cần dùng được cho developer/release operations, đặc biệt commit/tag; không chỉ là web URL.

**Câu 3.** `<url>https://git.example.invalid/team/repo</url>` trong `scm` có đủ để Maven biết dùng Git provider không?

**Đáp án:** Không. Release Plugin cần SCM URL dạng `scm:git:...` trong `developerConnection`; `scm.url` chủ yếu để hiển thị.

**Câu 4.** Release Plugin có tự tạo Git credentials từ `pom.xml` không?

**Đáp án:** Không. Credentials/identity và quyền remote phải được cấp riêng qua SSH/Git/Maven SCM mechanisms phù hợp.

**Câu 5.** Vì sao có thể `git clone` được nhưng bị `protected branch hook declined`?

**Đáp án:** Clone cần quyền read, còn direct push/tag chịu branch/tag protections và write authorization.

**Câu 6.** `release:prepare` và `release:perform` khác nhau ra sao?

**Đáp án:** Prepare chuẩn bị versions/SCM commits/tag; perform checkout tag và chạy build/publish Maven artifacts. Chúng có các điều kiện quyền khác nhau.

**Câu 7.** Nếu `release:perform` thiếu `release.properties` trong CI runner mới thì phải làm sao?

**Đáp án:** Cần truyền release descriptor từ job prepare hoặc cung cấp SCM URL/tag theo tham số goal và kiểm tra đúng release commit. Không giả định file local của job trước luôn có mặt.

**Câu 8.** Artifact deploy gặp 401. Sửa `<scm><developerConnection>` có phải cách đúng?

**Đáp án:** Thường không. Kiểm tra `distributionManagement.repository.id` với `settings.xml`, token/ACL của Maven artifact repository.

**Câu 9.** Git tag `v1.0.0` có nghĩa release `1.0.0` đã upload lên Maven repository?

**Đáp án:** Không. Tag là SCM reference; phải xác minh `release:perform`/`deploy` và repository artifact.

**Câu 10.** `release:prepare -DdryRun=true` có thể kiểm tra chắc chắn quyền push Git không?

**Đáp án:** Không. Dry-run mô phỏng SCM changes và kiểm thử POM/version; branch/tag permissions chỉ được xác minh bằng policy hoặc hành động được cấp quyền.

**Câu 11.** Khi main branch cấm direct push, có nên tắt protection để plugin chạy không?

**Đáp án:** Không. Hãy thiết kế release bot exception được phê duyệt hoặc PR/tag-driven workflow đúng governance.

**Câu 12.** `release:rollback` có tự xóa Maven artifact `1.0.0` đã được publish và revoke tag trên mọi mirror không?

**Đáp án:** Không thể mặc định như vậy. Rollback có giới hạn; cần audit Git/repository state và xử lý theo release/repository policy.

## 20. Kết luận và tài liệu chính thức

**Cấu hình SCM cho release có hai lớp:** (1) POM mô tả Git source/release destination thông qua `<scm>`, đặc biệt `developerConnection`; (2) Git server/CI thực sự cấp **identity và quyền commit/push/tag**. Để xuất bản artifacts cần **lớp thứ ba**, `distributionManagement` và repository publisher credential theo `settings.xml`. `release:prepare` làm việc với versions, Git commits và tag; `release:perform` checkout tag rồi chạy Maven deploy. Không gộp chúng thành một quyền, không đưa secrets vào POM và không mặc định release thành công cho đến khi **Git tag lẫn artifact repository** đều được đối chiếu.

### Tài liệu tham khảo

- [Apache Maven Release Plugin 3.3.1 — Usage](https://maven.apache.org/maven-release/maven-release-plugin/usage.html)
- [Apache Maven Release Plugin — Prepare a Release](https://maven.apache.org/maven-release/maven-release-plugin/usage/prepare-release.html)
- [Apache Maven Release Plugin — Perform a Release](https://maven.apache.org/maven-release/maven-release-plugin/usage/perform-release.html)
- [Apache Maven Release Plugin — Non-interactive Release](https://maven.apache.org/maven-release/maven-release-plugin/usage/non-interactive-release.html)
- [Apache Maven Release Plugin — release:prepare Parameters](https://maven.apache.org/maven-release/maven-release-plugin/prepare-mojo.html)
- [Apache Maven Release Plugin — release:perform Parameters](https://maven.apache.org/maven-release/maven-release-plugin/perform-mojo.html)
- [Apache Maven — SCM URLs](https://maven.apache.org/pom-scm-urls.html)
- [Apache Maven — Release Guide](https://maven.apache.org/guides/mini/guide-releasing.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven Deploy Plugin — Usage](https://maven.apache.org/plugins/maven-deploy-plugin/usage.html)

*Ví dụ Java/POM được viết cho JDK 17 và Maven Release Plugin 3.3.1. Các địa chỉ `example.invalid` và tài khoản trong settings là ví dụ không hoạt động; bài không thực hiện bất kỳ Git commit/tag/push hoặc artifact deployment thực tế nào. Khi áp dụng vào repository thật, phải đối chiếu plugin version, SCM provider, branch/tag protection, secrets và repository permissions của chính môi trường đó.*
