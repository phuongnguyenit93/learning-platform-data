# Không đưa token, mật khẩu hoặc khóa ký vào Git và artifact trong Gradle

## Mục tiêu bài học

Một Gradle build có thể chạy thành công nhưng vẫn gây sự cố nghiêm trọng khi **token, mật khẩu repository, private signing key hoặc passphrase** vô tình xuất hiện trong Git, JAR/ZIP, POM, test report, log, Build Scan hoặc CI artifact. Đây không chỉ là lỗi .gitignore: phải kiểm soát **nơi lưu**, **quyền sử dụng**, **vòng đời**, **đường truyền** và **đầu ra** của secret.

Bài học thuộc nhóm **An toàn build** giúp bạn:

1. Phân biệt secret với public metadata, public key, chữ ký và checksum.
2. Biết vì sao xóa ở HEAD không xóa token khỏi Git history/forks/clones.
3. Dùng .gitignore và secret scanning đúng chức năng, không tự tin quá mức.
4. Không hardcode secret vào Java class/resources, Gradle script hoặc test fixtures.
5. Cấp private Maven credentials qua **Gradle PasswordCredentials** và **ORG_GRADLE_PROJECT_***.
6. Sử dụng Gradle User Home, Providers và CI secrets store có kiểm soát.
7. Dùng Signing Plugin, **useInMemoryPgpKeys** hoặc gpg-agent thay vì commit private key.
8. Hiểu nguy cơ từ Gradle Build Cache/Configuration Cache, remote cache, logs và reports.
9. Thiết kế GitLab/Jenkins release jobs không cho untrusted PR/MR đọc signing/publishing secrets.
10. Chạy lab **Java 17** tạo public report, distribution ZIP và audit tên entry trong JAR/ZIP.
11. Phát hiện và xử lý sự cố đã lộ bằng revoke/rotate, artifact quarantine, history cleanup và review.

Tất cả ví dụ dùng **dữ liệu giả, không có real token/password/private key**. Các URL thuộc **example.invalid** chỉ để minh họa. Bài thực hành dùng Gradle Groovy DSL, kèm Kotlin DSL, Java17, Linux/macOS và Windows PowerShell.

---

## 1. Secret là gì?

| Loại dữ liệu | Cần giữ kín? | Rủi ro nếu lộ |
| --- | --- | --- |
| Git PAT, CI token, deploy token | Có | Thay danh tính và gọi API theo scopes |
| Maven read password | Có | Download private modules |
| Maven deploy password/token | Có | Publish hoặc thay package |
| Cloud access/session token | Có | Gọi cloud API đến khi hết hạn/revoke |
| SSH private key | Có | Mạo danh user/service |
| OpenPGP private signing key | Có | Ký artifact giả |
| Signing passphrase | Có | Sử dụng private key đã bị lộ |
| Keystore .p12/.pfx có private key | Có | Giả mạo hoặc ký |
| OpenPGP public key | Không | Verify signatures |
| Artifact signature .asc | Thường không | Public signature |
| SHA-256 checksum, commit SHA | Không | Integrity và version identifiers |
| Maven username | Tùy policy | Có thể là metadata nội bộ |
| Repository hostname/path | Tùy policy | Có thể lộ internal topology |

**Đừng chỉ dựa vào extension.** File `.asc` có thể là public signature hoặc ASCII-armored *private* key; file `.pem` có thể là certificate công khai hoặc private key. Phân loại theo nội dung.

**Least privilege:** Test cần read-only artifact token thì không được nhận deploy/admin token. Tạo scope riêng cho dependency read, publishing, deployment và signing; ưu tiên short-lived credentials, rotation và audit logs.

---

## 2. Ba ranh giới an toàn của một Gradle build

~~~text
CI secret manager / developer private store
                 |
                 v
           Gradle process
          /       |       \
 Maven auth    signing   app/build tasks
      |           |           |
      +-----------+-----------+
                  |
             Các điểm rò
       +----------+-----------+
       |          |           |
   Git/history   logs       JAR/ZIP/POM
   forks/clones   scans     test reports
                  |           |
              CI cache    CI artifacts
                  |           |
              external consumers/mirrors
~~~

Cần xét riêng:

- **Git boundary:** file/bytes nào được track, commit và push?
- **Execution boundary:** build.gradle, settings.gradle, buildSrc, init scripts, included builds, plugins nào được quyền đọc env và Gradle User Home?
- **Artifact boundary:** files/bytes nào được đưa vào JAR, ZIP, POM, test reports, container images và registry?

**Gradle build logic không chạy trong sandbox.** Code của một plugin/build script có quyền thực thi theo OS user của Gradle process. Vì vậy **không cấp release credentials khi chạy untrusted PR build logic**, dù token không nằm trong source code.

Một file `.env` bị .gitignore vẫn có thể bị `Zip.from(projectDir)` đóng vào artifact. Một secret không được in trên console vẫn có thể nằm trong JAR. Một CI system che password trong log không tự redact JUnit XML hoặc generated ZIP.

---

## 3. Ngăn Git commit và history leak

### 3.1. .gitignore mẫu

~~~gitignore
.env
.env.*
!.env.example
.local-secrets/
secrets.local/

*.p12
*.pfx
*.keystore
id_rsa
id_ed25519

.gradle/
build/
out/
~~~

`.env.example` chỉ nên lưu **tên biến và dummy value không có quyền thật**. Patterns key file có thể false-positive với public fixtures, cần review; không ignore `gradle/wrapper/` vì Wrapper là file phiên bản build cần commit.

### 3.2. gradle.properties có thể được commit nếu chỉ là public configuration

~~~properties
org.gradle.caching=true
org.gradle.jvmargs=-Xmx1g
org.gradle.warning.mode=summary
~~~

Không đặt token/password/private key trong project-root gradle.properties đã được track. Với developer credentials, ưu tiên OS keychain/secret manager hoặc user-level `GRADLE_USER_HOME/gradle.properties` ngoài Git và có quyền hạn chế.

### 3.3. Kiểm đường dẫn có được Git track hay không

~~~bash
git status --short
git ls-files -- .env
git ls-files -- gradle.properties
git ls-files -- '*.p12' '*.pfx' '*.keystore'
git check-ignore -v .env
~~~

Những lệnh này chỉ kiểm tên file/rules, không in secret values. Lưu ý **.gitignore không tự ngăn Git tiếp tục track một file đã commit**.

### 3.4. Xóa file khỏi commit mới chưa xóa khỏi history

~~~text
Commit A: chứa token trong .env
Commit B: xóa .env
HEAD hiện tại: không có file
History: Commit A vẫn có token
~~~

`git rm --cached -- .env` có thể bỏ file khỏi index mà giữ file local, nhưng **không revoke token, không xóa blobs cũ, không xóa forks/clones/backups**.

Khi phát hiện token thật bị commit:
1. Báo security/repository owner.
2. **Revoke/disable** token càng sớm càng tốt.
3. Rotate token mới ít quyền hơn, cập nhật secret manager.
4. Điều tra Git history, branches/tags, forks, logs, CI artifacts và mirrors.
5. Phối hợp history cleanup với admins; không tự force-push/rewrite history trên repo nhóm.
6. Quét lại nguồn và outputs để ngăn tái phát.

**History rewriting không thay cho revoke.** Những bản sao ngoài tầm kiểm soát có thể vẫn chứa secret.

### 3.5. Secret scanning nhiều tầng

Nên scan pre-commit/push, PR/MR, protected branches, history theo policy và **actual build artifacts**. Một scanner có thể miss token đã mã hóa/chia nhỏ trong binary hoặc false-positive trên public cert; findings cần review và redact, không copy raw secret vào issue công khai.

---

## 4. Không hardcode vào Java, Groovy, Kotlin hoặc resources

### 4.1. Anti-pattern Gradle

~~~groovy
// Phản ví dụ — đây chỉ là chuỗi giả, không được thay bằng secret thật.
repositories {
    maven {
        url = uri('https://repo.example.invalid/private')
        credentials {
            username = 'demo'
            password = 'DUMMY_NOT_A_REAL_SECRET'
        }
    }
}
~~~

Nếu real password được commit vào build.gradle, Git history và PR diffs đã lưu nó. Không phải chỉ khi build chạy mới có rò rỉ.

### 4.2. Java private modifier không bảo vệ secret khỏi người có JAR

~~~java
public final class BadConfig {
    private static final String TOKEN =
            "DUMMY_NOT_A_REAL_SECRET";
}
~~~

Compiled class có thể chứa string constant. Người nhận JAR có thể decompile hoặc dùng binary string scanner. **private** chỉ là visibility trong Java, không là encryption. Obfuscation cũng không làm hardcoded production token trở nên an toàn.

### 4.3. Resource packaging

Nếu secret được lưu dưới:

~~~text
src/main/resources/application.properties
src/main/resources/.env
src/main/resources/private-key.asc
~~~

nó có thể đi vào `processResources → jar → distZip` và Maven artifacts. Application resource có thể chứa **public defaults**, nhưng production secrets phải được inject khi chạy ứng dụng hoặc deploy, không nằm trong source/resources.

Generated source/resources, JAR manifest, POM, sourcesJar, javadocJar và shaded JAR cũng cần được kiểm tra. Không dùng `from(projectDir)` tùy tiện trong `jar`/`zip` tasks.

### 4.4. Test fixtures và reports

Tests có thể ghi HTTP Authorization headers, cookies, snapshot từ production, exception messages chứa tokens hoặc internal certificates. JUnit XML/HTML có thể giữ stdout. CI masking của console **không tự làm sạch test report files**. Dùng synthetic fixtures và redact ở nguồn.

---

## 5. Gradle User Home và Provider API

### 5.1. GRADLE_USER_HOME không phải public artifact

Mặc định là `~/.gradle` trên Unix và `.gradle` ở user profile trên Windows. Có thể chứa:
- `gradle.properties` của user.
- Gradle Wrapper distributions.
- Init scripts trong init.d.
- Daemon logs.
- Dependency and Build Cache.
- Key/configuration state.

User-level `gradle.properties` thường là **plain text**, không phải secret vault mã hóa. Với file thuộc user hiện tại trên Linux/macOS:

~~~bash
chmod 700 ~/.gradle
chmod 600 ~/.gradle/gradle.properties
~~~

Windows phải dùng NTFS ACL. Không dùng chung Gradle User Home giữa các trust domains hoặc upload nguyên thư mục như public CI artifact.

### 5.2. Environment injection qua CI secret store

GitLab CI/CD Variables, Jenkins Credentials, Vault hoặc workload identity có thể cấp credentials chỉ trong job có quyền. Tránh đặt actual values trong `.gitlab-ci.yml`, `Jenkinsfile`, root gradle.properties hoặc shell history.

Env variables vẫn có thể bị process cùng OS user/privileged code đọc; vì vậy **trusted runner isolation** và least privilege quan trọng không kém việc che console output.

### 5.3. Project properties Gradle từ environment

Gradle nhận env names dạng:

~~~text
ORG_GRADLE_PROJECT_myProperty
~~~

thành project property `myProperty`. Với repository identity `privateReleases`, CI sẽ dùng:

~~~text
ORG_GRADLE_PROJECT_privateReleasesUsername
ORG_GRADLE_PROJECT_privateReleasesPassword
~~~

Không có real credentials trong tên biến.

### 5.4. Provider API

~~~groovy
def channel = providers.gradleProperty('releaseChannel')
    .orElse('snapshot')

def endpoint = providers.environmentVariable('PUBLIC_ENDPOINT')
    .orElse('https://api.example.invalid')
~~~

Đây là ví dụ **public config**. Providers giúp lazy resolution, nhưng nếu `println provider.get()` với password hoặc đặt secret vào task outputs, nó vẫn rò. Với Maven credentials hãy ưu tiên Gradle typed credentials API.

### 5.5. Không truyền secret ở command line

~~~bash
# Phản ví dụ: dummy string, không dùng real password.
./gradlew publish -PreleasePassword=DUMMY_NOT_A_REAL_SECRET
~~~

Real secret ở -P/-D, URL user:token@host hoặc shell command có Authorization literal có thể xuất hiện trong process listing, shell history và logs. Chuyển sang secret store/environment hoặc Gradle credential providers.

---

## 6. Gradle PasswordCredentials: đúng repository identity

### 6.1. Groovy DSL cho dependency repository

~~~groovy
repositories {
    maven {
        name = 'privateDependencies'
        url = uri('https://repo.example.invalid/maven')
        credentials(PasswordCredentials)
    }
}
~~~

Gradle nhận repository name `privateDependencies` làm prefix, tự lookup:
- `privateDependenciesUsername`
- `privateDependenciesPassword`

CI có thể cấp thông qua:

~~~text
ORG_GRADLE_PROJECT_privateDependenciesUsername
ORG_GRADLE_PROJECT_privateDependenciesPassword
~~~

URL example.invalid không phải server để truy cập thật.

### 6.2. Groovy DSL cho publishing repository

Project cần áp `maven-publish` trước:

~~~groovy
publishing {
    repositories {
        maven {
            name = 'privateReleases'
            url = uri('https://repo.example.invalid/releases')
            credentials(PasswordCredentials)
        }
    }
}
~~~

Lookup theo:
- `privateReleasesUsername`
- `privateReleasesPassword`

Không ghi giá trị password vào build script. **Read-only** dependency repository identity và **write** publishing identity cần được tách. Creds có thể chỉ được yêu cầu khi task thực sự cần private repository.

### 6.3. Kotlin DSL tương đương

~~~kotlin
repositories {
    maven {
        name = "privateDependencies"
        url = uri("https://repo.example.invalid/maven")
        credentials(PasswordCredentials::class)
    }
}

publishing {
    repositories {
        maven {
            name = "privateReleases"
            url = uri("https://repo.example.invalid/releases")
            credentials(PasswordCredentials::class)
        }
    }
}
~~~

Đoạn `publishing` chỉ hợp lệ trong project áp `maven-publish`. Typed Gradle credentials giúp lookup/redact trong Gradle-managed diagnostics, nhưng plugin độc hại vẫn có thể đọc env theo OS permissions; nó không phải sandbox.

### 6.4. HTTP header authentication

Một số repository dùng HTTP header token thay Basic username/password. Gradle hỗ trợ `HttpHeaderCredentials`/`HttpHeaderAuthentication`. Chọn đúng server API, không nhét token vào URL query hay userinfo. Nếu provider hỗ trợ short-lived identity/OIDC, ưu tiên khi phù hợp.

---

## 7. Private signing key và Gradle Signing Plugin

### 7.1. Chữ ký không mã hóa JAR

Digital signature cho phép xác minh artifact gắn với signing identity và nội dung không bị sửa sau khi ký theo trust model; nó **không che file contents**. Một artifact bị hardcode password vẫn lộ dù có chữ ký hợp lệ.

- **Private key** và **passphrase** phải giữ kín.
- **Public key/fingerprint** thường có thể phân phối để verify.
- **Signature .asc** của artifact thường là output công khai.
- File `.asc` có thể chứa armored private key; cần phân loại bằng nội dung.

### 7.2. Signing publication từ environment

Trong Java project:

~~~groovy
plugins {
    id 'java'
    id 'maven-publish'
    id 'signing'
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}

signing {
    def privateKey =
        providers.environmentVariable('SIGNING_KEY').orNull
    def passphrase =
        providers.environmentVariable('SIGNING_PASSWORD').orNull

    useInMemoryPgpKeys(privateKey, passphrase)
    sign publishing.publications.mavenJava
}
~~~

CI cần cấp ASCII-armored private key và passphrase từ protected secrets store trong release stage. Không commit vào Git, không ghi private keyring xuống build/ và không archive credentials.

### 7.3. Fail closed khi release đòi chữ ký

Không viết logic “key vắng thì bỏ qua sign rồi publish unsigned” nếu release policy yêu cầu signed artifacts. Trong release script đã được cấp secrets:

~~~bash
test -n "$SIGNING_KEY"
test -n "$SIGNING_PASSWORD"
./gradlew --no-configuration-cache \
    publishMavenJavaPublicationToPrivateReleasesRepository
~~~

Fragment này chỉ chạy khi thật sự có Maven publication, protected repo, ký và CI credentials. Chạy `--no-configuration-cache` có thể hợp lý cho release chưa audit configuration state; nó không loại bỏ key khỏi JVM process memory.

### 7.4. gpg-agent và subkeys

Gradle còn hỗ trợ:

~~~groovy
signing {
    useGpgCmd()
    sign publishing.publications.mavenJava
}
~~~

Cần GnuPG, gpg-agent, key selection và trusted machine. Signing subkey thay master private key có thể thu hẹp phạm vi compromise và dễ revoke/rotate hơn. In-memory signing không bảo đảm secrets không bị plugin khác capture; vẫn phải cô lập Gradle process.

---

## 8. Artifact, logs và cache: kiểm đầu ra thật

### 8.1. Không đóng gói cả project root

~~~groovy
// Phản ví dụ nguy hiểm:
tasks.named('jar') {
    from(projectDir)
}
~~~

Cấu hình này có thể lấy local config, .env và key file vào JAR. Ưu tiên output từ Java sourceSet và explicit allowlist. `exclude` globs có thể giảm lỗi tên file nhưng không ngăn Java class constants hoặc secret bên trong file có tên bình thường.

### 8.2. Scope cần audit

- build/libs JARs, application distribution ZIP/TAR.
- sourcesJar, javadocJar, shaded artifacts.
- POM/Gradle Module Metadata/manifests.
- Generated resources.
- Test XML/HTML, coverage reports, log files.
- Docker build context và image layers.
- CI artifacts và Maven registry publications.

Scan **actual bytes trước upload**, không chỉ Git diff. Một public artifact có thể chứa secret không xuất hiện ở console.

### 8.3. Log/Build Scan

Không `println` token, không log credentials qua `logger.lifecycle`, error messages, request dumps, test assertion outputs. GitLab/Jenkins masking chỉ giảm rò qua một số console patterns, không tự scan reports/binaries. Build Scan có thể publish metadata/logs/custom values ra dịch vụ bên ngoài: kiểm access control, redaction và retention.

### 8.4. Gradle Build Cache

Build Cache lưu task outputs. Một cacheable task tạo file chứa token sẽ khiến remote/local cache có thể lưu token và phân phối lại. Không viết secret vào @OutputFile/@OutputDirectory; không đánh dấu secret-bearing side-effect task là cacheable.

### 8.5. Configuration Cache

Configuration Cache có thể lưu sensitive configuration/task graph state. Gradle có cơ chế encryption ở các versions hiện đại, nhưng phải bảo vệ directory/key/Gradle User Home và không đưa state vào shared untrusted CI cache. Review plugins bắt giữ secret lúc configuration; cân nhắc tắt cache cho release khi chưa audit.

### 8.6. Remote cache trust

Untrusted PR builds không có quyền push trusted remote Build Cache, vì cache poisoning có thể cung cấp output giả. Dùng ACL, authentication và trusted/untrusted cache namespaces tách biệt.

---

## 9. Lab Java 17 đầy đủ: build một artifact công khai

Lab không dùng token/password/key thật. Nó tạo **public report**, kiểm text và build distribution ZIP, để thấy khác nhau giữa source inputs và actual outputs.

### 9.1. File tree

~~~text
safe-artifact-demo/
├── settings.gradle
├── build.gradle
├── .gitignore
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── src/main/java/demo/SafeRelease.java
└── tools/ArchiveNameAudit.java
~~~

Gradle Wrapper phải được tạo từ Gradle tin cậy hoặc lấy từ repository đã xác minh; không tự viết gradle-wrapper.jar. Sử dụng JDK17 và Wrapper tương thích.

### 9.2. settings.gradle

~~~groovy
rootProject.name = 'safe-artifact-demo'
~~~

### 9.3. build.gradle

~~~groovy
plugins {
    id 'application'
    id 'maven-publish'
}

group = 'demo.security'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

application {
    mainClass = 'demo.SafeRelease'
}

def reportFile = layout.buildDirectory.file(
    'reports/public-release.txt'
)

tasks.register('createPublicReport', JavaExec) {
    group = 'verification'
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'demo.SafeRelease'
    args reportFile.get().asFile.absolutePath
    outputs.file(reportFile)
}

tasks.register('verifyPublicReport') {
    group = 'verification'
    dependsOn tasks.named('createPublicReport')
    inputs.file(reportFile)

    doLast {
        def actual = reportFile.get().asFile.getText('UTF-8')
        def expected =
            'component=safe-artifact-demo\nversion=1.0.0\n'

        if (actual != expected) {
            throw new GradleException(
                'Public report does not match approved content'
            )
        }
        println 'PUBLIC_REPORT_VERIFIED'
    }
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
~~~

**application** cung cấp Java source set, runtime classpath và `distZip`; **maven-publish** có local publication, chưa có remote credentials. `createPublicReport` chỉ sinh public metadata, `verifyPublicReport` kiểm nội dung chuẩn.

### 9.4. src/main/java/demo/SafeRelease.java

~~~java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class SafeRelease {
    private SafeRelease() {
    }

    public static void main(String[] args)
            throws IOException {

        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: SafeRelease <output-file>"
            );
        }

        Path output = Path.of(args[0])
                .toAbsolutePath().normalize();
        Path parent = output.getParent();

        if (parent != null) {
            Files.createDirectories(parent);
        }

        String text =
                "component=safe-artifact-demo\n"
                + "version=1.0.0\n";

        Files.writeString(
                output,
                text,
                StandardCharsets.UTF_8
        );

        System.out.println("PUBLIC_REPORT_CREATED");
    }
}
~~~

**Java17 runnable**, không đọc env secrets và không đưa absolute output path vào public file content.

### 9.5. .gitignore

~~~gitignore
.gradle/
build/
out/
.env
.env.*
!.env.example
.local-secrets/
*.p12
*.pfx
*.keystore
~~~

### 9.6. Lệnh chạy Gradle

Linux/macOS:

~~~bash
chmod +x ./gradlew
./gradlew clean verifyPublicReport distZip
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean verifyPublicReport distZip
~~~

Trong clean run, stdout do code và task action in:

~~~text
PUBLIC_REPORT_CREATED
PUBLIC_REPORT_VERIFIED
~~~

Gradle còn task logs/BUILD SUCCESSFUL. Sau lần đầu, Gradle có thể đánh dấu createPublicReport UP-TO-DATE, nên không in lại dòng action.

File:

~~~text
build/reports/public-release.txt
~~~

nội dung chính xác:

~~~text
component=safe-artifact-demo
version=1.0.0
~~~

Application distribution thông thường:

~~~text
build/distributions/safe-artifact-demo-1.0.0.zip
~~~

ZIP bao gồm start scripts/JAR, không tự chứa tất cả các files trong build/. Chỉ audit file sẽ thực sự upload.

### 9.7. Java chạy độc lập với javac

Linux/macOS:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
    -d out src/main/java/demo/SafeRelease.java
java -cp out demo.SafeRelease out/public-release.txt
cat out/public-release.txt
~~~

Stdout:

~~~text
PUBLIC_REPORT_CREATED
component=safe-artifact-demo
version=1.0.0
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out src\main\java\demo\SafeRelease.java
java -cp out demo.SafeRelease out\public-release.txt
Get-Content out\public-release.txt
~~~

### 9.8. Maven local

~~~bash
./gradlew publishToMavenLocal
~~~

Xuất bản publication trong **~/.m2/repository** hoặc Maven local path tương ứng, không gọi remote publishing API, không cần secret. Local publish không thay thế kiểm binary trước khi mang đi release.

---

## 10. Java 17 kiểm tên entry trong JAR/ZIP

Công cụ dưới đây kiểm một số **tên entry nguy hiểm**, không đọc contents. Nó chỉ là heuristic phụ, **không thay thế secret scanner chuyên nghiệp**, không phát hiện token trong .class, nested JAR hoặc file có tên bình thường.

File **tools/ArchiveNameAudit.java**:

~~~java
import java.io.IOException;
import java.util.Enumeration;
import java.util.Locale;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

public final class ArchiveNameAudit {
    private ArchiveNameAudit() {
    }

    public static void main(String[] args)
            throws IOException {

        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ArchiveNameAudit <jar-or-zip>"
            );
        }

        boolean suspicious = false;

        try (ZipFile archive = new ZipFile(args[0])) {
            Enumeration<? extends ZipEntry> entries =
                    archive.entries();

            while (entries.hasMoreElements()) {
                String name = entries.nextElement()
                        .getName()
                        .replace('\\', '/')
                        .toLowerCase(Locale.ROOT);

                if (name.equals(".env")
                        || name.contains("/.env")
                        || name.endsWith("gradle.properties")
                        || name.endsWith(".p12")
                        || name.endsWith(".pfx")
                        || name.endsWith(".keystore")
                        || name.endsWith("/id_rsa")
                        || name.endsWith("/id_ed25519")) {
                    suspicious = true;
                }
            }
        }

        if (suspicious) {
            throw new IllegalStateException(
                    "Disallowed archive entry name detected"
            );
        }

        System.out.println("ARCHIVE_NAME_AUDIT_OK");
    }
}
~~~

Compile và chạy sau build:

~~~bash
javac --release 17 -encoding UTF-8 -d out \
    tools/ArchiveNameAudit.java

java -cp out ArchiveNameAudit \
    build/libs/safe-artifact-demo-1.0.0.jar

java -cp out ArchiveNameAudit \
    build/distributions/safe-artifact-demo-1.0.0.zip
~~~

Với layout của lab, mỗi lần audit in:

~~~text
ARCHIVE_NAME_AUDIT_OK
~~~

Nếu có entry name match rule, nó ném IllegalStateException không dump secret content. Chỉ pass filename check không chứng minh artifact không có secret. Production cần scan binary contents, nested archives, manifests/POM và reports với redaction và size/depth limits.

---

## 11. Kotlin DSL tương đương

Java files không đổi. settings.gradle.kts:

~~~kotlin
rootProject.name = "safe-artifact-demo"
~~~

build.gradle.kts:

~~~kotlin
plugins {
    application
    id("maven-publish")
}

group = "demo.security"
version = "1.0.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
    options.encoding = "UTF-8"
}

application {
    mainClass = "demo.SafeRelease"
}

val reportFile = layout.buildDirectory.file(
    "reports/public-release.txt"
)

val createPublicReport = tasks.register<JavaExec>(
    "createPublicReport"
) {
    group = "verification"
    classpath = sourceSets.main.get().runtimeClasspath
    mainClass = "demo.SafeRelease"
    args(reportFile.get().asFile.absolutePath)
    outputs.file(reportFile)
}

tasks.register("verifyPublicReport") {
    dependsOn(createPublicReport)
    inputs.file(reportFile)

    doLast {
        val actual = reportFile.get().asFile.readText(
            Charsets.UTF_8
        )
        val expected =
            "component=safe-artifact-demo\nversion=1.0.0\n"
        if (actual != expected) {
            throw GradleException(
                "Public report does not match approved content"
            )
        }
        println("PUBLIC_REPORT_VERIFIED")
    }
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }
}
~~~

Không giữ cả Groovy và Kotlin settings/build files có nội dung mâu thuẫn. Kotlin release signing fragment:

~~~kotlin
plugins {
    id("maven-publish")
    signing
}

signing {
    val key =
        providers.environmentVariable("SIGNING_KEY").orNull
    val passphrase =
        providers.environmentVariable("SIGNING_PASSWORD").orNull
    useInMemoryPgpKeys(key, passphrase)
    sign(publishing.publications["mavenJava"])
}
~~~

Cần publication mavenJava và protected signing stage.

---

## 12. GitLab: protected variables thay YAML plaintext

Tạo variables trong GitLab CI/CD Variables hoặc secret manager:

~~~text
ORG_GRADLE_PROJECT_privateReleasesUsername
ORG_GRADLE_PROJECT_privateReleasesPassword
SIGNING_KEY
SIGNING_PASSWORD
~~~

Chỉ tên biến được ghi vào tài liệu, actual values do admin cấp; chọn protected/masked/file-type phù hợp. Không cấp release credentials cho fork MR hoặc untrusted code.

Release job fragment:

~~~yaml
release_maven:
  stage: release
  image: eclipse-temurin:17-jdk
  rules:
    - if: '$CI_COMMIT_TAG'
      when: manual
    - when: never
  script:
    - chmod +x ./gradlew
    - ./gradlew --no-daemon --no-configuration-cache publishMavenJavaPublicationToPrivateReleasesRepository
~~~

Cần pipeline stages, trusted runner/protected tags, repository thật, publication và permission policy. `when: manual` không thay server-side protection. Không dùng artifacts paths toàn repo hoặc cache cả GRADLE_USER_HOME chứa secrets.

---

## 13. Jenkins: withCredentials + isolated agent

Jenkins admin tạo credential ID **private-repo-release** kiểu username/password. Declarative Pipeline fragment:

~~~groovy
pipeline {
    agent { label 'trusted-release-linux' }

    stages {
        stage('Verify') {
            steps {
                sh './gradlew --no-daemon check'
            }
        }

        stage('Release') {
            when {
                buildingTag()
            }
            steps {
                withCredentials([
                    usernamePassword(
                        credentialsId: 'private-repo-release',
                        usernameVariable:
                            'ORG_GRADLE_PROJECT_privateReleasesUsername',
                        passwordVariable:
                            'ORG_GRADLE_PROJECT_privateReleasesPassword'
                    )
                ]) {
                    sh '''
                        set +x
                        ./gradlew --no-daemon --no-configuration-cache publishMavenJavaPublicationToPrivateReleasesRepository
                    '''
                }
            }
        }
    }
}
~~~

Requires Linux shell, Jenkins Pipeline/Credentials plugin, JDK/Wrapper, SCM tag context, Maven publication và protected permission. Windows agent phải dùng bat/gradlew.bat. Single-quoted Groovy sh tránh interpolate secrets thành command string trước khi shell nhận. **withCredentials masking không ngăn plugin độc hại đọc env, không scan artifact contents và không thay runner isolation**.

---

## 14. Release quality gate

~~~text
Untrusted pull/merge request
   -> Checkout + Gradle Wrapper validation
   -> Compile/Test/Check
   -> Build actual JAR/ZIP
   -> Scan source + archives + reports
   -> No signing/publishing credentials

Protected release tag
   -> Checkout verified commit
   -> Test/Check/Build
   -> Scan real artifact bytes
   -> Acquire short-lived scoped credentials
   -> Sign/Publish
   -> Public signature, checksum, provenance
   -> Cleanup runner and expire credentials
~~~

Dùng artifact allowlist, không archive cả project root/Gradle User Home. Nếu muốn publish **đúng bytes đã được test**, dùng artifact handoff với checksum/provenance; đừng build lại tùy tiện rồi giả định output giống hệt. Signatures bảo đảm integrity/identity theo trust policy, không quét secret.

---

## 15. Incident response

Khi phát hiện token/password/private key trong Git hoặc artifact:

1. **Báo ngay security/release owner.**
2. **Revoke/disable credential** theo policy, không đợi cleanup Git history.
3. **Rotate** sang credential mới với scopes hẹp hơn.
4. **Điều tra phạm vi**: commits, forks, tags, logs, Build Scans, CI artifacts/caches, package registry/mirrors, downloads.
5. **Sửa build source**, resource processing, packaging, logging và permissions.
6. **Phối hợp history rewrite** với admins nếu cần; không tự force push repo shared.
7. **Quarantine/purge** artifacts/cache có thể kiểm soát, phát hành bản sửa với provenance.
8. **Audit misuse** và ký giả nếu signing key đã lộ.
9. **Retest bằng synthetic data**, scanner trên actual outputs.
10. **Post-incident review** để ngăn tái diễn.

Nếu private signing key lộ, phải revoke/retire key/subkey, cập nhật trusted public key cho consumers và kiểm chữ ký/artifacts đáng ngờ. **Xóa file key khỏi HEAD không khôi phục trust**.

---

## 16. Troubleshooting

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Maven auth fail | Repo name/env prefix sai | Kiểm property names, không in values |
| Test bắt buộc phải có publish password | Credential lookup quá sớm | Chỉ yêu cầu trên publish tasks |
| .env bị ignore nhưng ZIP chứa | Task copy project root | Whitelist inputs, scan artifact |
| Token đã xóa khỏi Git HEAD nhưng còn | Commit history | Revoke, coordinated cleanup |
| JAR có token | Java constant/resource | Rotate, loại source, rebuild và scan |
| Signing Plugin không tìm key | Missing CI bindings/gpg-agent | Kiểm presence và permissions |
| Release unsigned dù required | Fail-closed gate thiếu | Chặn publish nếu key vắng |
| JUnit XML chứa Authorization | Test logging thiếu redaction | Sanitize ở nguồn, purge files |
| Build Scan có token | Logger/custom values leak | Restrict scan, rotate |
| Jenkins secret trong command | Groovy interpolation/trace | Single-quoted sh, set +x |
| GitLab masked var vẫn rò | Binary artifact/encoded output | Scan actual files, rotate |
| Build Cache chứa secret | Task outputs nhạy cảm | Purge, sửa task, revoke |
| Configuration Cache nhạy cảm | Plugin capture secret | Isolate storage/key và audit plugin |
| Audit filenames PASS nhưng scanner FAIL | Token trong binary/nested JAR | Dùng content scanner |
| Gradle User Home bị archive | CI glob quá rộng | Restrict paths, clean up |
| PR có publish rights | CI trust policy sai | Protected refs/runner/credentials |
| Signing key đã lộ | Key compromise | Revoke/rotate và audit signatures |

---

## 17. Bài tập có đáp án

### Bài 1. .env đã .gitignore có thể vào ZIP không?

**Đáp án:** Có. Gradle task có thể đọc file untracked. Quét actual archive.

### Bài 2. Commit A có token, commit B xóa. Có cần revoke?

**Đáp án:** Có. Token vẫn ở Git history/forks/clones.

### Bài 3. privateReleases PasswordCredentials tìm property names?

**Đáp án:** privateReleasesUsername và privateReleasesPassword.

### Bài 4. Cần đặt env names nào?

**Đáp án:** ORG_GRADLE_PROJECT_privateReleasesUsername và ORG_GRADLE_PROJECT_privateReleasesPassword.

### Bài 5. ~/.gradle/gradle.properties có tự mã hóa không?

**Đáp án:** Không; thường là plain text, dùng ACL/secret store.

### Bài 6. Root gradle.properties có thể commit không?

**Đáp án:** Có nếu chỉ chứa public settings và policy cho phép.

### Bài 7. Java private static final TOKEN có che khỏi người có JAR?

**Đáp án:** Không; class bytecode có thể decompile.

### Bài 8. OpenPGP public key có phải secret?

**Đáp án:** Không; private key/passphrase là secret.

### Bài 9. Signing có mã hóa artifact không?

**Đáp án:** Không; signature không che bytes.

### Bài 10. useInMemoryPgpKeys có bảo đảm key không nằm trong process memory?

**Đáp án:** Không; nó chính là cách cung cấp key trong process memory.

### Bài 11. Release thiếu signing key khi policy bắt buộc?

**Đáp án:** Fail closed, không publish unsigned.

### Bài 12. GitLab masked variable có redact JUnit XML không?

**Đáp án:** Không tự động; sanitize files trước artifacts upload.

### Bài 13. Jenkins sh nên dùng single-quoted Groovy string vì sao?

**Đáp án:** Tránh Groovy interpolation của secrets vào command arguments.

### Bài 14. Gradle Build Cache có thể chứa token?

**Đáp án:** Có khi task output chứa token; không cache secret-bearing output.

### Bài 15. Configuration Cache encrypted có nghĩa có thể public archive?

**Đáp án:** Không; storage/key/ACL vẫn cần bảo vệ.

### Bài 16. ArchiveNameAudit PASS có nghĩa mọi token an toàn?

**Đáp án:** Không; tool chỉ kiểm filename entries.

### Bài 17. Lab Java in stdout nào?

**Đáp án:** PUBLIC_REPORT_CREATED; verifyPublicReport in PUBLIC_REPORT_VERIFIED.

### Bài 18. Public report trong lab chứa gì?

**Đáp án:** Hai dòng component=safe-artifact-demo và version=1.0.0.

### Bài 19. publishToMavenLocal cần remote password?

**Đáp án:** Không trong lab. Chỉ ghi Maven local repository.

### Bài 20. Untrusted PR nên được cấp publish credentials?

**Đáp án:** Không. Tách trusted release jobs và least privilege.

### Bài 21. Rewriting history thay được rotation?

**Đáp án:** Không. Forks/backups vẫn có thể giữ secret và credential còn hiệu lực.

### Bài 22. Docker image có thể chứa key dù Git sạch?

**Đáp án:** Có khi build context/layers đã copy private file.

### Bài 23. Test fixtures dùng production secret có phù hợp?

**Đáp án:** Không. Dùng synthetic data không có quyền thật.

### Bài 24. Signing private key lộ thì sao?

**Đáp án:** Revoke/retire, cấp key mới, cập nhật trust và audit signatures.

### Bài 25. Kiểm gì trước publish?

**Đáp án:** Tests, source scan, actual artifact/report content scan, provenance, signing credentials và release permissions.

---

## 18. Checklist trước merge/release

- [ ] Không có token/password/private key trong Git diff/history chưa xử lý?
- [ ] .gitignore phù hợp, không bỏ Gradle Wrapper?
- [ ] Không hardcode credential trong Java/Gradle scripts/resources?
- [ ] Test fixtures không dùng production credentials?
- [ ] GRADLE_USER_HOME/gradle.properties có ACL riêng?
- [ ] Maven repositories dùng HTTPS và typed credentials?
- [ ] Read-only dependency credential tách khỏi publish identity?
- [ ] CI secret store cấp credentials chỉ trong protected release?
- [ ] Untrusted PR/MR không chạy trên agent có production key?
- [ ] Signing key/passphrase không trong Git/log/artifact?
- [ ] Signing requirement fail closed?
- [ ] Không truyền real secret bằng -P/-D/URL hoặc echo?
- [ ] JAR/ZIP/sourcesJar/javadocJar/POM/test reports được scan?
- [ ] Không archive cả project root hay Gradle User Home?
- [ ] Build Cache/Configuration Cache được bảo vệ khỏi secret-bearing data?
- [ ] Remote cache trusted writers, untrusted readers cách ly?
- [ ] Không in key qua --debug, Build Scan hoặc test reports?
- [ ] Artifacts có commit/version/checksum/provenance?
- [ ] Release chỉ chạy sau test/security gate?
- [ ] Có incident response: revoke, rotate, cleanup và audit?

## 19. Tài liệu chính thức

- [Gradle — Securing the Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html): Wrapper, plugins, Gradle User Home, credentials và caches.
- [Gradle — Securing Repositories](https://docs.gradle.org/current/userguide/securing_repositories.html): repository policy.
- [Gradle — Supported Repository Protocols](https://docs.gradle.org/current/userguide/supported_repository_protocols.html): PasswordCredentials, lookup by repository name.
- [Gradle — Build Environment](https://docs.gradle.org/current/userguide/build_environment.html): ORG_GRADLE_PROJECT_*, gradle.properties và Provider API.
- [Gradle — Signing Plugin](https://docs.gradle.org/current/userguide/signing_plugin.html): useInMemoryPgpKeys, gpg-agent và signed publications.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): sensitive configuration state.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): task outputs và remote cache.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): publication metadata/artifacts.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): distZip.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): version pinning/verification.
- [GitLab — CI/CD Variables](https://docs.gitlab.com/ci/variables/): masked/protected variables.
- [GitLab — Job Artifacts](https://docs.gitlab.com/ci/jobs/job_artifacts/): artifact permissions and retention.
- [Jenkins — Credentials Binding](https://www.jenkins.io/doc/pipeline/steps/credentials-binding/): withCredentials và shell interpolation caveats.
- [Jenkins — Pipeline Syntax](https://www.jenkins.io/doc/book/pipeline/syntax/): protected release stages.
- [GitHub — Removing Sensitive Data](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository): history cleanup và risk.

**Kết luận:** Không commit secret mới chỉ là lớp đầu tiên. Hãy cấp credential từ **secret store**, dùng **typed Gradle credentials** và signing backend có trust boundary; không đưa secret vào **Git history, resources, JAR/ZIP, reports, logs, Build Scan hoặc caches**. Quét chính outputs sẽ upload và chỉ cho protected release jobs có quyền ký/publish. Nếu đã lộ, **revoke/rotate trước**, xử lý artifacts/history và tăng cường policy để tránh tái diễn.
