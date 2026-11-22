# Giữ bí mật khóa ký và thông tin xác thực ngoài kho mã khi phát hành Maven

## 1. Vì sao phát hành Maven không được đặt secrets trong Git?

Một bản phát hành Maven có thể cần **ký artifact** và **đăng tải artifact**. Hai bước này sử dụng bí mật khác nhau:

- **Khóa ký riêng (private signing key)** dùng để tạo chữ ký OpenPGP/GPG cho JAR, POM và các artifact đính kèm.
- **Passphrase** dùng để mở khóa private key đã được bảo vệ.
- **Repository credentials** như upload token, username/password hoặc credential tạm thời cho phép gửi artifact lên kho Maven.
- **SCM credentials** có thể cần khi tạo tag/đẩy commit trong một release workflow; chúng không phải repository credentials.

Nếu một khóa ký riêng bị lộ, kẻ tấn công có thể ký artifact giả dưới danh tính khóa đó. Nếu token deploy bị lộ, họ có thể upload artifact theo quyền token. Nếu cả hai bị lộ, khả năng giả mạo một bản phát hành được người dùng tin tưởng tăng lên đáng kể.

**Nguyên tắc:** source Git giữ cấu hình có thể chia sẻ, còn secret material phải do **secret vault, keyring, HSM, gpg-agent hoặc CI protected secret** cấp cho đúng người/job vào đúng thời điểm. Không chép khóa riêng, passphrase hay token vào `pom.xml` để tiện debug.

Mục tiêu học tập:

1. Nhận diện đúng từng loại bí mật trong build/release.
2. Phân biệt `distributionManagement` trong POM với `<servers>` trong Maven `settings.xml`.
3. Dùng Maven GPG Plugin 3.2.8 với `bestPractices=true`, GnuPG keyring và passphrase an toàn.
4. Hiểu giới hạn bảo vệ mật khẩu của Maven 3 và cơ chế Maven 4.
5. Build project Java 17/JUnit 5 hoàn chỉnh mà **không cần secret**; chỉ bật ký ở profile phát hành.
6. Thiết kế CI tránh lộ private key, password/token qua log, CLI, Docker layers và artifact uploads.
7. Kiểm chữ ký bằng public key/fingerprint từ kênh đáng tin, ứng phó khi secret bị lộ.

## 2. Phân loại: bí mật và metadata được phép công bố

| Dữ liệu | Có bí mật không? | Nơi thích hợp |
| --- | --- | --- |
| `groupId`, `artifactId`, `version` | Không | `pom.xml` |
| Maven repository `id` | Không | `pom.xml` và `settings.xml` |
| Hosted repository URL | Thường không; có thể nội bộ | POM/cấu hình được phê duyệt |
| GPG **public key** | Không | Trang release/keyserver/kênh công khai |
| GPG **fingerprint** | Không | Release metadata, kênh xác minh |
| GPG **private key** | **Có** | Keyring/HSM/secret manager, ngoài Git |
| Passphrase của private key | **Có** | `gpg-agent`/pinentry hoặc protected CI secret |
| Token deploy Maven | **Có** | Protected Maven settings/CI secret store |
| SCM push token | **Có** | VCS credential manager hoặc CI scoped token |
| Maven 3 encrypted password | **Vẫn nhạy cảm** | Protected settings + master key riêng |
| SHA-256 checksum | Không | Release manifest, kiểm với nguồn tin cậy |

Một chữ ký `.asc` thường là **public artifact** để người tiêu thụ kiểm tra tính toàn vẹn/chủ thể ký, chứ không phải secret. Không nhầm file **detached signature** với file **private key** chỉ vì cùng có đuôi `.asc`.

### 2.1. GPG private key khác GPG passphrase

Private key chứa khóa dùng tạo chữ ký. Passphrase bảo vệ việc mở private key đã được lưu mã hóa. Giữ riêng hai yếu tố có ích, nhưng **passphrase không biến việc commit private key thành an toàn**: Git có lịch sử và nhiều bản sao; thuật toán/passphrase/config có thể yếu hoặc bị lộ ở nơi khác.

Public key tương ứng có thể được công bố. Người xác minh phải đối chiếu **fingerprint chính xác** qua kênh họ tin tưởng. Chữ ký hợp lệ với một public key tùy ý mới lấy từ cùng nơi không chứng minh artifact do đúng nhà phát hành tạo.

## 3. Luồng phát hành và ranh giới tin cậy

~~~text
Git repository (không có secret)
  |
  |-- pom.xml: GAV, plugin versions, profile ký,
  |            repository ID/URL không nhạy cảm
  |-- src/main, src/test
  |
  v
Build job (JDK/Maven cố định)
  |
  +-- compile -> test -> package -> verify
  |       artifact JAR, POM, test reports
  |
  +-- Signature step (protected release job)
  |       private key: keyring/HSM/vault
  |       unlock: agent/pinentry hoặc CI secret env
  |       -> gpg:sign -> detached signatures (*.asc)
  |
  +-- Publishing step (restricted upload permission)
          settings.xml: <server id=...>
          token: secret store
          -> Maven deploy / approved publishing plugin
          -> Maven hosted repository
  |
  v
Consumer
  +-- lấy artifact + chữ ký
  +-- xác minh bytes với public key/fingerprint đáng tin
~~~

**Chữ ký và quyền deploy là hai lớp riêng.** HTTPS/token bảo vệ kết nối và quyền upload; chữ ký OpenPGP giúp consumer kiểm bytes/danh tính khóa ký. Một JAR được ký **không tự an toàn về logic, malware, license hay vulnerability**.

Nếu một CI job có thể chạy code không đáng tin với private key và deploy token đã inject, việc giữ key ngoài Git **không ngăn được code độc hại trong job lấy secrets**. Vì vậy phải bảo vệ cả trust boundary của job.

## 4. Những anti-pattern cần tránh

Không đặt secret vào POM:

~~~xml
<!-- PHẢN VÍ DỤ: tuyệt đối không dùng giá trị thật -->
<properties>
    <gpg.passphrase>UNSAFE_REAL_PASSPHRASE</gpg.passphrase>
    <repo.password>UNSAFE_REAL_DEPLOY_TOKEN</repo.password>
</properties>
~~~

Không truyền passphrase lên command line:

~~~bash
# PHẢN VÍ DỤ: không chạy với secret thật
mvn -Dgpg.passphrase=UNSAFE_SECRET deploy
~~~

Không commit những tệp sau:

~~~text
private-signing-key.asc
secret-key.gpg
secring.gpg
settings.xml có deploy token
settings-security.xml hoặc settings-security4.xml nhạy cảm
.env chứa mật khẩu/token
.mvn/maven.config chứa -Dpassword hoặc -Dtoken
src/main/resources/secrets.properties
Dockerfile với ENV TOKEN=real-value hoặc COPY private-key
~~~

Các đường rò rỉ thường gặp:
- Git history, pull request diffs, forks, Git caches.
- Shell history/process command line.
- Maven `-X` logs và test reports.
- Debug dumps từ custom Maven plugins.
- CI environment dumps, logs, cache và artifact uploads.
- Docker image layers và build cache.
- Resource filtering vô tình đóng gói một environment secret vào JAR.
- Các runners được dùng lại giữa trusted và untrusted jobs.

**`.gitignore` chỉ ngăn những tệp chưa tracked được thêm một cách thông thường.** Nó không xóa một secret đã nằm trong commit history hay CI artifacts.

## 5. `pom.xml` chứa repository đích, không chứa mật khẩu

Với Maven Deploy Plugin chạy qua lifecycle, cấu hình POM thường có:

~~~xml
<distributionManagement>
    <repository>
        <id>internal-releases</id>
        <url>https://repo.example.invalid/repository/releases/</url>
    </repository>
    <snapshotRepository>
        <id>internal-snapshots</id>
        <url>https://repo.example.invalid/repository/snapshots/</url>
    </snapshotRepository>
</distributionManagement>
~~~

**Đây là mảnh POM minh họa**. `repo.example.invalid` là endpoint không tồn tại; không có hành động publish thực. Khi dùng thật phải thay bằng URL được administrator phê duyệt và repository đã được cấp quyền.

Ba khái niệm:

- `<repositories>`: nơi Maven tải project dependencies.
- `<pluginRepositories>`: nơi Maven tải build plugins.
- `<distributionManagement>`: nơi project artifact được publish khi `mvn deploy`.

**Server ID** như `internal-releases` không phải token. Nó liên kết repository tới entry auth ở Maven settings. Không đặt `https://username:token@host/...` trong URL Git vì URL có thể bị in lại trong log, exception hoặc metadata.

## 6. Maven `settings.xml` theo người dùng hoặc CI

Maven có hai vị trí settings thông dụng:

~~~text
${maven.home}/conf/settings.xml
${user.home}/.m2/settings.xml
~~~

Tệp user settings không thuộc source repository. Một CI job có thể tạo `settings.xml` **tạm** ở một vị trí protected rồi gọi Maven bằng `-s`.

Ví dụ template có **placeholder environment**, không chứa secret literal:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">

    <servers>
        <server>
            <id>internal-releases</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
        <server>
            <id>internal-snapshots</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
~~~

Maven đọc environment references `${env.NAME}` trong settings theo tính năng interpolation; CI phải inject giá trị thực cho process build đúng quyền. Nếu không có env var hoặc token không đủ scope, Maven không tự sinh credential.

**Lưu ý:** template tham chiếu cùng token cho hai ID để minh họa cấu trúc; production nên tách **tokens theo snapshots/releases**, phạm vi quyền và thời hạn nếu repository hỗ trợ.

Một lần triển khai hợp lệ có thể gọi:

~~~bash
mvn -B -s /path/to/protected-settings.xml clean deploy
~~~

Lệnh chỉ diễn giải cú pháp. Chưa thể chạy nó để publish khi chưa có source/POM, repository URL thật, credentials hợp lệ và sự phê duyệt cần thiết.

### 6.1. Bảo vệ quyền tệp

Trên Linux/macOS:

~~~bash
chmod 700 "$HOME/.m2"
chmod 600 "$HOME/.m2/settings.xml"
~~~

Trên Windows sử dụng ACL của filesystem để chỉ account được phép đọc; **không coi `chmod` là biện pháp áp dụng trực tiếp cho NTFS**. Self-hosted CI runner phải có chính sách lifecycle, cô lập và dọn secrets sau mỗi job.

Không upload toàn bộ thư mục `.m2` như một CI artifact. Maven cache dùng để tăng tốc dependency download không nên chứa tệp settings có token hoặc secret cần bảo vệ.

## 7. Maven 3: “encrypted password” không phải secret vault

Maven 3 có hỗ trợ mã hóa password bằng `settings-security.xml` và các lệnh:

~~~bash
mvn --encrypt-master-password
mvn --encrypt-password
~~~

Với bản hỗ trợ tương tác, **không đưa plaintext password vào cùng command**; để Maven hỏi trực tiếp. Kết quả mã hóa sẽ được đặt vào files bảo vệ ở user home theo tài liệu Maven 3.

Ví dụ biểu diễn hình dạng **không phải giá trị thực**:

~~~xml
<settingsSecurity>
    <master>{LOCAL_ENCRYPTED_MASTER_VALUE}</master>
</settingsSecurity>
~~~

Một `settings.xml` khác có thể chứa server password đã mã hóa. **Cả hai file vẫn nhạy cảm.** Tài liệu Maven 3 cảnh báo bảo vệ này chỉ ở mức *obfuscation-grade*; không chống được người tấn công có quyền truy cập các giá trị cần thiết để giải mã.

Không:
- Commit `settings.xml` đã encrypt với suy nghĩ “đã an toàn”.
- Commit cùng lúc settings và `settings-security.xml`.
- Bỏ quyền truy cập thư mục user home.
- Dùng một master key chung không kiểm soát trên nhiều môi trường release.

Ưu tiên protected CI secret store hoặc credential manager hỗ trợ rotate/scope. Mã hóa local là một lớp giảm rủi ro, không thay thế các biện pháp khác.

## 8. Maven 4: cơ chế bảo vệ password mới

Maven 4 có **mvnenc** và các dispatcher/master-key sources mới. Theo tài liệu, cơ chế Master dùng crypto mạnh hơn Maven 3; cấu hình security mới nằm ở `settings-security4.xml`. Một số lệnh hướng dẫn là:

~~~bash
mvnenc init
mvnenc diag
mvnenc encrypt
~~~

Khả năng của Maven 4 gồm các master key sources từ protected file, environment, gpg-agent/pinentry hoặc secret-manager integrations tùy môi trường. **Không bê nguyên `settings-security.xml` và cách thao tác Maven 3 sang Maven 4 rồi coi semantics như nhau.**

Dù mã hóa mạnh hơn, nếu malicious build step hoặc compromised runner có quyền giải mã và gọi repository, token vẫn có thể bị lấy. **Bảo mật phụ thuộc vào cả quyền thực thi code và nguồn secrets**, không chỉ kiểu lưu chuỗi.

Luôn xem `mvn -version` và tài liệu tương ứng Maven major version của team.

## 9. GPG private key, public key và passphrase

- **Private key** tạo chữ ký; phải nằm trong keyring được bảo vệ, HSM hoặc secret vault.
- **Public key** dùng để xác minh chữ ký; có thể phân phối cho consumers.
- **Fingerprint** nhận diện public key cần được xác minh qua một kênh đáng tin.
- **Passphrase** bảo vệ việc sử dụng private key; có thể được `gpg-agent` và `pinentry` xử lý.
- **Revocation/rotation** cần có kế hoạch trước khi key bị mất hoặc compromise.

Kiểm tra GnuPG và metadata khóa trên workstation:

~~~bash
gpg --version
gpg --list-secret-keys --keyid-format LONG
gpg --list-keys --fingerprint
~~~

Các lệnh này không export private signing key. Nếu chưa có key, người được phép có thể thiết lập tương tác:

~~~bash
gpg --full-generate-key
~~~

Chọn thuật toán, thời hạn, identity và passphrase theo chính sách. **Không dùng script ghi passphrase vào source**. Đối với release thực, key generation, backup, rotation/revocation và access cần có owner/audit.

Để phân phối **public key**, có thể dùng:

~~~bash
gpg --armor --export YOUR_VERIFIED_PUBLIC_FINGERPRINT
~~~

Thay tên đại diện bằng fingerprint được kiểm chứng. **Không thay `--export` thành `--export-secret-keys` rồi đưa output vào Git**.

## 10. Maven GPG Plugin 3.2.8 và `bestPractices`

Maven GPG Plugin ký project artifact, POM và các attached artifacts. Goals chính có `gpg:sign`; plugin còn có các goal cho trường hợp ký artifact đã có sẵn. Từ bản 3.2.0, plugin hỗ trợ:

~~~xml
<bestPractices>true</bestPractices>
~~~

Khi bật, một số thực hành truyền secret không an toàn sẽ làm plugin fail thay vì chỉ phát cảnh báo. Maven GPG Plugin 3.2.8 là stable release được tài liệu hóa trong phần này.

### 10.1. Hai đường cung cấp passphrase phù hợp

**Developer workstation:** dùng `gpg-agent` và `pinentry` để người ký mở khóa tương tác; passphrase không cần xuất hiện trong POM hoặc CLI.

**CI batch:** passphrase từ protected secret manager qua environment variable. Tên mặc định do plugin hỗ trợ là:

~~~text
MAVEN_GPG_PASSPHRASE
~~~

Không viết giá trị thật vào YAML hay log. Environment variables không tuyệt đối an toàn: mọi process chạy cùng trust boundary có thể có cơ hội đọc chúng. Release job chỉ được chạy mã đã được review và không cung cấp secrets cho untrusted PR jobs.

GPG signer có `gpg.keyname` để chọn khóa qua `--local-user`. **Không nhầm** tham số fingerprint environment của BC signer với cách chọn khóa của GnuPG signer mặc định; xem tài liệu plugin cho signer được dùng.

## 11. Lab Java 17: build bình thường không cần secret

Demo dùng một project có ba JUnit 5 tests. GPG Plugin nằm trong **profile riêng**, nên `mvn clean verify` hoạt động không cần signing key hoặc repository token.

### 11.1. Cấu trúc

~~~text
release-secret-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/release/ReleaseLabel.java
    └── test/java/com/example/release/ReleaseLabelTest.java
~~~

### 11.2. `pom.xml` hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.release</groupId>
    <artifactId>release-secret-demo</artifactId>
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
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>sign-release</id>
            <build>
                <plugins>
                    <plugin>
                        <groupId>org.apache.maven.plugins</groupId>
                        <artifactId>maven-gpg-plugin</artifactId>
                        <version>3.2.8</version>
                        <configuration>
                            <bestPractices>true</bestPractices>
                        </configuration>
                        <executions>
                            <execution>
                                <id>sign-artifacts</id>
                                <phase>verify</phase>
                                <goals>
                                    <goal>sign</goal>
                                </goals>
                            </execution>
                        </executions>
                    </plugin>
                </plugins>
            </build>
        </profile>
    </profiles>
</project>
~~~

`pom.xml` này **không** có `distributionManagement` vì demo không cho phép publish tới endpoint thật. GPG Plugin sẽ chỉ chạy khi profile `sign-release` active. Mọi version được pin để tránh phụ thuộc plugin defaults vô hình.

Lệnh unsigned build có thể chạy khi Maven/JDK/repository artifacts có sẵn:

~~~bash
mvn -version
java -version
mvn -B clean verify
~~~

Khi bật profile:

~~~bash
mvn -Psign-release clean verify
~~~

Maven sẽ yêu cầu một GnuPG signing key hợp lệ. Nếu không có key, pinentry/agent không mở được hoặc CI chưa cấp passphrase, **signing fail là đúng**; không tự chuyển sang `-Dgpg.skip=true` để giả mạo một signed build đã pass.

### 11.3. `ReleaseLabel.java`

Tạo `src/main/java/com/example/release/ReleaseLabel.java`:

~~~java
package com.example.release;

public final class ReleaseLabel {

    private ReleaseLabel() {
    }

    public static String label(String artifactId, int major, int minor) {
        if (artifactId == null || artifactId.isBlank()) {
            throw new IllegalArgumentException(
                    "artifactId must not be blank");
        }

        if (major < 0 || minor < 0) {
            throw new IllegalArgumentException(
                    "version numbers must be non-negative");
        }

        return artifactId + ":" + major + "." + minor;
    }

    public static void main(String[] args) {
        System.out.println(label("release-secret-demo", 1, 0));
    }
}
~~~

### 11.4. `ReleaseLabelTest.java`

Tạo `src/test/java/com/example/release/ReleaseLabelTest.java`:

~~~java
package com.example.release;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ReleaseLabelTest {

    @Test
    void formatsVersion() {
        assertEquals("release-secret-demo:1.0",
                ReleaseLabel.label("release-secret-demo", 1, 0));
    }

    @Test
    void rejectsBlankArtifactId() {
        assertThrows(IllegalArgumentException.class,
                () -> ReleaseLabel.label("  ", 1, 0));
    }

    @Test
    void rejectsNegativeVersion() {
        assertThrows(IllegalArgumentException.class,
                () -> ReleaseLabel.label("demo", -1, 0));
    }
}
~~~

Có **3 test methods**. Không có private key, token hoặc network trong Java source. Code thực hành minh họa tính chất quan trọng: **ứng dụng có thể được build/test độc lập với việc ký và publish**.

### 11.5. Build, chạy và expected stdout

~~~bash
mvn -B clean verify
java -cp target/classes com.example.release.ReleaseLabel
jar tf target/release-secret-demo-1.0.0.jar
~~~

**Stdout chính xác từ Java main**:

~~~text
release-secret-demo:1.0
~~~

Maven chạy JUnit với 3 tests, tạo `target/release-secret-demo-1.0.0.jar` nếu không có lỗi. Lệnh `jar tf` liệt kê compiled class `com/example/release/ReleaseLabel.class`; thứ tự và toàn bộ logs phụ thuộc JDK/plugin. Không dùng `java -jar` trực tiếp vì demo chưa thêm `Main-Class` manifest.

## 12. Ký trên workstation bằng gpg-agent

Với private key hợp lệ được lưu trong protected keyring, kiểm metadata:

~~~bash
gpg --list-secret-keys --keyid-format LONG
~~~

Sau đó có thể dùng Maven interactive:

~~~bash
mvn -Psign-release clean verify
~~~

`gpg-agent`/pinentry có thể yêu cầu người ký nhập passphrase qua giao diện an toàn. Trong batch/non-interactive mode, pinentry không luôn hiển thị; theo tài liệu GPG Plugin, agent có thể cần được **prime** từ một interactive session hoặc CI inject passphrase qua protected environment.

Không:
- Dùng `-Dgpg.passphrase=ACTUAL_SECRET`.
- Đặt `<passphrase>` chứa secret literal trong POM.
- Viết passphrase vào `settings.xml` không kiểm soát.
- In private key hoặc passphrase khi `-X` debugging.

### 12.1. Chữ ký `.asc` được tạo như thế nào?

GPG Plugin `gpg:sign` ký project artifact, POM và attached artifacts. Tham số `ascDirectory` mặc định của plugin là `${project.build.directory}/gpg`, nên có thể gặp:

~~~text
target/release-secret-demo-1.0.0.jar
target/gpg/release-secret-demo-1.0.0.jar.asc
target/gpg/release-secret-demo-1.0.0.pom.asc
~~~

Tên file/đường dẫn có thể thay đổi theo cấu hình plugin; xác minh file thực sau khi chạy. Nếu project còn tạo sources/Javadoc JARs trước phase ký, plugin có thể ký chúng như attached artifacts. **GPG Plugin không tự tạo Javadoc/sources JARs**; cần cấu hình plugin tạo artifacts riêng.

### 12.2. Kiểm chữ ký bằng public key đã xác minh

Với đúng file signature và public key đáng tin:

~~~bash
gpg --verify target/gpg/release-secret-demo-1.0.0.jar.asc target/release-secret-demo-1.0.0.jar
~~~

Một thông báo tương đương `Good signature` chỉ là kết quả kiểm mật mã. Phải kiểm **fingerprint** của key có đúng identity của nhà phát hành không. Nếu key tự tải từ cùng một nguồn không tin cậy với JAR, kẻ tấn công có thể thay cả artifact và public key.

Chữ ký **không mã hóa** JAR. Bất kỳ secret nào đã bị đóng gói trong JAR vẫn có thể bị đọc dù JAR có `.asc`.

## 13. Signed build khác authenticated upload

Hai bước cần được coi độc lập:

| Bước | Bí mật cần | Kết quả |
| --- | --- | --- |
| `mvn -B clean verify` | Không | JAR/POM được build và test |
| `mvn -Psign-release clean verify` | Signing private key và cách unlock | JAR/POM signatures nếu ký thành công |
| `mvn -Psign-release clean deploy` | Signing secrets **và** repository write credentials | Ký rồi publish nếu mọi bước pass |
| Consumer verification | Public key/fingerprint tin cậy | Xác minh provenance/integrity của bytes |

`mvn -Psign-release clean deploy` là **lệnh hình mẫu cho release project được cấp quyền**. Demo POM chưa có distributionManagement thật nên không dùng lệnh ấy để tự publish. Cần repository URL và token do owner cấp, cùng policy đủ tests, signatures, legal approval.

**Đừng dùng cùng passphrase làm repository token.** Nếu repo hỗ trợ, tách quyền read vs write và snapshots vs releases. Token upload không cần có quyền admin toàn organization.

## 14. CI: injection vào môi trường protected, không vào YAML literal

Một GitHub Actions template minh họa **chỉ ký, không publish**:

~~~yaml
name: Signed release candidate

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  sign:
    runs-on: ubuntu-latest
    environment: protected-release

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Prepare isolated GnuPG home
        run: install -d -m 700 "$RUNNER_TEMP/gnupg"

      - name: Import private key from vault-backed secret
        env:
          GNUPGHOME: ${{ runner.temp }}/gnupg
          RELEASE_GPG_KEY_B64: ${{ secrets.RELEASE_GPG_KEY_B64 }}
        run: |
          printf '%s' "$RELEASE_GPG_KEY_B64" |
            base64 --decode |
            gpg --batch --import

      - name: Compile, test and sign
        env:
          GNUPGHOME: ${{ runner.temp }}/gnupg
          MAVEN_GPG_PASSPHRASE: ${{ secrets.RELEASE_GPG_PASSPHRASE }}
        run: mvn -B -Psign-release clean verify
~~~

**Đây chưa phải workflow production hoàn chỉnh.** Nó giả định:
- `RELEASE_GPG_KEY_B64` là private key material được cấp vào protected secret store, không ghi literal vào repository. Base64 **không phải encryption**.
- `RELEASE_GPG_PASSPHRASE` là protected secret khác.
- `protected-release` có approval và chỉ người được phép trigger.
- Runner đủ GnuPG/Maven/JDK, plugin và repository artifacts.
- Code/commit đã được review; không chạy untrusted PR code với release key.
- Ephemeral runner sẽ được hủy. Self-hosted runner cần cleanup/segregation nghiêm ngặt.

Không dùng `set -x`, `env`, `printenv` hoặc in secret values để debug. Masked-logs là defense-in-depth, không thay access control.

### 14.1. Tại sao environment secrets cũng có nguy cơ?

Nếu CI chạy shell script từ PR của người ngoài sau khi inject `MAVEN_GPG_PASSPHRASE`, script đó có thể đọc variable. Vì vậy protection quan trọng nhất là **không cấp secret cho untrusted code path**.

Tách PR build (tests, no secret) và protected release job (secrets sau approval). Dùng permissions tối thiểu, pinned actions theo security policy, isolated user/runner và audit.

## 15. Tạo settings tạm cho job upload

Trong release job được phép publish, một tệp `settings.xml` tạm có thể chứa references:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>internal-releases</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
~~~

Đây là **settings template**, chưa có real token. Một step CI cấp env vars từ protected vault và gọi:

~~~bash
mvn -B -s /path/to/ephemeral-settings.xml -Psign-release clean deploy
~~~

**Lệnh không tự đủ để chạy:** phải có POM cấu hình approved `distributionManagement`, server ID matching, real repository endpoint, protected key, token và release approval. Tránh đặt token trong URL hoặc CLI `-Dpassword`; chúng có thể rò qua logs/process list.

Không upload settings, keyring, `$HOME/.m2`, `$HOME/.gnupg` hoặc `$RUNNER_TEMP` cả thư mục như diagnostic artifact.

## 16. POM và `settings.xml` có quan hệ gì khi Maven deploy?

Ví dụ POM:

~~~xml
<distributionManagement>
    <repository>
        <id>internal-releases</id>
        <url>https://repo.example.invalid/repository/releases/</url>
    </repository>
</distributionManagement>
~~~

`settings.xml` cần:

~~~xml
<server>
    <id>internal-releases</id>
    <username>${env.MAVEN_REPO_USER}</username>
    <password>${env.MAVEN_REPO_TOKEN}</password>
</server>
~~~

`id` phải khớp. URL xác định destination, server entry xác định authentication. Quyền token phải tương ứng endpoint, repository type và action.

**`<repositories>` trong project không phải chỗ deploy.** Nó phục vụ dependency resolution. **`distributionManagement` không phải chỗ đặt credentials**.

### 16.1. Origin binding trong các Maven versions mới

Maven versions mới có cơ chế ràng buộc credentials với origins của repository để giảm nguy cơ gửi token tới host khác chỉ vì repository ID giống nhau. Các phần như `repositoryOrigins` và `maven.repository.credentialScope` có hành vi phụ thuộc phiên bản; đừng coi Maven 3.9.x giống Maven 3.10.0/Maven 4 trong chi tiết này.

Vẫn cần **verify approved URL/host**, TLS, scope token, permissions và trust boundary của code. Một plugin đọc `settings.xml` trực tiếp không nhất thiết chịu cùng cơ chế credential binding của Maven Resolver.

## 17. Maven Central không nhất thiết dùng quy trình deploy truyền thống

Với internal Nexus/Artifactory/hosted Maven repository, `mvn deploy` thường dùng `distributionManagement` và server credentials.

**Central Publisher Portal** có workflow và Maven plugin riêng, ví dụ `central-publishing-maven-plugin`, với yêu cầu metadata, sources, Javadoc và signatures theo hướng dẫn Sonatype hiện hành. Đừng dùng một URL OSSRH cũ được copy từ blog rồi tự coi là Maven Central endpoint hiện tại.

Ở mọi môi trường, **quyền upload** không thay **quyền ký** và không thay security/legal review.

## 18. Không để secret lọt vào JAR qua resource filtering

Một lỗi tinh vi: POM không chứa token literal, nhưng một resource template có:

~~~properties
repo.token=${env.MAVEN_REPO_TOKEN}
~~~

nếu Maven Resources Plugin bật filtering, token từ môi trường build có thể được nội suy và **đóng gói vào JAR**.

Để tránh:
- Không tham chiếu secrets trong resources được package.
- Chỉ filter metadata công khai (project version, build revision).
- Kiểm nội dung `target/classes`, JAR entries, generated resources trước release.
- Dùng runtime secret injection nếu ứng dụng cần credential khi chạy, không bundle trong source/JAR.
- Dùng secret scanning cả source tree và build outputs theo policy.

`gpg:sign` ký JAR có secret **không che giấu secret**. Nó chỉ xác minh chính JAR ấy đã được ký.

## 19. `.gitignore` phòng ngừa nhưng không thay incident response

Ví dụ các patterns có thể dùng cho repository mới:

~~~gitignore
.env
.env.local
private-signing-key.asc
private-signing-key.gpg
settings.local.xml
release-secrets/
target/
~~~

Không ignore **tất cả** `.asc` vì detached signature `.asc` là public artifact có thể cần xuất bản. Kiểm nội dung/nguồn gốc file để phân biệt signature với exported secret material.

Nếu secret đã bị Git track, thêm ignore **không xóa commit history**. Cần revoke/rotate secret trước, đánh giá các bản sao trong PRs/forks/cache/logs, rồi mới làm sạch source/history theo quy trình và phối hợp người có quyền.

## 20. Xác minh không lộ secret từ build

Khi hoàn tất unsigned build:

~~~bash
mvn -B clean verify
jar tf target/release-secret-demo-1.0.0.jar
~~~

Tìm những entries không nên có:
- `settings.xml` chứa token.
- Private signing key block/material.
- `.env` bí mật.
- Generated config chứa credential.
- Dump môi trường hoặc log có token.

Đừng chỉ scan tên file, vì secret có thể nằm trong `.properties`/resources dưới tên hợp lệ. Dùng secret scanner và kiểm distribution artifact. Khi chạy `mvn -X`, logs có thể rất chi tiết; **không tự đăng chúng lên issue công khai**. `mvn help:effective-settings` cũng phải được sử dụng thận trọng vì output có thể chứa thông tin server nhạy cảm.

### 20.1. Cách kiểm an toàn hơn khi debug

~~~bash
mvn -version
gpg --version
gpg --list-secret-keys --keyid-format LONG
mvn -B clean verify
~~~

Những lệnh này giúp phân biệt toolchain, availability của key metadata và lỗi build unsigned. Nếu không ký được, kiểm GnuPG agent/pinentry và CI secret presence qua cơ chế **không in giá trị**. Đừng “sửa 401” bằng cách echo token.

## 21. Chữ ký không thay tính toàn vẹn của pipeline

Một bản phát hành an toàn cần:
- Build từ Git revision được review.
- Pin Maven/JDK/plugin versions.
- Tests/quality/security checks bắt buộc pass.
- Source/Javadoc/POM/artifact metadata chính xác.
- Signing key được kiểm soát và public fingerprint đáng tin.
- Chữ ký được tạo **sau** khi artifact bytes hoàn tất.
- Artifact publish **đúng bytes** đã ký.
- Repository upload token có scope tối thiểu.
- Immutable releases và audit log.
- Consumer kiểm lại signatures/checksum từ nguồn được phép.

Nếu signing job và publishing job là hai jobs khác nhau, cần chuyển **chính artifact đã ký** một cách an toàn. Không rebuild rồi publish một JAR mới mà chưa đối chiếu bytes: build timestamp/resource generation có thể khiến JAR mới khác dù cùng source commit.

## 22. Bảo vệ khóa ký xuyên suốt vòng đời

Một khóa ký có vòng đời:

1. Tạo bằng tham số được tổ chức phê duyệt.
2. Ghi fingerprint/public key qua kênh tin cậy.
3. Lưu private key trong protected keyring/HSM/vault.
4. Cấp quyền sử dụng cho authorized signers/jobs.
5. Dùng `gpg-agent`/CI secrets để mở khóa đúng lúc.
6. Audit signing operations và artifacts.
7. Giám sát expiration, rotate theo policy.
8. Thu hồi khi key bị mất/compromised.
9. Thông báo consumers cập nhật fingerprint/key trust khi cần.

Trên self-hosted CI, GnuPG keyring/agent cache có thể sống lâu hơn một job. Cô lập OS user, `GNUPGHOME`, quyền directory và cleanup. Một runner chia sẻ với untrusted PR jobs **không nên đồng thời giữ signing key có quyền release**.

## 23. Khi secret bị lộ: hành động nào trước?

**Không** xem việc `git rm` là kết thúc sự cố.

1. Xác định loại secret và phạm vi quyền: token deploy, SCM token, private signing key hay passphrase.
2. Hạn chế/tạm dừng release workflows có nguy cơ.
3. **Revoke/rotate** tokens có thể dùng, và cấp lại quyền tối thiểu.
4. Nếu private key có khả năng compromise, kích hoạt quy trình **key revocation/rotation** và thông báo users về identity mới theo policy.
5. Kiểm repository audit logs, artifact checksums, unauthorized releases.
6. Tìm các nơi secret có thể tồn tại: Git history, PR forks, CI artifacts/cache/logs, runner disk.
7. Sau khi vô hiệu hóa credential, loại khỏi source/histories theo quy trình; history rewrite **không đảm bảo xóa các bản sao đã bị tải**.
8. Rà soát build scripts có thể đã exfiltrate values.
9. Bổ sung secret scanning, branch/environment protection và key management.
10. Ghi incident timeline và chứng cứ **không chứa secret literal**.

Nếu chỉ là **public key** xuất hiện trong repo, đó không tự là lộ private key; điều cần kiểm là tính đúng đắn/fingerprint của key được quảng bá.

## 24. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý không lộ secret |
| --- | --- | --- |
| `gpg: signing failed: No secret key` | Key chưa được import vào đúng keyring/GNUPGHOME | `gpg --list-secret-keys`; kiểm job provisioning |
| `No pinentry` | Headless agent hoặc không có interactive prompt | Prime agent hoặc CI env theo policy |
| Plugin GPG báo best-practices violation | Dùng `gpg.passphrase`/cách lưu secret deprecated | Dùng agent hoặc `MAVEN_GPG_PASSPHRASE` |
| CI ký fail, workstation ký pass | CI chưa có private key/unlock | Kiểm protected secret/job permissions |
| `mvn verify` xanh nhưng không có `.asc` | Signing profile không active | Kiểm `-Psign-release`, không tuyên bố đã ký |
| `.asc` có nhưng `BAD signature` | Artifact bytes khác hoặc signature sai | So checksums và ký lại từ artifact đã verify |
| `Good signature` nhưng signer không rõ | Chưa kiểm fingerprint public key | Xác minh từ trusted release channel |
| HTTP 401 khi deploy | Token thiếu/sai/hết hạn | Kiểm server ID và secret presence, không echo |
| HTTP 403 khi deploy | Repo permissions không đủ | Request scope phù hợp, không cấp admin mặc định |
| HTTP 409 khi deploy | Release GAV đã tồn tại/immutable | Không overwrite, sửa version theo release process |
| Env var có trong local nhưng không trong CI | CI secret không cấp hoặc job không trusted | Protected environment/job setup |
| Maven 3 encrypted password bị trộm | Obfuscation-grade bị hiểu sai | Rotate và chuyển secret store chặt hơn |
| Token lộ trong Maven logs | Debug/plugin in params | Restrict log, rotate, sửa pipeline |
| Token xuất hiện trong JAR | Resource filtering/packaging sai | Thu hồi release, rotate và audit |
| CI job dùng untrusted PR code với token | Trust boundary bị phá | Tách PR tests và approved release |
| Signing key được upload như artifact | Upload cả keyring/temp dir | Revoke/rotate, allowlist uploads |
| Deploy xong nhưng consumer không verify | Chưa công bố public key/manifest | Publish identity/verification instructions |

Không dùng `-Dgpg.skip=true` hay `-DskipTests` chỉ để cho release pipeline xanh khi policy yêu cầu chữ ký hoặc tests bắt buộc.

## 25. Bài tập tự kiểm tra

**Câu 1.** Private signing key có được commit nếu đã có passphrase không?

**Đáp:** Không. Key material vẫn nhạy cảm và Git history tạo nhiều bản sao lâu dài.

**Câu 2.** Public key/fingerprint có phải secret không?

**Đáp:** Không. Nó cần được công bố qua kênh đáng tin để consumers xác minh signer.

**Câu 3.** `distributionManagement` có phải nơi lưu token deploy không?

**Đáp:** Không. Nó mô tả repository đích; auth thuộc settings/secret manager.

**Câu 4.** `<server><id>` trong Maven settings cần khớp gì?

**Đáp:** Repository id được Maven sử dụng cho upload/download được xác thực.

**Câu 5.** Mã hóa password Maven 3 có bằng secret vault không?

**Đáp:** Không. Nó ở mức obfuscation-grade theo tài liệu Maven.

**Câu 6.** Maven 4 có công cụ chuyên dụng nào cho encrypted settings?

**Đáp:** `mvnenc`, với cơ chế master key source/dispatcher mới.

**Câu 7.** GPG Plugin 3.2.8 dùng environment variable mặc định nào cho passphrase batch?

**Đáp:** `MAVEN_GPG_PASSPHRASE`.

**Câu 8.** `gpg:sign` có mã hóa nội dung JAR không?

**Đáp:** Không. Signing tạo chữ ký số; JAR vẫn đọc được.

**Câu 9.** Có nên cấp signing key/token cho PR từ fork để test Maven build không?

**Đáp:** Không. Chạy build/test unsigned với quyền tối thiểu; chỉ approved release job mới dùng secrets.

**Câu 10.** `mvn -B clean verify` của demo có cần private key không?

**Đáp:** Không. Profile ký không active mặc định.

**Câu 11.** `mvn -Psign-release clean verify` thiếu key thì sao?

**Đáp:** Signing fail; không được báo release signed thành công.

**Câu 12.** GPG báo Good signature có đủ để tin artifact không?

**Đáp:** Chưa. Cần kiểm fingerprint/key identity từ kênh đáng tin.

**Câu 13.** `.gitignore` có xóa token từng bị commit khỏi history không?

**Đáp:** Không. Revoke/rotate và incident response vẫn bắt buộc.

**Câu 14.** Environment variable trong CI có tuyệt đối bảo vệ secrets không?

**Đáp:** Không. Untrusted code trong job có thể đọc env; quan trọng là job trust boundary.

**Câu 15.** Có nên in `MAVEN_GPG_PASSPHRASE` để debug agent không?

**Đáp:** Không. Dùng non-sensitive diagnostics về keyring và tools.

**Câu 16.** Repo token lộ có chứng minh private signing key cũng lộ không?

**Đáp:** Không tự động; phải điều tra hai bí mật riêng.

**Câu 17.** Nếu sửa JAR sau khi ký, chữ ký có nên hợp lệ không?

**Đáp:** Không, vì bytes không còn khớp.

**Câu 18.** Maven Central Portal có nhất thiết dùng `mvn deploy` truyền thống không?

**Đáp:** Không. Phải theo publisher portal/plugin workflow hiện hành.

**Câu 19.** GPG signature có ngăn secret bị đưa vào JAR không?

**Đáp:** Không. Nó ký artifact ngay cả khi artifact chứa dữ liệu không nên công bố.

**Câu 20.** Vì sao release token nên có expiry/scope tối thiểu?

**Đáp:** Giảm tác động nếu token bị lộ và giúp revoke/audit dễ hơn.

## 26. Checklist trước khi ký và phát hành thật

1. `pom.xml` không có khóa riêng, passphrase hoặc deploy token.
2. `.mvn/maven.config`, `.mvn/jvm.config`, CI YAML không chứa secret literal.
3. Secret scanner chạy trên Git và release artifacts theo policy.
4. User `settings.xml` có quyền đọc tối thiểu, nằm ngoài repo.
5. Không coi encrypted Maven 3 password là secret storage đủ mạnh.
6. Với Maven 4, dùng đúng `mvnenc`/dispatcher theo version.
7. Repo URL/ID được admin xác minh và không bị untrusted POM chuyển hướng.
8. Deployment credentials chỉ nằm trong protected CI settings/env.
9. Token write riêng cho hosted repo/phạm vi cần thiết.
10. Read token của PR build không có quyền release.
11. Signing private key nằm trong keyring/HSM/secret vault.
12. Passphrase từ agent/pinentry hoặc protected CI env.
13. GPG Plugin version được pin, `bestPractices=true`.
14. Signing profile chỉ active ở approved release jobs.
15. Fail nếu thiếu private key/passphrase hoặc chữ ký bắt buộc.
16. Public key/fingerprint được công bố qua trusted channel.
17. Kiểm detached signatures với chính bytes dự kiến publish.
18. Kiểm JAR/POM không mang secrets qua filtering/packaging.
19. Không upload keyring, settings, temp directory hoặc env dump.
20. Không chạy untrusted PR code trong job có release secrets.
21. Protected release approvals và branch/tag restrictions có hiệu lực.
22. Ephemeral CI runners hoặc self-hosted cleanup nghiêm ngặt.
23. Unit/integration/quality/security checks pass trước release.
24. Signature, POM, sources/Javadoc cần thiết được publish đầy đủ.
25. Không overwrite immutable GAV bằng bytes mới.
26. Repo TLS/ACL/audit logs được bật.
27. Ghi Git commit, versions, checksum, SBOM/provenance.
28. Có key/token rotation và incident response playbook.
29. Consumer test từ sạch kiểm được artifact/signatures.
30. Nếu publish Maven Central, theo đúng workflow hiện hành của Central Portal.

## Tài liệu tham khảo

- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Security and Deployment Settings](https://maven.apache.org/guides/mini/guide-deployment-security-settings.html)
- [Apache Maven — Password Encryption (Maven 3)](https://maven.apache.org/guides/mini/guide-encryption.html)
- [Apache Maven — Password Encryption (Maven 4)](https://maven.apache.org/guides/mini/guide-encryption-4.html)
- [Apache Maven — Deploy Plugin Usage](https://maven.apache.org/plugins/maven-deploy-plugin/usage.html)
- [Apache Maven GPG Plugin — Overview](https://maven.apache.org/plugins/maven-gpg-plugin/)
- [Apache Maven GPG Plugin — Usage](https://maven.apache.org/plugins/maven-gpg-plugin/usage.html)
- [Apache Maven GPG Plugin — gpg:sign (3.2.8)](https://maven.apache.org/plugins/maven-gpg-plugin/sign-mojo.html)
- [Apache Maven GPG Plugin — FAQ](https://maven.apache.org/plugins/maven-gpg-plugin/faq.html)
- [Apache Maven — SCM Authentication](https://maven.apache.org/scm/authentication.html)
- [Sonatype — Central Portal publishing with Maven](https://central.sonatype.org/publish/publish-portal-maven/)
- [GnuPG — Official Manual](https://www.gnupg.org/documentation/manuals/gnupg/)
- [JUnit 5 — User Guide](https://docs.junit.org/5.11.4/user-guide/)

