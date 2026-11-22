# Xử lý release thất bại hoặc phát hành lại với phiên bản mới trong Maven

## 1. Đặt vấn đề: release thất bại ở bước nào?

Bạn đang phát hành thư viện Java:

```text
com.example.training:release-recovery-lab:1.4.0
```

Maven đã tạo Git tag `release-recovery-lab-1.4.0`, nhưng `release:perform` báo lỗi khi upload. Một đồng nghiệp đề xuất “chạy lại release từ đầu”, người khác đề xuất “rollback”, người thứ ba muốn đổi version thành `1.4.1`. Phương án nào đúng?

**Không thể quyết định chỉ dựa vào dòng `BUILD FAILURE`.** Phải xác định ba lớp trạng thái độc lập:

1. **SCM/Git:** release commit và tag đã được tạo/push chưa? Tag trỏ commit nào? Đã được downstream tham chiếu chưa?
2. **Build:** test/package của phiên bản release đã chạy chưa? `release:perform` đã checkout tag vào `target/checkout` chưa?
3. **Artifact repository:** chưa upload, đã upload một phần, đang staging, hay đã publish? Có module nào được công bố trước khi job lỗi?

Một command Maven thất bại **không có nghĩa mọi side effect đều được hoàn tác**. Release Plugin **không tạo một transaction nguyên tử trải dài Git, CI, staging, Maven Central và deployment production**. Khi release version đã xuất hiện công khai, cách khắc phục thường là **đưa code sửa vào version mới** chứ không thay artifact cùng tọa độ.

Bài này sử dụng **Apache Maven Release Plugin 3.3.1**, Maven **3.9.x**, Java **17+**, Git và một ví dụ JUnit 5 hoàn chỉnh. Trọng tâm là xử lý lỗi thực tế với `release:prepare`, `release:perform`, `release:rollback`, `release:clean`, `-Dresume` và quy trình phát hành bản thay thế.

### Sau bài học, bạn có thể

- Giải thích các phases của Maven Release Plugin và các file/commit/tag được tạo.
- Phân biệt resume, retry, rollback, clean và bắt đầu attempt mới.
- Điều tra lỗi trước tag, sau tag, trong perform hoặc ở staging/public repository.
- Hiểu tại sao Git tag, Maven GAV và bytes artifact cần bất biến.
- Chọn version mới khi artifact cũ đã published, kể cả nếu release đầu tiên có lỗi.
- Đọc trạng thái qua Git, release.properties, build logs và repository portal.
- Biên dịch/test project Java 17 thật với Maven 3.9/JUnit 5.
- Thực hiện dry-run an toàn trước khi thao tác vào SCM.
- Kiểm soát CI retry, multi-module, credentials, signatures và approvals.
- Tránh những lệnh xóa tag/commit hoặc redeploy khiến release khó audit.

## 2. Maven Release Plugin: prepare và perform là hai giai đoạn khác nhau

### 2.1. release:prepare

Maven Release Plugin chuẩn bị phiên bản phát hành và nguồn SCM. Với source đang có:

```xml
<version>1.4.0-SNAPSHOT</version>
```

quy trình điển hình:

```text
Working copy version 1.4.0-SNAPSHOT
   |
   v
Kiểm tra Git clean, project/dependency SNAPSHOT
   |
   v
Chuyển POM thành release version 1.4.0
   |
   v
Chạy preparation goals (mặc định clean verify)
   |
   v
Commit release-version POM
   |
   v
Tạo Git tag release-recovery-lab-1.4.0
   |
   v
Đổi development POM sang 1.4.1-SNAPSHOT
   |
   v
Commit development-version POM
```

Thứ tự gồm việc sửa metadata SCM, chạy goals, commit, tag và tăng development version. **Bất kỳ bước nào cũng có thể fail**, do đó khi `prepare` dừng ở giữa, Git có thể đã nhận một hoặc nhiều commits/tags. Không kết luận tag vắng mặt chỉ từ `BUILD FAILURE`.

`release:prepare` không có nhiệm vụ upload release JAR lên Maven Central. Tồn tại một Git tag `1.4.0` chỉ chứng minh source được đánh dấu, **chưa chứng minh artifact đã published**.

### 2.2. release:perform

`release:perform` thường:
1. Đọc release descriptor `release.properties` để biết SCM connection/tag.
2. Checkout source **từ Git tag**, mặc định vào `target/checkout`.
3. Fork một Maven process và chạy perform goals.
4. Với release production, goals thường là `deploy` hoặc `deploy site-deploy` nếu website deployment đã được cấu hình.
5. Upload, staging hoặc publish qua repository tương ứng.

**Điểm dễ nhầm:** sau `prepare`, development branch đã tiến đến `1.4.1-SNAPSHOT`; `perform` vẫn xây source `1.4.0` từ **tag**, không xây những thay đổi mới trên main. Sửa bug trên main rồi chỉ chạy lại perform **không tự đưa bug fix vào release đã tag**.

### 2.3. release:rollback và release:clean

| Goal | Mục đích | Giới hạn |
| --- | --- | --- |
| `release:prepare` | Chuẩn bị POM, SCM commit/tag, next development version | Không tự chứng minh đã deploy artifact |
| `release:perform` | Checkout tagged source và build/deploy | Không tự rollback remote khi upload giữa chừng |
| `release:rollback` | Khôi phục thay đổi POM/SCM của prepare dựa trên descriptor/backups | Không gỡ artifact đã published |
| `release:clean` | Xóa descriptor và POM backup trong working copy | Không hoàn tác Git tag/commit hay Maven repository |
| `release:update-versions` | Cập nhật version của POMs | Không biến published release thành bản mới |

Tài liệu rollback phiên bản 3.3.1 cho biết nó có thể xóa tag/branch do prepare tạo (tính năng có từ 3.0.0-M1) **khi SCM provider và quyền cho phép**. Trên Git có protected tags, code review và server hooks, bước đó có thể không thành công. **Không dùng rollback như cách xóa release đã công bố.**

### 2.4. Các dấu vết cần giữ lại

Một lần prepare có thể tạo các dữ liệu sau:
- `release.properties`: release descriptor chứa tham số/phase status giúp resume hoặc perform.
- `pom.xml.releaseBackup` ở root và các POM modules.
- `pom.xml.tag`, `pom.xml.next` hoặc các file dự thảo trong dry-run.
- Git commits cho POM release version và next development version.
- Git tag local, sau đó có thể có Git tag remote.
- Log kiểm thử, CI job ID và source SHA.
- `target/checkout` khi perform.

**Không xóa thủ công hoặc commit các file release state trước khi phân loại lỗi.** Dữ liệu backup/descriptor có thể là điều kiện để rollback. Nếu chúng đã bị `release:clean` xóa thì rollback không còn đủ thông tin theo cách thông thường.

## 3. Ma trận quyết định trước khi khôi phục

| Trạng thái thực tế | Nên làm gì | Tránh làm gì |
| --- | --- | --- |
| Chưa có commit/tag, chưa publish | Sửa nguyên nhân rồi chạy `prepare` phù hợp | Xóa source không kiểm tra |
| Prepare dừng giữa chừng, descriptor còn | Kiểm phases, cân nhắc resume hoặc rollback | Chạy `-Dresume=false` như lệnh reset |
| Prepare hoàn tất, tag đúng, chưa publish | Sửa môi trường và `perform` từ tag | Prepare lại để tạo tag trùng |
| Perform fail do toolchain/network, chưa upload | Sửa môi trường rồi thử perform từ cùng tag | Sửa tag source trong checkout |
| Perform fail khi upload, staging chưa published | Kiểm deployment ID, drop/retry theo policy | Retry mù vào repository |
| Artifact đã published nhưng có bug | Fix và release **version mới** | Overwrite cùng GAV |
| Multi-module chỉ publish một vài artifacts | Inventory từng module/GAV; lập kế hoạch phát hành mới khi cần | Coi toàn release “chưa tồn tại” |
| Tag đã được ký/protected hoặc consumer sử dụng | Giữ lịch sử, version mới | Force-move tag |
| release.properties/backups đã bị xóa | Điều tra bằng Git/repository records, workflow khôi phục riêng | Hứa rollback sẽ hoạt động |
| Không xác minh được trạng thái repository | Dừng thao tác có side effect, hỏi repository owner | Tự suy ra chưa publish |

**GAV** là `groupId:artifactId:version`; một artifact còn có extension/classifier (JAR, POM, sources, Javadoc, signatures). Với release nhiều module, phải kiểm **từng GAV** chứ không chỉ một file JAR.

## 4. Runbook kiểm tra chỉ đọc trước khi gọi bất kỳ goal có side effect

### 4.1. Git và Maven runtime

Từ đúng root project:

```bash
mvn -version
git status --short
git branch --show-current
git log -n 8 --oneline --decorate
git remote -v
```

Chúng cho biết:
- Maven/JDK đang chạy thật.
- Working tree có thay đổi chưa commit không.
- Nhánh và các commits do Release Plugin tạo.
- Repository Git remote nào được tham chiếu.

**Không** bắt đầu bằng `git reset --hard`, `git clean -fd`, `git push --force`, `git tag -d` hoặc xóa `release.properties`. Đây là lệnh có thể phá dữ liệu hoặc bằng chứng, không phải chẩn đoán chỉ đọc.

### 4.2. Tag local và remote

Với tag `release-recovery-lab-1.4.0`:

```bash
git tag --list "release-recovery-lab-1.4.0"
git ls-remote --tags origin "refs/tags/release-recovery-lab-1.4.0"
git show --no-patch --decorate release-recovery-lab-1.4.0
git show release-recovery-lab-1.4.0:pom.xml
```

Hai `git show` cuối chỉ chạy khi có tag local. Không thấy tag local **không có nghĩa** tag remote không tồn tại. Nếu `ls-remote` bị lỗi do permission/network, trạng thái cần ghi là **chưa xác minh được**, không phải “tag trống”.

Annotated Git tags có tag-object SHA và commit SHA khác nhau. Đối chiếu source commit thực sự được tag, không so nhầm object hash. Kiểm POM **ở commit tag** có version `1.4.0`, thay vì chỉ mở POM development đã thành `1.4.1-SNAPSHOT`.

### 4.3. release.properties và repository state

Nếu còn descriptor và backups trong working copy, giữ nguyên cho tới khi có quyết định resume/rollback. Không gửi file này lên issue công khai mà chưa rà soát, vì SCM URLs và release metadata có thể nhạy cảm.

Tại repository/portal, kiểm:
- tọa độ `com.example.training:release-recovery-lab:1.4.0`;
- trạng thái staging deployment (open, validated, published, dropped);
- checksum/signature nếu có;
- POM/JAR/sources/Javadoc/classifiers nào đã có;
- lịch sử upload, HTTP response, CI job và thời gian;
- version có thể được consumers truy cập hay không.

**Một file ở `target/` không chứng minh remote đã nhận artifact.** Ngược lại, một upload timeout không chứng minh server chưa nhận file.

## 5. Project Java 17/JUnit 5 mẫu: build runnable, release chỉ chạy trong sandbox

Bài thực hành chọn cách không tạo side effect production:
- Java project chạy được qua `mvn clean verify`.
- Maven Release Plugin 3.3.1 được ghim.
- `perform` được cấu hình chạy **`verify` thay vì deploy** để chỉ kiểm tagged source.
- `<scm>` có URL `git.example.invalid` được đánh dấu rõ là **mẫu**, không phải repository có thật; trước khi chạy `prepare` thật, phải thay bằng một Git sandbox có quyền commit/tag/push.

### 5.1. Cấu trúc thư mục

```text
release-recovery-lab/
├── pom.xml
├── .gitignore
└── src/
    ├── main/java/com/example/releaselab/ReleaseCheck.java
    └── test/java/com/example/releaselab/ReleaseCheckTest.java
```

### 5.2. `pom.xml` đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.training</groupId>
    <artifactId>release-recovery-lab</artifactId>
    <version>1.4.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <name>Release Recovery Lab</name>
    <description>Safe release recovery tutorial for Maven 3</description>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <!-- Placeholder: replace with a real authorized Git SANDBOX. -->
    <scm>
        <connection>scm:git:https://git.example.invalid/training/release-recovery-lab.git</connection>
        <developerConnection>scm:git:https://git.example.invalid/training/release-recovery-lab.git</developerConnection>
        <tag>HEAD</tag>
    </scm>

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
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-release-plugin</artifactId>
                <version>3.3.1</version>
                <configuration>
                    <tagNameFormat>@{project.artifactId}-@{project.version}</tagNameFormat>
                    <preparationGoals>clean verify</preparationGoals>
                    <!-- Tutorial mode: never publish artifacts. -->
                    <goals>verify</goals>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Phân tích cấu hình:**
- `version=1.4.0-SNAPSHOT` là trạng thái development ban đầu.
- `scm` là nguồn Git dùng để tạo tag; URL `.invalid` không hoạt động, buộc người học xác nhận Git sandbox trước khi thực thi release.
- `<tag>HEAD</tag>` là giá trị SCM ở development POM; Release Plugin thiết lập tag khi prepare.
- `tagNameFormat` dùng cú pháp đặc biệt `@{project.artifactId}`, không dùng `${...}` của Maven properties. Tag dự kiến là `release-recovery-lab-1.4.0`.
- `preparationGoals=clean verify` được ghim, giống default plugin 3.3.1: chạy tests **trước** khi commit/tag release.
- `goals=verify` có nghĩa `release:perform` thử checkout/build từ tag mà **không deploy**. Trong production, release owner phải chuyển sang `deploy` hoặc release goals được phê duyệt, cấu hình repository và credentials.
- Compiler Plugin 3.13.0 với Java release 17 yêu cầu JDK đủ mới; Surefire 3.5.2 hỗ trợ JUnit Jupiter.
- Project không cần Spring Boot, database, HTTP, Docker hay license server để chạy code mẫu.
- Không có `distributionManagement` vì đây là sandbox tutorial; production phải cấu hình đích deploy riêng.

**Quan trọng:** File POM này **runnable cho Java build/test ngay lập tức**. Lệnh release thật chưa runnable cho tới khi setup Git remote sandbox/SCM và clean working tree. Đừng hiểu URL giả trong ví dụ như một Git host đã tồn tại.

### 5.3. `src/main/java/com/example/releaselab/ReleaseCheck.java`

```java
package com.example.releaselab;

/**
 * A deterministic runtime smoke-test for Maven release training.
 */
public final class ReleaseCheck {

    private ReleaseCheck() {
    }

    public static String result(int input) {
        return "release-ready=" + (input * 2);
    }

    public static void main(String[] args) {
        System.out.println(result(21));
    }
}
```

Output không phụ thuộc network, locale, timezone hoặc external config. `ReleaseCheck.result(21)` trả `"release-ready=42"`.

### 5.4. `src/test/java/com/example/releaselab/ReleaseCheckTest.java`

```java
package com.example.releaselab;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

final class ReleaseCheckTest {

    @Test
    void doublesPositiveInput() {
        assertEquals("release-ready=42", ReleaseCheck.result(21));
    }

    @Test
    void handlesZero() {
        assertEquals("release-ready=0", ReleaseCheck.result(0));
    }
}
```

Hai tests xác minh code. Nếu một test fail, `prepare` mặc định không được coi là hoàn tất, vì `preparationGoals` chạy `verify`.

### 5.5. `.gitignore`

```gitignore
target/
release.properties
pom.xml.releaseBackup
pom.xml.tag
pom.xml.next
pom.xml.backup
*.releaseBackup
```

Đây là chính sách **không commit trạng thái release tạm** vào Git. Điều đó **không cho phép xóa chúng khỏi working copy** khi cần resume/rollback. File thực tế có thể thay đổi theo plugin version và multi-module structure.

### 5.6. Kiểm build/test và stdout

Từ root `release-recovery-lab`:

```bash
mvn -version
mvn -B -ntp clean verify
java -cp target/classes com.example.releaselab.ReleaseCheck
```

Với Maven 3.9.x, JDK 17+ và dependencies tải được, kỳ vọng:

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là **phần tóm tắt Maven logs**, không phải từng dòng stdout nguyên văn. Còn stdout **chính xác của Java program** là:

```text
release-ready=42
```

Đừng dùng `java -jar target/release-recovery-lab-1.4.0-SNAPSHOT.jar` để mong chạy main: POM không cấu hình manifest `Main-Class`. `java -cp` mới là cách chạy rõ ràng ở đây.

## 6. Dry-run và release sandbox: phân biệt chạy thử với hành động thật

### 6.1. Điều kiện trước release:prepare

Một lần prepare thật cần:
- Git repository đã commit source/POM và working tree sạch.
- `<scm>` chứa Git connection/developerConnection **thật** tới sandbox được cho phép.
- Có remote, branch và quyền commit/tag/push theo policy.
- Tag `release-recovery-lab-1.4.0` **chưa tồn tại** trên remote.
- Maven 3.9.x/JDK 17+ phù hợp.
- No SNAPSHOT dependencies không được phép; Maven `clean verify` PASS.
- Version `1.4.0` chưa published ở repository release đích.
- Release owner và CI concurrency lock đã được xác định.

**Không dùng production repo để thử đầu tiên.** `prepare` thật có thể tạo và push commit/tag trước khi error.

### 6.2. Dry-run không commit/tag SCM

Với sandbox Git đã cấu hình đúng:

```bash
mvn -B org.apache.maven.plugins:maven-release-plugin:3.3.1:prepare -DdryRun=true -DreleaseVersion=1.4.0 -DdevelopmentVersion=1.4.1-SNAPSHOT -Dtag=release-recovery-lab-1.4.0
```

Theo docs plugin 3.3.1, `dryRun=true` không checkin/tag hay thay đổi Git checkout như release thật, nhưng có thể **tạo các POM bản dự thảo cạnh originals**, kiểm versioning và chạy verification goals. Vì thế lệnh không phải hoàn toàn side-effect-free ở filesystem.

Quan sát:
- Version release dự kiến là `1.4.0`.
- Tag name dự kiến là `release-recovery-lab-1.4.0`.
- Version tiếp tục phát triển là `1.4.1-SNAPSHOT`.
- Preparation verification chạy đúng cấu hình.
- Không có Git commit/tag mới từ dry-run.
- Mọi file tạm chỉ được dọn sau khi xác định chúng thuộc attempt nào.

Nếu chỉ dọn trạng thái dry-run riêng và **không cần rollback một attempt thật**:

```bash
mvn org.apache.maven.plugins:maven-release-plugin:3.3.1:clean
```

Cẩn thận: lệnh `clean` xóa descriptor/backups. **Không dùng trên working copy còn cần rollback**.

### 6.3. Prepare thật (chỉ sandbox, đã được phê duyệt)

```bash
mvn -B org.apache.maven.plugins:maven-release-plugin:3.3.1:prepare -DreleaseVersion=1.4.0 -DdevelopmentVersion=1.4.1-SNAPSHOT -Dtag=release-recovery-lab-1.4.0
```

Maven Release Plugin có `pushChanges=true` theo mặc định trên distributed SCM như Git. Do đó lệnh có thể **commit/push Git và tạo tag**. Không phải thử nghiệm đọc. Sau thành công, xác minh Git remote tag/version, release.properties và branch development. Đừng suy “release đã published” nếu chỉ prepare thành công.

### 6.4. Perform an toàn cho lab

POM mẫu đặt `goals=verify`, nên sau prepare sandbox thành công và descriptor còn:

```bash
mvn -B org.apache.maven.plugins:maven-release-plugin:3.3.1:perform -Dgoals=verify
```

Lệnh sẽ checkout Git tag và build/test/package từ tag, **không upload artifact**. Đây là một phép kiểm production-like về source tagged, **không phải bước publish thực**. Release `perform` mặc định ở production có thể dùng `deploy` và cần repository/credentials.

## 7. Fail trước commit/tag: xử lý theo nguyên nhân

### 7.1. Git working tree dirty

Khi prepare báo thay đổi chưa commit:
1. Chạy `git status --short`.
2. Phân loại thay đổi cần giữ, files build hoặc file release từ attempt trước.
3. Commit thay đổi đã review hoặc stash có chủ đích trên nhánh phù hợp.
4. Đừng `git reset --hard` bỏ mọi thay đổi không rõ nguồn.
5. Nếu chưa từng vào phases ghi SCM, sửa lỗi xong prepare lại.

Không chạy `rollback` chỉ vì thấy `BUILD FAILURE`: có thể plugin chưa tạo descriptor/backups cần rollback.

### 7.2. SNAPSHOT dependency bị chặn

Release Plugin thường kiểm các dependencies SNAPSHOT và có thể yêu cầu giải quyết trước khi phát hành. Ví dụ module dùng `com.example:common-api:2.0-SNAPSHOT`. Thay đổi phù hợp:
- chọn release version `common-api` đã được publish và kiểm thử;
- cập nhật POM/BOM/dependencyManagement đúng;
- chạy `mvn clean verify` trên source có dependency release;
- commit và chạy prepare lại.

Không tự bật `ignoreSnapshots` hay `autoResolveSnapshots` để bỏ qua quyết định versioning, vì SNAPSHOT mutable làm release khó tái lập. Nếu policy cho phép ngoại lệ, tài liệu hóa và kiểm provenance.

### 7.3. Test fail trong preparationGoals

Vì `preparationGoals=clean verify`, JUnit fail sẽ làm prepare dừng. Trong project mẫu, bạn có thể **thử lỗi build mà không làm release** bằng cách tạm đổi assertion:

```java
assertEquals("release-ready=41", ReleaseCheck.result(21));
```

và chạy:

```bash
mvn test
```

Actual là `release-ready=42` nên assertion fail. Sau đó khôi phục:

```java
assertEquals("release-ready=42", ReleaseCheck.result(21));
```

rồi chạy `mvn clean verify` để PASS.

**Nếu muốn thử prepare fail thật trên Git sandbox**, một test failure cần tồn tại trong **commit đã được commit**; nếu bạn sửa file mà chưa commit, prepare có thể fail từ `dirty working copy` trước khi chạy tests. Không commit source lỗi vào protected production branch chỉ để demo.

### 7.4. Plugin hoặc SCM bootstrap fail

Các lỗi `PluginResolutionException`, parent POM missing, Git executable not found, network/TLS hoặc JDK mismatch có thể xuất hiện trước bất kỳ tag nào. Ghi lại lỗi thật, Maven/JDK/settings, remote, token scope, rồi sửa đúng tầng. Đừng điều chỉnh phiên bản release hoặc xóa tag như giải pháp cho lỗi Maven plugin chưa tải được.

## 8. Prepare fail giữa chừng: resume, rollback, clean hay start again?

### 8.1. Resume khi descriptor còn đúng attempt

`release:prepare` có `resume=true` mặc định. Khi lần chạy bị dừng giữa một chuỗi phases, nó có thể tiếp tục dựa trên `release.properties`.

```bash
mvn org.apache.maven.plugins:maven-release-plugin:3.3.1:prepare
```

Chỉ resume nếu:
- descriptor thực sự thuộc cùng release/version/attempt;
- Git branch và tag đã được kiểm tra;
- source/working copy không đổi bất ngờ;
- lỗi đã được sửa mà không cần sửa tagged source;
- không có concurrent release job;
- artifact/repository chưa xảy ra publish mâu thuẫn.

`resume` không phải “undo rồi làm lại”. Nó tiếp tục theo trạng thái plugin lưu, và state này có thể không còn phản ánh thực tế nếu có người sửa Git hoặc repository ngoài luồng.

### 8.2. Rollback một attempt chưa publish

Nếu release chuẩn bị dang dở và bạn quyết định **hủy attempt**, đồng thời backup/descriptor còn:

```bash
mvn org.apache.maven.plugins:maven-release-plugin:3.3.1:rollback
```

Theo tài liệu, plugin cố khôi phục POM trước prepare ở working copy và SCM nếu release đã commit; các phiên bản mới có hỗ trợ loại bỏ branch/tag đã tạo. Nhưng:
- rollback có thể bị chặn bởi Git protected tags hoặc quyền;
- một SCM provider có thể có behavior riêng;
- rollback không thu hồi Maven Central artifact;
- người khác có thể đã fetch tag hoặc tham chiếu nó;
- rollback là hành động có side effect cần owner/approval khi SCM shared.

**Không dùng rollback sau publish để cố đổi bytes dưới cùng GAV.** Khi tag hoặc artifact đã công bố, ưu tiên giữ lịch sử và tạo version mới.

### 8.3. Clean chỉ xóa dữ liệu phục hồi

```bash
mvn org.apache.maven.plugins:maven-release-plugin:3.3.1:clean
```

Theo docs, lệnh xóa `release.properties` và POM backups, **không hoàn tác SCM changes**. Nếu chạy clean trước rồi mới muốn rollback, plugin thường không còn điều kiện để khôi phục tự động.

### 8.4. -Dresume=false không phải nút reset

```bash
mvn org.apache.maven.plugins:maven-release-plugin:3.3.1:prepare -Dresume=false
```

đề nghị bắt đầu một prepare attempt mới, **không bảo đảm tag cũ biến mất hoặc commit được khôi phục**. Nếu tag `release-recovery-lab-1.4.0` đã có trên remote hoặc development branch đang là `1.4.1-SNAPSHOT`, lệnh mới có thể fail với tag conflict hoặc release version sai. Trước khi dùng, xử lý trạng thái lần trước có kiểm soát.

**Quy tắc nhớ:**
- Cùng attempt và descriptor còn → xem `resume`.
- Muốn hủy một prepare chưa publish → cân nhắc `rollback`.
- Chỉ dọn metadata sau khi đã có quyết định → `clean`.
- Muốn tạo attempt mới → giải quyết state cũ trước, không chỉ `resume=false`.

## 9. Tag đã tồn tại: không xóa hoặc retag theo phản xạ

`git tag --list` và `git ls-remote --tags origin` phải được kiểm riêng. Một tag “already exists” có thể đến từ:
- Prepare đã tạo tag local nhưng push failed.
- Tag remote đã push, còn commit next development chưa tạo.
- Một CI job khác đã publish release.
- Tag thuộc một attempt trước có tên trùng.
- Tag được ký/protected hoặc đang được consumers sử dụng.

Nếu tag đúng source version và chưa publish, có thể **không cần prepare lại**: khôi phục perform từ tag đúng. Nếu tag đã public, hãy giữ tag bất biến. **Không** dùng `git tag -f`, `git push --force` hay delete/recreate remote tag chỉ để đổi source SHA.

Tag được ký có thể dùng SHA tag object khác SHA commit. Khi audit, ghi lại commit SHA được tag trỏ tới, POM version ở tag, artifact checksums/signatures và CI job. Tên version giống nhau **không tự chứng minh** bytes artifact giống nhau.

## 10. Prepare hoàn tất nhưng perform thất bại

### 10.1. SCM checkout từ tag fail

Dấu hiệu:
- `release:perform` báo không checkout được `target/checkout`;
- repository URL/auth/SSH keys sai;
- Git remote tag không nhìn thấy;
- CI runner mới không có `release.properties`;
- proxy/network/branch permissions chặn SCM.

Điều tra:
1. Kiểm remote tag bằng Git read-only.
2. Kiểm `release.properties` và SCM URL của POM (không leak token).
3. Xác minh Maven 3.9.x, Release Plugin 3.3.1, Git executable và credentials.
4. Sửa connection/permission đúng repo sandbox/production.
5. Chạy lại perform **nếu release tag đúng và repository upload state an toàn**.

Không chỉnh source trong `target/checkout` rồi coi là đã sửa Git tag. Thư mục đó là workspace build tạm từ SCM.

### 10.2. Perform checkout được nhưng tests fail

Khi perform build từ Git tag, bạn phải phân biệt:
- **Lỗi môi trường:** JDK khác, thiếu settings/mirror, external test service không chạy, toolchain sai. Sửa môi trường, retry từ cùng tag khi an toàn.
- **Lỗi trong source đã tag:** bug code, test sai hoặc một dependency version không tương thích. Sửa trên một branch có review rồi **phát hành tag/version mới** nếu release/tag đã công bố hoặc protected.
- **Test flaky:** thu thập evidence, xử lý tính xác định; không bỏ kiểm thử bằng `-DskipTests` để phát hành trong khi release validation chưa đáng tin.

`mvn clean verify` trên development branch ngày hôm sau có thể PASS, nhưng `perform` vẫn lấy code của tag hôm trước. Phải kiểm **cùng commit SHA** mới so sánh được.

### 10.3. Chạy thử perform với goals=verify

POM lab chọn:

```xml
<goals>verify</goals>
```

Có thể gọi tường minh:

```bash
mvn -B org.apache.maven.plugins:maven-release-plugin:3.3.1:perform -Dgoals=verify
```

Nếu source tag được checkout đúng và các tests PASS, đây là bằng chứng **build từ tag** hoạt động, nhưng **không có artifact published**. Không gọi tình trạng này là release thành công ở môi trường production.

### 10.4. Deploy lỗi 401/403/409/timeout

Đừng đoán:
- **401:** credentials thiếu/sai hoặc token expired.
- **403:** không có quyền, repository policy/allowlist hoặc protected deployment.
- **409:** version/GAV đã tồn tại, repository từ chối overwrite, hoặc conflict staging.
- **Timeout/5xx:** có thể server đã nhận file một phần hoặc toàn bộ trước khi CLI mất kết nối.

**Checklist cần xác minh trước retry:**
1. Remote có đúng `G:A:V` không?
2. JAR/POM/sources/Javadoc/checksum/signatures có đủ chưa?
3. Đây là snapshot, staging chưa publish, private release hay public Maven Central?
4. Staging deployment ID nào, trạng thái open/validated/published/dropped?
5. Có job CI khác đang phát hành same version không?
6. Consumers đã có thể tải version đó chưa?
7. Artifact bytes tương ứng tag/commit nào?
8. Repository owner có cho phép replay cùng version không?

Chỉ khi xác định **chưa publish bất kỳ artifact conflict nào** và staging policy cho phép, mới cân nhắc retry từ **cùng tag**. Nếu repository đã nhận một release GAV và bytes cần thay, dùng **new version**.

## 11. Tại sao artifact đã publish phải có version mới?

### 11.1. Maven Central immutable

Sonatype Central quy định các release components đã published **không được sửa, xóa hay cập nhật**. Nếu `1.4.0` có bug, cách đúng là xuất bản `1.4.1` (hoặc next version phù hợp chính sách) và hướng dẫn consumers nâng cấp.

Nguyên nhân kỹ thuật: Maven Resolver và các công cụ build có thể cache release artifacts theo GAV. Nếu một ngày cùng `1.4.0` có bytes mới, người dùng A còn cache cũ, người dùng B tải bản mới, dù cả hai khai cùng dependency version. Điều đó phá reproducibility và khiến debug/security audit khó tin cậy.

### 11.2. Staging chưa publish khác release đã public

Một staging deployment có thể được drop khi validation fail, tùy repository policy. **Drop staging chưa publish** không đồng nghĩa xóa release đã công bố. Nếu staging chưa publish và mọi artifact có thể xóa an toàn, có thể chuẩn bị staging mới từ cùng source tag theo chính sách. Nhưng nếu `1.4.0` đã public, không được sửa artifact cùng version.

### 11.3. Private release repository cũng nên tránh overwrite

Một số repository nội bộ về mặt kỹ thuật cho phép redeploy cùng version. Dù vậy, chính sách tốt thường là **disable redeploy releases** để tránh cache/provenance mismatch. Chỉ repo owner mới có thể xác định trạng thái và policy. Không coi khả năng bấm nút “Delete” ở UI là quyền xóa một artifact consumers đang dùng.

### 11.4. Khi release nhiều module publish một phần

Giả sử:
```text
parent:1.4.0    published
core:1.4.0      published
api:1.4.0       failed
app:1.4.0       skipped
```

Đừng nói “release 1.4.0 chưa tồn tại”. Các artifacts đã public có thể không được xóa/chỉnh. Cần inventory từng GAV/classifier, đánh giá consumers đang resolve được gì và có thể phải phát hành **coordinated new version** cho tất cả modules theo chiến lược compatibility của dự án.

## 12. Phát hành lại 1.4.1 sau bug trong 1.4.0

### 12.1. Chọn đúng source branch

Nếu sau `prepare 1.4.0` branch development đang `1.4.1-SNAPSHOT` và chứa thay đổi phù hợp, tạo fix branch từ đó rồi merge/review. Nếu main đã phát triển lên `1.5.0-SNAPSHOT` với thay đổi không muốn backport, mở maintenance branch từ commit/tag `1.4.0`, cherry-pick hoặc sửa bug có kiểm soát, và chuẩn bị patch release `1.4.1`.

Giữ nguyên:
- old tag `release-recovery-lab-1.4.0`;
- old artifact `release-recovery-lab:1.4.0` và checksums;
- lịch sử CI/issue của version cũ.

Không tự xóa hoặc force-move tag cũ.

### 12.2. Kiểm build trước khi release version mới

Trên branch fix, với POM phát triển `1.4.1-SNAPSHOT` và test đã sửa:

```bash
mvn -B -ntp clean verify
git status --short
git log -n 5 --oneline
```

Source phải được commit/review và working tree sạch trước prepare. Nếu nhiều modules, kiểm parent/child versions, dependencyManagement, SCM tag naming, modules included và release profiles.

### 12.3. Dry-run new version

Chỉ trên Git sandbox hoặc môi trường đã cho phép:

```bash
mvn -B org.apache.maven.plugins:maven-release-plugin:3.3.1:prepare -DdryRun=true -DreleaseVersion=1.4.1 -DdevelopmentVersion=1.4.2-SNAPSHOT -Dtag=release-recovery-lab-1.4.1
```

Đối chiếu:
- tag mới chưa tồn tại;
- version release không còn `-SNAPSHOT`;
- next development version có ý nghĩa;
- checks PASS và SCM connection trỏ đúng repository;
- repository chưa có GAV `1.4.1`.

### 12.4. Prepare release mới có phê duyệt

Sau khi đã kiểm và được phép thao tác trên SCM release:

```bash
mvn -B org.apache.maven.plugins:maven-release-plugin:3.3.1:prepare -DreleaseVersion=1.4.1 -DdevelopmentVersion=1.4.2-SNAPSHOT -Dtag=release-recovery-lab-1.4.1
```

**Đây là lệnh có thể push commit/tag thật.** Không chạy trên repo production chỉ vì bài hướng dẫn nêu ví dụ. Sau prepare, lưu commit SHA của tag mới và next-development commit.

### 12.5. Verify từ tag trước publish

Với POM lab:

```bash
mvn -B org.apache.maven.plugins:maven-release-plugin:3.3.1:perform -Dgoals=verify
```

Lệnh checkout tag mới và chạy tests, nhưng không deploy. Production release pipeline thay `verify` bằng goals có `deploy` sau khi repository target, signing, security/quality gates và approvals được kiểm xong.

**Không dùng `1.4.1` nếu version đó đã tồn tại trên repository.** Chọn next free version theo version policy; releaseVersion/developmentVersion không được đoán từ tên branch.

## 13. Repository SCM và artifact deployment là hai cấu hình khác nhau

### 13.1. SCM URL

POM có:
```xml
<scm>
    <connection>scm:git:https://git.example.invalid/training/release-recovery-lab.git</connection>
    <developerConnection>scm:git:https://git.example.invalid/training/release-recovery-lab.git</developerConnection>
    <tag>HEAD</tag>
</scm>
```

Đây chỉ là placeholder về nơi source/tag. Với release thật, thay bằng connection thực và xác nhận quyền Git theo chính sách, không lưu Git token trong POM.

### 13.2. Artifact repository URL

Để `release:perform` thực sự deploy, production POM còn cần configuration như:

```xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <url>https://repo.example.invalid/repository/maven-releases</url>
    </repository>
    <snapshotRepository>
        <id>company-snapshots</id>
        <url>https://repo.example.invalid/repository/maven-snapshots</url>
    </snapshotRepository>
</distributionManagement>
```

**Fragment này là minh họa, URL không tồn tại.** Credentials nên nằm trong protected Maven `settings.xml`/CI secret manager gắn đúng server ID, không đưa password vào POM.

- `<scm>` chọn source Git/tag.
- `distributionManagement` chọn nơi Maven deploy artifact.
- `release:prepare` chủ yếu sửa SCM/POM.
- `release:perform` chạy build/deploy từ SCM tag theo goals.

Nếu Git push lỗi, sửa Git permission; nếu artifact deploy 401, sửa repository server ID/credentials; không sửa nhầm hai nơi.

### 13.3. Thử nghiệm perform và deploy thực

POM lab cố ý đặt:

```xml
<goals>verify</goals>
```

Để thực sự publish một release **đã được phê duyệt**, config production phải dùng goals có `deploy` và repository đích hợp lệ. Ví dụ mang tính phân biệt hành vi, **không tự chạy**:

```bash
mvn -B org.apache.maven.plugins:maven-release-plugin:3.3.1:perform -Dgoals=deploy
```

Lệnh này có khả năng upload artifact thật. Chỉ sử dụng khi tag/version/repository/staging và quyền đã được xác minh. Khi publish Maven Central, có thể dùng một cơ chế publisher/staging portal riêng, không phải mọi project đều đẩy trực tiếp chỉ với Maven Deploy Plugin.

## 14. Multi-module và release version consistency

Một parent reactor có:

```text
root-parent (pom)
├── common-lib (jar)
├── api-lib (jar, depends common-lib)
└── app (jar, depends api-lib)
```

Release Plugin có thể đặt version cho từng module. `autoVersionSubmodules=true` giúp các module theo version parent khi dự án cần đồng version. Với multi-module versions khác nhau, non-interactive release dùng properties dạng:

```text
project.rel.<groupId>:<artifactId>=<releaseVersion>
project.dev.<groupId>:<artifactId>=<nextDevelopmentVersion>
```

Trong shell, có thể cần quote/escape dấu `:` trong property names khi truyền qua Maven; docs có ví dụ rõ ràng. Đừng đổi độc lập mỗi `<version>` mà quên:
- parent references ở modules;
- inter-module dependency versions;
- dependencyManagement BOM/version;
- module inclusion/exclusion;
- snapshot dependencies còn sót;
- tag naming và release staging artifacts.

**Partial multi-module publish** là trường hợp đặc biệt nguy hiểm: một GAV có thể public trong khi GAV khác cùng release line chưa có. Inventory từng module, manifest artifact/checksum và consumers trước khi chọn coordinated new version. Không retry blind khi repository cấm redeploy.

## 15. CI release: checkpoint và idempotency

### 15.1. Thiết kế pipeline

```text
Preflight: Git SHA, clean branch, toolchain, tag/GAV free
    |
    v
Tests: mvn clean verify, security/license/SBOM checks
    |
    v
Prepare: version, commit, tag, next development commit
    |
    v
Verify tagged source: checkout + clean verify
    |
    v
Stage/upload: repository deployment under scoped credentials
    |
    v
Validate/approve/publish
    |
    v
Post-release: checksums, provenance, changelog, notify
```

Lần prepare tự chạy preparationGoals, nhưng nhiều CI pipelines cũng có test stage độc lập trước đó. Điều quan trọng là **source đã tag được kiểm thử đúng** và releases không đi thẳng đến publish khi còn failure.

### 15.2. Chống concurrent jobs

Trước khi job publish:
- lock theo project + version + repository target;
- xác minh remote tag và published GAV chưa bị job khác chiếm;
- gắn attempt ID, CI build URL và commit SHA;
- lưu release descriptor/metadata theo chính sách bảo mật;
- phân quyền Git tag/push và artifact repository deploy;
- không cho retry tự động sau timeout khi publish state chưa được xác minh.

Một idempotency key có thể gồm:

```text
project=com.example.training:release-recovery-lab
version=1.4.1
tag=release-recovery-lab-1.4.1
commit=<actual-git-sha>
repository=<approved-release-repository>
```

Các giá trị trong dấu ngoặc là **dữ liệu phải đọc thật**, không phải placeholder để đưa vào artifact manifest. Nếu key đã published, job không publish lại. Nếu state unknown, job dừng để kiểm trước khi retry.

### 15.3. Quyền và secrets

Git token chỉ cần những quyền SCM thật sự được cấp; token deploy artifact nên có phạm vi repository riêng. Với protected Git tags, thao tác rollback có thể bị chặn, điều đó **không cho phép force-push**. Nếu cần signed tags hoặc ký artifact, phải có key và quy trình provision phù hợp. Không copy secrets vào CLI logs, POM, chat hoặc public HTML reports.

### 15.4. Không dùng skip flags để chữa lỗi phát hành

`-DskipTests`, `-Dmaven.test.skip=true`, tắt Enforcer, bỏ signing hoặc gắn `-Dresume=false` không phải biện pháp chữa một release thất bại. Chúng có thể che lỗi hoặc bắt đầu attempt khác trong khi tag/GAV cũ còn. Release chuẩn cần test artifact thực và giữ đủ chứng cứ về source, checksum và approvals.

## 16. Bảng lỗi Maven Release Plugin và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Working copy has local modifications | Git dirty | Kiểm status, commit/stash có chủ đích |
| SNAPSHOT dependencies found | Dùng dependency chưa release | Pin release dependency và test lại |
| SCM connection missing | POM thiếu `<scm>`/URL không hợp lệ | Cấu hình Git repository thật |
| Git tag already exists | Attempt cũ hoặc release đã có | Kiểm local/remote/repo state |
| Git push rejected | Protected branch/tag, token thiếu quyền | Xử lý với repository owner |
| Prepare fail giữa commits | Release descriptor còn | Xem resume hoặc rollback sau inventory |
| release:prepare -Dresume=false tiếp tục lỗi | Tag/commit side effects chưa xử lý | Không coi là reset |
| release:clean xong không rollback được | Backups/descriptor bị xóa | Điều tra Git, kế hoạch thủ công có review |
| release:rollback không xóa tag | Provider/permission/policy | Dừng, kiểm tag và owners |
| Perform không checkout tag | SCM URL/auth/remote tag lỗi | Kiểm ls-remote và descriptor |
| Perform chạy source cũ | Checkout đúng tag cũ | Version/tag mới nếu source cần thay |
| Local main pass, tag build fail | Source/JDK/profiles khác | So SHA/JDK/config đúng tag |
| Deploy HTTP 401 | Auth credentials sai | Kiểm Maven server ID/secret |
| Deploy HTTP 403 | Thiếu quyền hoặc repo policy | Liên hệ repo owner, không bypass |
| Deploy HTTP 409 | Version/GAV đã có | Không overwrite, cân nhắc new version |
| Deploy timeout/5xx | Server có thể đã upload một phần | Tra server state trước retry |
| Staging validation fail | Chữ ký/POM metadata thiếu | Sửa trước publish, drop/recreate staging theo policy |
| Một module published, module khác chưa | Multi-module release dang dở | Inventory từng GAV/classifier |
| Maven Central version có bug | Artifact immutable | Release patch/new version + advisory |
| CI retry tạo duplicate release | Thiếu lock/idempotency | Lock theo version/tag, kiểm remote trước |
| Perform `goals=verify` SUCCESS nhưng repo trống | Lab không deploy | Production cần deploy/publisher stage |
| File JAR local có, remote không có | Package ≠ deploy | Kiểm repository state, không dựa vào target |
| Tag và source checksum khác kỳ vọng | Release metadata mismatch | Dừng publish, audit commit/manifest |
| CI credentials lộ trong log | Secret handling sai | Thu hồi token, sửa pipeline, không đăng log thô |

## 17. Bài tập tự đánh giá

**Bài 1.** `release:prepare` fail khi JUnit test trước commit/tag. Có bắt buộc đổi release version không? **Không nhất thiết**, nếu chưa publish/tag thì sửa test, kiểm descriptor/state rồi prepare lại phù hợp.

**Bài 2.** `release:prepare` thành công, Git tag `1.4.0` có, `perform` chưa chạy. Nên làm gì? **Dùng perform từ tag**, không prepare lại để tạo tag trùng.

**Bài 3.** `release:rollback` có xóa artifact Maven Central không? **Không.** Nó không phải một rollback transaction cho remote releases.

**Bài 4.** `release:clean` có hoàn tác Git commit/tag không? **Không.** Nó xóa descriptor/backups tại working copy.

**Bài 5.** `-Dresume=false` có tự xóa tag remote cũ không? **Không.** Cần phân loại side effects trước.

**Bài 6.** Deploy timeout có chắc remote chưa nhận JAR? **Không.** Tra server/repository state, không retry mù.

**Bài 7.** `1.4.0` đã public nhưng có bug. Có thể upload lại bytes mới vào `1.4.0` trên Maven Central không? **Không**, cần new version.

**Bài 8.** Bạn sửa code trên main, chạy lại perform tag `1.4.0`. Code fix có đi vào artifact không? **Không**, perform checkout tag cũ.

**Bài 9.** Staging chưa published, validation fail. Có thể drop/recreate cùng version không? **Có thể**, nếu policy và repo state xác nhận an toàn; không coi trường hợp này giống artifact đã public.

**Bài 10.** core:1.4.0 đã publish nhưng app:1.4.0 fail. Có nên nói release chưa tồn tại? **Không**, phải xem từng GAV.

**Bài 11.** Tại sao POM mẫu đặt `goals=verify`? Để perform từ tag **không upload artifact** trong lab.

**Bài 12.** Các tham số non-interactive prepare 1.4.0 gồm gì? `releaseVersion=1.4.0`, `developmentVersion=1.4.1-SNAPSHOT`, `tag=release-recovery-lab-1.4.0`.

**Bài 13.** Vì sao không force-move Git tag đã phát hành? Vì tag, source SHA, artifact checksum, cache và audit không còn nhất quán.

**Bài 14.** Git push lỗi 403, artifact deploy credentials đúng. Nên sửa ở đâu? **SCM permissions/branch policy**, không phải distributionManagement.

**Bài 15.** 1.4.0 đã public, fix được review, branch đang 1.4.1-SNAPSHOT. Version kế tiếp hợp lý? **1.4.1** nếu chưa có và phù hợp version policy, với tag mới và next development 1.4.2-SNAPSHOT.

**Bài 16.** Có release.properties nhưng Git đã có người sửa tag từ ngoài. Có nên resume ngay? **Không**, descriptor có thể lệch state thực; cần kiểm tra/audit.

**Bài 17.** `mvn clean verify` trên main PASS có chứng minh perform từ tag cũng PASS? **Không**, main và tag có thể là commits khác nhau.

**Bài 18.** Những bằng chứng để chốt release thành công? Tag + commit SHA, Maven build/tests, artifact manifest/checksums/signatures, repository publish state, approvals/changelog.

## 18. Checklist áp dụng trong dự án thật

- [ ] Đã xác định lỗi ở prepare, perform, staging hay sau publish.
- [ ] Đã lấy Maven/JDK/Git versions và log của chính attempt lỗi.
- [ ] Đã biết source branch/commit SHA, Git tag local và remote.
- [ ] Đã kiểm `release.properties` và POM backups **trước khi chạy clean**.
- [ ] Đã xác minh repository publish state của mọi GAV/classifier liên quan.
- [ ] Đã xác minh tag trỏ source/POM release đúng version.
- [ ] Không chạy force push, xóa tag, hard reset hay redeploy theo phản xạ.
- [ ] Resume prepare chỉ khi state descriptor phù hợp attempt thật.
- [ ] Rollback chỉ khi được phép hủy prepare và còn đủ backups.
- [ ] Clean chỉ dùng khi đã chốt không cần rollback/resume.
- [ ] Perform retry chỉ sau khi kiểm partial publish/staging.
- [ ] Với version đã public, chọn **new version**, giữ old tag/artifact.
- [ ] Đã sửa source, test và review ở branch/maintenance line đúng.
- [ ] Đã đảm bảo new tag/GAV chưa tồn tại.
- [ ] Đã dry-run prepare khi thích hợp và chốt release/development versions.
- [ ] Đã test source từ tag, không chỉ main.
- [ ] Với multi-module, parent/dependency versions đồng bộ và không sót artifact.
- [ ] CI có lock/idempotency, deploy secrets scoped và publish approvals.
- [ ] Chữ ký/checksum/provenance/SBOM đạt policy nếu yêu cầu.
- [ ] Đã thông báo changelog/advisory và cách nâng version cho consumers.
- [ ] Đã lưu evidence để audit cả attempt lỗi và release thay thế.

## 19. Sơ đồ quyết định cuối cùng

```text
Release command failed
         |
         v
Read Git tag/commit + release.properties + repository status
         |
         v
Is any release artifact already PUBLIC?
    | YES                                | NO / UNKNOWN
    v                                    v
Preserve old GAV/tag                 Inspect staging and tag
Fix source and NEW VERSION                |
    |                             +------+--------+
    v                             |               |
new prepare/tag/perform      prepare incomplete  prepare complete
                              |                     |
                        resume/rollback        retry perform
                        if safe                if safe
                              |                     |
                              +----------+----------+
                                         |
                                         v
                               Verify repo state again
```

Nhánh **UNKNOWN** không có nghĩa được quyền retry ngay. Phải xác minh server/staging/publisher state trước khi có một hành động mới.

**Kết luận:** Cách xử lý release Maven thất bại phụ thuộc **side effects đã xảy ra**. `release:prepare` có thể đã commit/tag; `release:perform` có thể đã upload một phần hoặc toàn bộ; `release:rollback` không thu hồi artifact public; `release:clean` chỉ dọn descriptor/backup. Chỉ resume/retry cùng version khi đã chứng minh trạng thái an toàn; nếu artifact đã public và cần thay đổi code hoặc bytes, hãy **phát hành version mới** và giữ lịch sử bất biến.

### Tài liệu chính thức

- [Maven Release Plugin 3.3.1](https://maven.apache.org/maven-release/maven-release-plugin/)
- [Prepare a Release](https://maven.apache.org/maven-release/maven-release-plugin/usage/prepare-release.html)
- [Perform a Release](https://maven.apache.org/maven-release/maven-release-plugin/usage/perform-release.html)
- [Rollback a Release](https://maven.apache.org/maven-release/maven-release-plugin/usage/rollback-release.html)
- [Clean a Release](https://maven.apache.org/maven-release/maven-release-plugin/usage/clean-release.html)
- [Non-interactive Release](https://maven.apache.org/maven-release/maven-release-plugin/usage/non-interactive-release.html)
- [Update POM Versions](https://maven.apache.org/maven-release/maven-release-plugin/usage/update-versions.html)
- [release:prepare parameters](https://maven.apache.org/maven-release/maven-release-plugin/prepare-mojo.html)
- [release:perform parameters](https://maven.apache.org/maven-release/maven-release-plugin/perform-mojo.html)
- [Apache Maven Guide to Releasing](https://maven.apache.org/guides/mini/guide-releasing.html)
- [Sonatype Central: Immutability of Published Components](https://central.sonatype.org/publish/requirements/immutability/)
- [Sonatype Central: Can I change published artifacts?](https://central.sonatype.org/faq/can-i-change-a-component/)
