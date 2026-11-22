# Cấp thông tin xác thực từ môi trường CI thay vì lưu trong Git (Maven Settings)

## 1. Mục tiêu và nguyên tắc an toàn

Một dự án Maven thường tải dependencies từ repository công khai, repository nội bộ hoặc **deploy artifact** lên Maven repository manager (Nexus, Artifactory, GitHub Packages...). Một số repository yêu cầu username/password, access token hoặc thông tin xác thực khác.

Vấn đề: nếu lưu mật khẩu/token thật trong `pom.xml`, `settings.xml` đã commit, file YAML workflow, script shell hoặc README trong Git, những người có quyền đọc repository (và đôi khi cả Git history, fork, build log hoặc artifact) có thể lấy được bí mật. Xóa một dòng trong commit mới **không đảm bảo** bí mật đã biến mất khỏi lịch sử.

**Thiết kế khuyến nghị:** Git chỉ chứa **địa chỉ repository, server ID, cấu hình build và các tên biến**. Secret thực được giữ trong kho bí mật của CI/secret manager, chỉ cấp cho job được phép, chuyển vào môi trường của Maven lúc chạy và không đưa vào Git, log hoặc build artifact.

Sau bài này, bạn có thể:

- Tách thông tin **repository/ID công khai** trong `pom.xml` khỏi **credentials** trong `settings.xml`.
- Dùng `${env.MAVEN_REPO_USER}` và `${env.MAVEN_REPO_PASSWORD}` để Maven đọc biến môi trường.
- Cấp secrets từ GitHub Actions hoặc GitLab CI cho job được bảo vệ; không viết chúng trực tiếp vào YAML đã commit.
- Tạo file settings tạm với **placeholder**, quyền truy cập hạn chế, chạy Maven với `-s` rồi dọn file.
- Chẩn đoán lỗi 401/403, `server.id` không khớp, biến CI trống hoặc repository URL sai mà không in lộ credentials.
- Phân biệt cách làm này với token ngắn hạn/OIDC và giới hạn quyền trong CI.

## 2. POM và Settings có trách nhiệm khác nhau

### 2.1. POM mô tả artifact và repository đích

`pom.xml` là phần của source repository. Khi deploy, Maven Deploy Plugin dựa vào `<distributionManagement>` để biết **đẩy artifact đến đâu**. Ví dụ:

```xml
<distributionManagement>
    <repository>
        <id>internal-releases</id>
        <url>https://repo.example.invalid/repository/maven-releases/</url>
    </repository>
    <snapshotRepository>
        <id>internal-snapshots</id>
        <url>https://repo.example.invalid/repository/maven-snapshots/</url>
    </snapshotRepository>
</distributionManagement>
```

Đây là một **đoạn POM**; muốn sử dụng phải đặt trong phần tử `<project>` của POM hợp lệ. Địa chỉ `repo.example.invalid` là ví dụ cố ý không hoạt động; khi làm bài thực tế, thay bằng URL HTTPS của repository được tổ chức cấp phép.

- `repository`: đích phát hành artifact release, chẳng hạn `1.0.0`.
- `snapshotRepository`: đích cho phiên bản `-SNAPSHOT`, chẳng hạn `1.1.0-SNAPSHOT`.
- `id`: định danh **logic** để Maven tìm credentials tương ứng.
- `url`: địa chỉ Maven truy cập, **không nhúng username/password** vào URL.

Điều quan trọng là **`id` trong `distributionManagement` phải khớp chính xác `id` của mục `<server>` trong settings đang được Maven sử dụng**. Chúng không nhất thiết giống hostname và không nên phụ thuộc việc bạn đặt tên biến CI giống gì.

### 2.2. Settings giữ cấu hình phụ thuộc môi trường và auth

Maven đọc settings từ các vị trí thông thường như `${user.home}/.m2/settings.xml` (user settings) và file cấu hình global của Maven. Có thể truyền file settings cụ thể qua `-s`:

```bash
mvn -s /path/to/settings.xml -B -ntp deploy
```

`-s` chọn **user settings thay thế** cho lần gọi này; global settings vẫn có thể được Maven hợp nhất theo quy tắc của phiên bản Maven. Điều này hữu ích trong CI vì bạn có thể để cấu hình tạm ngoài Git checkout.

Một settings tối thiểu để dùng credentials từ môi trường:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <servers>
        <server>
            <id>internal-releases</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_PASSWORD}</password>
        </server>
        <server>
            <id>internal-snapshots</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_PASSWORD}</password>
        </server>
    </servers>
</settings>
```

Các chuỗi `${env.MAVEN_REPO_USER}` và `${env.MAVEN_REPO_PASSWORD}` là **placeholder**, không chứa bí mật thực. Khi Maven đọc file, cơ chế nội suy settings có thể lấy giá trị từ **environment variables của tiến trình Maven**. Tên biến trên Linux có phân biệt chữ hoa/chữ thường.

Một số repository nhận **token** thay cho password: theo quy định của hệ thống đó, `username` có thể là tên service account hoặc giá trị được yêu cầu, `password` chứa token. Không giả định mọi repository đều cho phép để `username` trống hoặc đều dùng cùng một cách xác thực.

**Phân biệt:** `settings.xml` có thể chứa plaintext **sau khi** nội suy và khi Maven sử dụng nó trong bộ nhớ. Không đưa secret thực vào Git chỉ là một lớp bảo vệ; vẫn phải quản lý quyền, log và vòng đời credentials của runner.

## 3. Vì sao phải khớp `<server><id>`?

Giả sử POM chứa:

```xml
<distributionManagement>
    <repository>
        <id>internal-releases</id>
        <url>https://repo.example.invalid/repository/maven-releases/</url>
    </repository>
</distributionManagement>
```

Settings lại chứa:

```xml
<server>
    <id>nexus-release</id>
    <username>${env.MAVEN_REPO_USER}</username>
    <password>${env.MAVEN_REPO_PASSWORD}</password>
</server>
```

Maven **không tự đoán** `nexus-release` là alias của `internal-releases` chỉ vì URL trỏ đến server cùng tên. Kết quả có thể là request không có credentials phù hợp và remote báo HTTP 401/403.

Cách sửa là sửa `id` để khớp **đúng tên**, giữ bí mật trong CI:

```xml
<server>
    <id>internal-releases</id>
    <username>${env.MAVEN_REPO_USER}</username>
    <password>${env.MAVEN_REPO_PASSWORD}</password>
</server>
```

Khi **download dependency** từ private Maven repository, `<repositories><repository><id>...` hoặc mirror đã được chọn cũng cần `<server>` thích hợp. Với **mirror** trong `settings.xml`, thường là ID của mirror thực sự được sử dụng cần có credentials tương ứng, không phải lúc nào cũng là ID repository gốc.

Cần nhận diện **tình huống dùng credentials** trước khi sửa: tải dependency (`repositories`/mirror), tải plugin (`pluginRepositories`/mirror) hay deploy (`distributionManagement`). Mỗi tình huống có thể đi qua một server ID khác.

## 4. Cấp secrets cho job CI thay vì commit giá trị

Mô hình luồng dữ liệu:

```text
Kho secrets của CI / secret manager
        |
        | chỉ cấp cho job được phép
        v
MAVEN_REPO_USER  +  MAVEN_REPO_PASSWORD (environment)
        |
        | Maven đọc trong lúc chạy
        v
settings.xml chỉ chứa ${env.MAVEN_REPO_USER} / ${env.MAVEN_REPO_PASSWORD}
        |
        | server id khớp POM
        v
Maven Resolver / Deploy Plugin
        |
        v
Private artifact repository qua HTTPS
```

Các tầng có trách nhiệm riêng:

1. **Repository Git:** version code, POM, workflow, tên biến và template không chứa giá trị bí mật.
2. **CI secrets store:** lưu token/password, kiểm soát ai được cấu hình/đọc hoặc job nào được dùng.
3. **Runner:** nhận secret lúc job được phép chạy; chỉ đưa cho process/step cần thiết.
4. **Maven settings:** ánh xạ server ID thành credentials dựa vào environment.
5. **Repository manager:** kiểm tra quyền của credentials, chấp nhận/từ chối request.

Không nên thiết kế “bảo mật” chỉ dựa vào việc CI tự mask secret trong log: masking có giới hạn, nhất là khi giá trị bị biến đổi, cắt ra, encode hoặc được in qua plugin khác.

## 5. Ví dụ thực hành đầy đủ: Java 17 và repository cần xác thực

Ví dụ minh họa một dự án `release-demo`. Phần **build local** chạy được khi có JDK 17+ và Maven; bước **deploy** chỉ chạy thành công sau khi bạn cấu hình URL thực, token/service account đủ quyền và secret CI.

Cấu trúc:

```text
release-demo/
├── pom.xml
├── src/main/java/demo/App.java
└── .github/workflows/publish.yml
```

### 5.1. File `pom.xml` — có repository ID nhưng không chứa secret

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>release-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <distributionManagement>
        <repository>
            <id>internal-releases</id>
            <url>https://repo.example.invalid/repository/maven-releases/</url>
        </repository>
    </distributionManagement>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-deploy-plugin</artifactId>
                <version>3.1.3</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Địa chỉ `repo.example.invalid` phải được thay trước khi deploy. Không cần auth để chạy build local của mã Java nhỏ này; Maven vẫn có thể cần network khi tải plugin.

### 5.2. File `src/main/java/demo/App.java`

```java
package demo;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Build ready for CI");
    }
}
```

Trong thư mục chứa `pom.xml`, chạy local:

```bash
mvn clean verify
java -cp target/release-demo-1.0.0.jar demo.App
```

Dòng **stdout chính xác từ `App.main`** là:

```text
Build ready for CI
```

Chú ý JAR này chưa được cấu hình `Main-Class` trong manifest. Vì vậy chạy bằng `java -cp ... demo.App`, không mặc định dùng `java -jar`.

**`mvn clean verify` không tự deploy**; việc đẩy artifact vào repository thông thường xảy ra ở phase `deploy` khi chạy `mvn deploy`. Chỉ job phát hành được ủy quyền mới cần credentials để thực hiện bước này.

### 5.3. GitHub Actions — cấp secrets tại step publish

Trong GitHub Actions, đặt hai secrets do tổ chức quản lý (tên minh họa): `MAVEN_REPO_USER` và `MAVEN_REPO_PASSWORD`. Có thể đặt tại **repository secrets** hoặc **environment secrets** được bảo vệ bằng approval/branch rules. Không ghi giá trị thật vào file workflow.

File `.github/workflows/publish.yml`:

```yaml
name: Publish Maven artifact

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: release

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Build and deploy
        shell: bash
        env:
          MAVEN_REPO_USER: ${{ secrets.MAVEN_REPO_USER }}
          MAVEN_REPO_PASSWORD: ${{ secrets.MAVEN_REPO_PASSWORD }}
        run: |
          set -euo pipefail
          : "${MAVEN_REPO_USER:?Missing MAVEN_REPO_USER secret}"
          : "${MAVEN_REPO_PASSWORD:?Missing MAVEN_REPO_PASSWORD secret}"

          umask 077
          settings_file="$(mktemp)"
          trap 'rm -f "$settings_file"' EXIT

          cat > "$settings_file" <<'XML'
          <settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
                    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                    xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
            <servers>
              <server>
                <id>internal-releases</id>
                <username>${env.MAVEN_REPO_USER}</username>
                <password>${env.MAVEN_REPO_PASSWORD}</password>
              </server>
            </servers>
          </settings>
          XML

          mvn -B -ntp -s "$settings_file" clean deploy
```

Điều gì diễn ra?

1. Workflow chỉ chạy khi người được phép khởi động thủ công bằng `workflow_dispatch`. Có thể bổ sung quy trình approval và quy tắc branch/tag trước khi dùng trong production.
2. `environment: release` áp dụng quy tắc của environment nếu bạn đã cấu hình (như required reviewers); việc ghi dòng này **không tự tạo approval rule**.
3. `permissions: contents: read` giới hạn quyền cấp cho `GITHUB_TOKEN` của job ở mức đọc nội dung repository; credentials đẩy artifact là **hai secrets riêng**.
4. `env: ... secrets....` chỉ chuyển secrets vào step build/deploy, không vào mọi step của workflow.
5. `umask 077` và `mktemp` tạo file tạm trong môi trường runner; file được dùng qua `-s` rồi xóa trong `trap` kể cả khi lệnh Maven thất bại.
6. Heredoc `<<'XML'` **được quote**, nên shell **không** thay `${env.MAVEN_REPO_PASSWORD}` bằng secret tại bước tạo file. Maven thay bằng biến môi trường khi đọc settings.
7. `mvn -B -ntp -s "$settings_file" clean deploy` chạy chế độ non-interactive, hạn chế log transfer, chọn file settings tạm, đi qua lifecycle đến deploy.
8. Không có lệnh `echo`, `cat` hay `set -x` nào in token/password. Không đính kèm file settings, biến môi trường hay log chứa secret vào build artifact.

**Điều phải sửa trước khi chạy thật:** URL `repo.example.invalid` trong POM, quyền của service account, secrets trong CI và các chính sách cho môi trường phát hành. Đây là workflow mẫu về **cấp thông tin xác thực**, không phải cấu hình production phù hợp mọi repository.

#### Vì sao file tạm là placeholder chứ không chứa mật khẩu?

Nếu viết:

```bash
# Không nên làm:
echo "<password>$MAVEN_REPO_PASSWORD</password>" > settings.xml
```

thì secret trở thành **nội dung file thực**. Dù file nằm ngoài Git, vẫn có rủi ro bị log, upload artifact, backup hoặc đọc bởi process khác có quyền. Giữ placeholder `${env.MAVEN_REPO_PASSWORD}` trong file giúp tránh việc lưu plaintext token trong file settings. **Secret vẫn tồn tại trong process environment** khi job chạy, nên vẫn phải giới hạn quyền và tin cậy đối với runner.

`rm -f` chỉ xóa tên file theo cách thông thường, **không phải đảm bảo xóa dữ liệu vật lý không thể khôi phục**. Ưu tiên hosted runner tạm thời/ephemeral runner được cách ly, không tái sử dụng workspace chứa credentials hoặc giữ cache chứa dữ liệu bí mật.

## 6. Cách thay thế: để `actions/setup-java` tạo Maven settings

GitHub Actions `actions/setup-java` có thể tự tạo Maven `settings.xml` với cấu hình server ID và **tên biến môi trường** thay vì yêu cầu tự viết file qua heredoc. Cách này phù hợp khi repository cần xác thực đơn giản và bạn muốn giảm mã shell.

Ví dụ **đoạn workflow** (các bước dưới đây nằm trong `jobs.<job>.steps` của một workflow hợp lệ):

```yaml
- uses: actions/setup-java@v4
  with:
    distribution: temurin
    java-version: '17'
    server-id: internal-releases
    server-username: MAVEN_REPO_USER
    server-password: MAVEN_REPO_PASSWORD

- name: Deploy artifact
  env:
    MAVEN_REPO_USER: ${{ secrets.MAVEN_REPO_USER }}
    MAVEN_REPO_PASSWORD: ${{ secrets.MAVEN_REPO_PASSWORD }}
  run: mvn -B -ntp clean deploy
```

Ở đây `server-username`/`server-password` là **tên biến**, không phải giá trị thật. `setup-java` tạo cấu hình Maven có thể tham chiếu các biến tương ứng. Tùy phiên bản action, file settings mặc định và việc overwrite settings có thể ảnh hưởng cấu hình có sẵn trên runner; hãy xem tài liệu của version action đang dùng.

**Chọn một trong hai cách rõ ràng:** tự tạo settings tạm và truyền `-s` khi cần kiểm soát chính xác nhiều server/mirror, hoặc dùng `setup-java` khi nhu cầu tương thích với tính năng của action. Tránh để hai cách vô tình ghi đè settings của nhau.

## 7. Ví dụ GitLab CI: dùng masked/protected variables

GitLab CI cho phép cấu hình **CI/CD variables** trong dự án/nhóm và áp dụng cơ chế bảo vệ biến. Ví dụ hướng tiếp cận trên một runner Linux có Maven 3.9 + JDK 17:

```yaml
stages:
  - build
  - publish

build:
  stage: build
  image: maven:3.9-eclipse-temurin-17
  script:
    - mvn -B -ntp clean verify

publish:
  stage: publish
  image: maven:3.9-eclipse-temurin-17
  rules:
    - if: '$CI_COMMIT_TAG'
  script:
    - |
      set -eu
      : "${MAVEN_REPO_USER:?missing variable}"
      : "${MAVEN_REPO_PASSWORD:?missing variable}"
      umask 077
      settings_file="$(mktemp)"
      trap 'rm -f "$settings_file"' EXIT
      cat > "$settings_file" <<'XML'
      <settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
        <servers>
          <server>
            <id>internal-releases</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_PASSWORD}</password>
          </server>
        </servers>
      </settings>
      XML
      mvn -B -ntp -s "$settings_file" clean deploy
```

Workflow trên chỉ là ví dụ; cấu hình **protected/masked variables**, quyền runner, protected tags và policy phê duyệt thực tế phải được thực hiện trong GitLab project. `rules: if: '$CI_COMMIT_TAG'` chỉ giới hạn job theo sự kiện tag, **không thay thế bảo vệ tag hoặc quyền truy cập variables**. Cần xác minh image/container có shell và Maven phù hợp trước khi dùng nguyên mẫu.

### Khi dùng Jenkins hoặc hệ thống CI khác

Ý tưởng không đổi: Jenkins Credentials Binding hoặc secret manager của CI cung cấp credential qua biến môi trường/file chỉ trong phạm vi step được phép, Maven dùng `settings.xml` chứa placeholder hoặc tệp được CI tạo tạm. Không lưu giá trị thật trong Jenkinsfile, POM hay shell script đã commit. Nên tách service account phát hành khỏi tài khoản cá nhân và xoay vòng token theo chính sách.

## 8. Test an toàn: kiểm tra configuration mà không làm lộ secret

Bạn có thể tách kiểm tra thành ba mức:

### Mức A — kiểm tra POM không cần secret

```bash
mvn -B -ntp clean verify
```

Build local và test code không yêu cầu quyền deploy. Nếu nó lỗi do dependency private, cần cấu hình **read-only credentials** cho repository tải dependency; không cần cấp quyền deploy chỉ để compile/test.

### Mức B — xác nhận ID và biến đã được cung cấp

Đọc file POM và template settings: `distributionManagement.repository.id` phải trùng `servers.server.id`. Xác minh CI đã cấu hình secret *tồn tại* mà không in giá trị:

```bash
: "${MAVEN_REPO_USER:?Missing MAVEN_REPO_USER}"
: "${MAVEN_REPO_PASSWORD:?Missing MAVEN_REPO_PASSWORD}"
```

Lệnh trên dùng trong Bash và chỉ kiểm tra biến rỗng/không được đặt; không in giá trị. **Không** dùng `printenv`, `env`, `echo "$MAVEN_REPO_PASSWORD"` hoặc `set -x` trong bước xử lý secrets.

### Mức C — xác minh request thật ở job được phép

Một lệnh `mvn -s "$settings_file" validate` có thể xác nhận cú pháp POM và việc Maven đọc settings, **nhưng chưa chắc xác nhận quyền truy cập repository**. Muốn biết token thực sự có thể deploy, phải chạy publish đến repository được cho phép hoặc có endpoint kiểm thử phù hợp trong môi trường được kiểm soát.

Khi lỗi, phân biệt:

| Dấu hiệu | Khả năng thường gặp | Cách xử lý an toàn |
| --- | --- | --- |
| HTTP 401 Unauthorized | Credentials thiếu/sai/hết hạn, server ID không khớp | Kiểm tra ID, biến hiện diện và thời hạn token; không in giá trị |
| HTTP 403 Forbidden | Đã xác thực nhưng không có quyền hoặc bị policy chặn | Kiểm tra scope publish, repo/namespace, branch/tag permissions |
| HTTP 404 Not Found | URL hoặc repo đích không đúng, hoặc service ẩn endpoint | Kiểm tra URL và repository type, policy; không đổi token bừa |
| TLS/certificate error | Trust store/certificate chain/proxy sai | Sửa CA/trust setup thay vì tắt xác minh TLS |
| Artifact already exists / immutable release | Cố deploy lại cùng release version | Tăng version theo chính sách hoặc dùng snapshot repo đúng mục đích |
| Biến môi trường rỗng | Secret không được cấp cho job, tên sai, fork/Dependabot hoặc environment policy | Kiểm tra phạm vi secrets và quyền job |
| Dependency không resolve được trước deploy | Private dependency/plugin repository cần quyền read riêng | Cấu hình ID của repository/mirror và read-only credentials |

Thông điệp lỗi đôi khi khác theo repository manager; không coi mọi lỗi 403 là sai mật khẩu. Không dùng `-X` hoặc in `help:effective-settings` trên job chứa secrets khi chưa đánh giá nguy cơ lộ thông tin nhạy cảm: bản output/debug có thể chứa chi tiết cấu hình và đường dẫn, và masking không phải cơ chế đảm bảo tuyệt đối.

## 9. Những điều KHÔNG nên làm

**Không hard-code token trong POM:**

```xml
<!-- Ví dụ cấu hình KHÔNG NÊN dùng -->
<properties>
    <repo.password>my-real-secret-value</repo.password>
</properties>
```

Dù plugin có nhận property này hay không, giá trị bí mật đã nằm trong Git. Không thêm nó chỉ để một build demo hoạt động.

**Không đưa credentials vào URL:**

```text
https://username:password@repo.example.invalid/repository/maven-releases/
```

URL có thể được ghi log, lưu trong history, proxy hay telemetry. Dùng URL không có password và ánh xạ `server.id` qua settings.

**Không truyền secret bằng argument CLI nếu có thể tránh:** ví dụ `-Drepo.password=<secret>` có thể lộ qua danh sách process, audit log hoặc script debug. Ưu tiên CI secret → environment → Maven settings placeholder, với process/runner được giới hạn quyền.

**Không commit `settings.xml` chứa plaintext hoặc token đã “mã hóa” kèm dữ liệu giải mã:** các cơ chế mã hóa password của Maven có mục đích và giới hạn riêng. Một blob đã mã hóa không tự trở thành an toàn để public nếu key có thể lấy được. Với CI, sử dụng kho secrets chuyên dụng và token ngắn hạn khi có thể.

**Không upload file settings tạm làm artifact** và không đưa `~/.m2/settings.xml` vào cache. Cache Maven dependency thường chỉ cần local repository `~/.m2/repository`; xem cấu hình từng CI trước khi dùng cache.

**Không in secrets để “debug”**: thậm chí giá trị hash, base64 hoặc đã cắt đoạn cũng có thể hỗ trợ việc lộ credential. Secret masking của CI không đảm bảo che được mọi biến thể.

**Không publish từ untrusted pull request bằng job chứa token deploy.** Kiểm soát trigger, runner permissions, environment approval và nguồn code mà job sẽ thực thi.

**Không để secrets không giới hạn thời gian/quyền.** Ưu tiên token scope nhỏ, riêng cho publish, rotation/revocation và review sự kiện phát hành.

## 10. Mở rộng: token ngắn hạn và OIDC

Khi repository manager hoặc hệ thống phát hành hỗ trợ **federated identity/OIDC** hoặc service cung cấp cách đổi workload identity thành token, có thể tránh lưu secret dài hạn:

1. CI xác thực workload của job (repository, branch/tag, environment) với identity provider.
2. Một hệ thống tin cậy cấp **token ngắn hạn** với quyền tối thiểu cho registry/repository.
3. Runner đặt token vào biến môi trường chỉ trong bước cần deploy.
4. Maven tiếp tục dùng `settings.xml` với placeholder `${env.MAVEN_REPO_PASSWORD}` hoặc cơ chế auth được plugin/repository hỗ trợ.

**Không suy luận rằng Maven Deploy Plugin tự động hỗ trợ mọi nhà cung cấp OIDC.** Quá trình đổi OIDC identity thành credential repository phụ thuộc nhà cung cấp, registry, CI và cơ chế phát hành. Nếu môi trường hiện tại chỉ hỗ trợ service account token, vẫn có thể triển khai tốt bằng secret store, quyền tối thiểu và rotation.

## 11. Nếu credentials từng bị commit: xử lý như một sự cố

Nếu đã lỡ commit token/password vào Git, **đừng chỉ xóa dòng và cho là đã an toàn**. Có thể token đã xuất hiện trong commit cũ, fork, pull request, cache, artifact hoặc log.

Quy trình cơ bản:

1. **Thu hồi/rotate token ngay**, tạo credential thay thế với quyền tối thiểu; kiểm tra khả năng truy cập bất thường nếu có log/audit.
2. Chuyển credential mới vào CI secrets store; sửa POM/settings/workflow để không cần plaintext trong repo.
3. Xác định phạm vi lộ: commit history, clone/fork, CI logs, build artifacts và đường dẫn backup liên quan.
4. Nếu cần làm sạch lịch sử, tuân thủ quy trình của tổ chức, phối hợp với chủ repository và đồng đội vì rewrite history có thể ảnh hưởng nhiều người; **rotation vẫn là bước bắt buộc**.
5. Bổ sung secret scanning, kiểm tra trước commit, review và policy ngăn credentials bị ghi lại.

Lợi ích của mô hình env-based không chỉ là “ẩn password khỏi file POM”: nó cho phép **thu hồi, thay thế và phân quyền** mà không phải sửa mã nguồn trong Git.

## 12. Checklist khi triển khai thật

- [ ] `pom.xml` chỉ chứa repo URL HTTPS và `distributionManagement` ID, không chứa password/token.
- [ ] `settings.xml` dùng `${env.MAVEN_REPO_USER}` / `${env.MAVEN_REPO_PASSWORD}` (hoặc cơ chế secret injection có kiểm soát).
- [ ] `<server><id>` khớp chính xác ID repository/mirror thực sự dùng.
- [ ] Secret được cấu hình ở CI secret manager, không lưu trong workflow Git và không cấp cho untrusted PR.
- [ ] Token/service account có quyền **tối thiểu**, đặc biệt tách read dependency và deploy nếu có thể.
- [ ] File settings tạm nằm ngoài Git checkout, permission hạn chế và được dọn sau job.
- [ ] Không in secret, không bật shell tracing cho đoạn xử lý secret, không cache/upload settings.
- [ ] Job publish có trigger, tag/branch protection hoặc environment approval phù hợp.
- [ ] Build `mvn clean verify` chạy được mà không cần quyền deploy khi dependencies công khai.
- [ ] Deploy sử dụng đúng `mvn -s <settings-file> ... deploy` hoặc settings do CI action tạo.
- [ ] Lỗi 401/403/404 được phân loại, không dùng log chứa plaintext để dò lỗi.
- [ ] Có kế hoạch rotation, thu hồi và audit credentials nếu token bị lộ.

**Ghi nhớ:** POM nói **“đưa artifact đến repository nào?”**; `settings.xml` nói **“dùng thông tin xác thực nào cho server ID đó?”**; CI secret manager quyết định **“job nào được cấp thông tin thực và trong bao lâu?”**. Khi ba phần này tách biệt, source code có thể được kiểm tra, chia sẻ và tái sử dụng mà không mang theo bí mật đăng nhập.

## Tài liệu tham khảo chính thức

- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Deployment Transports & Server IDs](https://maven.apache.org/guides/mini/guide-deployment-transports.html)
- [Apache Maven Deploy Plugin — Usage](https://maven.apache.org/plugins/maven-deploy-plugin/usage.html)
- [GitHub Docs — Using Secrets in GitHub Actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets)
- [GitHub Docs — Secrets Security](https://docs.github.com/en/actions/concepts/security/secrets)
- [GitHub Docs — OpenID Connect in GitHub Actions](https://docs.github.com/en/actions/concepts/security/openid-connect)
