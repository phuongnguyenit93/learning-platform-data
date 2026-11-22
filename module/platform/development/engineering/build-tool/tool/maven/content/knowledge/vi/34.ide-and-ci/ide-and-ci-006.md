# Cấp settings.xml và bí mật cho CI theo phạm vi công việc trong Maven

## 1. Mục tiêu và ranh giới bảo mật của một CI job

Một pipeline Maven có nhiều nhiệm vụ: kiểm thử pull request, tải private dependencies, xây SNAPSHOT, ký release, deploy artifact và xác minh bản vừa phát hành. **Không job nào tự động cần mọi credential**. Nếu đặt cùng `settings.xml` chứa token quyền admin vào mọi job, một Maven plugin, test class hoặc build script không đáng tin có thể lấy token.

~~~text
pull_request verify      -> public dependencies; KHÔNG có token deploy
trusted internal build   -> private Maven read-only token nếu thật sự cần
snapshot publish         -> snapshot repository write token
protected release        -> release repository write token, có approval
post-release audit       -> read-only token, kiểm JAR/POM/checksums
~~~

**Nguyên tắc chính:** secret được lưu ở CI secret store/vault, chỉ cấp cho đúng **job hoặc step** có nhiệm vụ cần nó, bằng identity/role có **quyền tối thiểu**, có giới hạn thời gian, cơ chế revoke và audit. `settings.xml` là nơi Maven tìm thông tin xác thực; nó không phải lý do để commit token vào `pom.xml`.

Bài dùng Maven 3.9.x và Java 17. Các ví dụ GitHub Actions dùng `actions/setup-java@v6` và `actions/checkout@v7` theo tài liệu hiện hành. Jenkins hoặc GitLab có cơ chế cấp credential khác nhưng cùng nguyên tắc tách job/role.

## 2. Cái gì là cấu hình, cái gì là bí mật?

| Dữ liệu | Có thể lưu Git? | Giải thích |
| --- | --- | --- |
| `groupId/artifactId/version`, Java release | Có | Metadata Maven, không phải mật khẩu. |
| `distributionManagement.repository.id` | Có | Chỉ là tên khóa ghép nối, ví dụ `corp-release`. |
| Endpoint repo công khai | Có thể | Kiểm xem hostname/path có nhạy cảm không. |
| Template `settings.xml` chỉ có `${env.VAR}` | Có điều kiện | Không được có credential literal. |
| Read token private packages | **Không** | Chỉ cho job trusted cần download. |
| Write token SNAPSHOT/release | **Không** | Chỉ cho publisher đúng repository. |
| GPG private key/passphrase | **Không** | Chỉ cấp cho signing job nếu cần. |
| OIDC short-lived token | Không lưu | Chỉ cấp theo policy, hết hạn nhanh. |
| `settings-security.xml` master secret | **Không** | Legacy Maven 3 encryption không thay secret manager. |
| Test dummy password không có quyền | Có điều kiện | Phải thể hiện rõ là giả và không tái dùng. |

Các URL `https://repo.example.invalid/` bên dưới **chỉ minh họa**, không có remote registry thật. Không phát hành Maven Central với namespace/URL giả.

## 3. POM và settings.xml có vai trò khác nhau

**POM** mô tả project, dependencies, plugins, GAV và **đích** xuất bản:

~~~xml
<distributionManagement>
    <repository>
        <id>corp-release</id>
        <url>https://repo.example.invalid/maven/releases/</url>
    </repository>
</distributionManagement>
~~~

**User settings** mô tả cấu hình theo máy/user/CI runner: `servers`, `mirrors`, `profiles`, `activeProfiles`, `proxies` và `localRepository`.

~~~xml
<servers>
    <server>
        <id>corp-release</id>
        <username>${env.MAVEN_REPO_USER}</username>
        <password>${env.MAVEN_REPO_TOKEN}</password>
    </server>
</servers>
~~~

Hai khối là **mảnh XML**, chưa phải file độc lập. Maven Deploy Plugin dùng `distributionManagement/repository/id` và tra server credentials cùng `id` trong settings.

**Phân biệt ba nơi khai báo URL:**

- `<repositories>`: nơi Maven tải **project dependencies**.
- `<pluginRepositories>`: nơi Maven tải **build plugins**.
- `<distributionManagement>`: nơi Maven **deploy project artifacts**.

`project.url` là metadata/trang dự án, **không** phải remote deployment endpoint. POM không nên chứa username/password, dù repository URL là private.

## 4. Maven tìm settings.xml ở đâu và lệnh -s làm gì?

Maven 3 dùng cấu hình global và user, thường là:

~~~text
Global:  $MAVEN_HOME/conf/settings.xml
User:    $HOME/.m2/settings.xml
Custom:  mvn --settings /private/job/settings.xml verify
~~~

Cả global và user settings có thể được merge; user settings ưu tiên khi các phần tương ứng xung đột theo quy tắc Maven. Với CI, chủ động chọn user settings theo job:

~~~bash
mvn -B -ntp -s .ci/maven/settings-read.xml clean verify
~~~

Hoặc dạng dài:

~~~bash
mvn -B -ntp --settings .ci/maven/settings-read.xml clean verify
~~~

`-gs` dùng để chỉ định global settings khác khi cần. `-s` **chỉ lựa chọn file**, không cô lập process: Java tests, build plugins, annotation processors và subprocess vẫn có thể đọc file/env với quyền OS của runner.

**Đừng nhầm:**

- `.m2/settings.xml`: thường riêng máy/user/runner, có thể liên quan credentials.
- `.mvn/maven.config`: project-level CLI options, thường được commit, **không đặt token**.
- `.mvn/jvm.config`: JVM options, **không đặt token**.
- `.mvn/extensions.xml`: Maven extensions có khả năng chạy code trong build; cần được review.

Maven 4 có hỗ trợ và quy tắc project settings khác Maven 3; không bê nguyên hướng dẫn credentials Maven 3 sang `.mvn/settings.xml` rồi tin Maven 4 sẽ dùng giống nhau.

## 5. Interpolation: settings dùng biến môi trường

Trong Maven Settings Reference, `${env.MAVEN_READ_TOKEN}` lấy giá trị từ **environment variable của Maven process**:

~~~xml
<server>
    <id>corp-read</id>
    <username>${env.MAVEN_READ_USER}</username>
    <password>${env.MAVEN_READ_TOKEN}</password>
</server>
~~~

Đây **không phải token literal**. CI phải cung cấp `MAVEN_READ_USER` và `MAVEN_READ_TOKEN` khi chạy Maven. Nếu thiếu hoặc sai tên biến, xác thực có thể thất bại.

Các lỗi hay gặp:

- Settings cần `MAVEN_READ_TOKEN`, YAML chỉ map `MVN_READ_TOKEN`.
- Token chỉ có quyền download từ kho A, nhưng Maven đang chọn kho B.
- Settings có server ID `corp-read`, repository/mirror thực được chọn có ID khác.
- Pipeline in cả environment để debug, làm rò rỉ token.
- Settings template được lưu an toàn nhưng runner self-hosted còn `~/.m2/settings.xml` quyền admin của job trước.

**Quan trọng:** environment variables giúp tránh hard-code secrets trên disk/Git, nhưng chúng **không bảo vệ secret khỏi code chạy cùng job**. Secret store, runner isolation và trust source code vẫn quyết định phạm vi rủi ro.

## 6. settings-read.xml hoàn chỉnh cho một trusted build

Ví dụ file `.ci/maven/settings-read.xml` chứa **chỉ env placeholders**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <interactiveMode>false</interactiveMode>

    <servers>
        <server>
            <id>corp-read</id>
            <username>${env.MAVEN_READ_USER}</username>
            <password>${env.MAVEN_READ_TOKEN}</password>
        </server>
    </servers>

    <profiles>
        <profile>
            <id>ci-private-read</id>
            <repositories>
                <repository>
                    <id>corp-read</id>
                    <url>https://repo.example.invalid/maven/private/</url>
                    <releases>
                        <enabled>true</enabled>
                    </releases>
                    <snapshots>
                        <enabled>false</enabled>
                    </snapshots>
                </repository>
            </repositories>
        </profile>
    </profiles>

    <activeProfiles>
        <activeProfile>ci-private-read</activeProfile>
    </activeProfiles>
</settings>
~~~

Giải thích:

1. `<server><id>corp-read</id>` gắn thông tin xác thực với repository **cùng ID**.
2. `<repositories>` cung cấp nguồn để tải dependencies; không phải nơi deploy.
3. `<activeProfiles>` kích hoạt profile settings đã định nghĩa.
4. `snapshots=false` là chính sách **minh họa** của repository này; nhiều tổ chức có kho snapshot read riêng.
5. Token trong CI cần có **quyền đọc đúng namespace**. Tên biến `MAVEN_READ_TOKEN` không làm token tự trở nên read-only.
6. `example.invalid` phải được thay bằng URL thật trước khi dùng.
7. Nếu build plugins nằm ở private repository, cần cân nhắc `<pluginRepositories>`; thêm `<repositories>` không đồng nghĩa Maven biết nơi tải mọi plugin.
8. File không chứa release/snapshot write credential, phù hợp với trusted job chỉ tải private dependencies.

Không dùng settings này cho public PR chưa được review nếu việc inject read token vẫn có thể tiết lộ private packages hoặc secret cho untrusted code.

## 7. Mirrors thay đổi ID nào được dùng khi authenticate

Khi tổ chức proxy Maven Central và các kho ngoài qua một mirror:

~~~xml
<mirrors>
    <mirror>
        <id>corp-mirror</id>
        <mirrorOf>external:*</mirrorOf>
        <url>https://repo.example.invalid/maven/public-proxy/</url>
    </mirror>
</mirrors>
~~~

Nếu mirror cần credentials:

~~~xml
<servers>
    <server>
        <id>corp-mirror</id>
        <username>${env.MAVEN_MIRROR_USER}</username>
        <password>${env.MAVEN_MIRROR_TOKEN}</password>
    </server>
</servers>
~~~

Maven chọn mirror rồi dùng **mirror ID** để tìm server credentials, không nhất thiết dùng `central` hay ID của repository gốc. Đây là nguyên nhân rất phổ biến của HTTP 401 dù XML có token đúng.

`external:*` là pattern mirror matching của Maven cho các remote external repositories phù hợp, **không phải security allowlist hostname**. Quản trị mirror cần HTTPS, trusted endpoint, role scopes, access policy, egress controls và kiểm repository metadata.

Không dùng cùng token quyền deploy làm mirror read credential chỉ vì cả hai cùng nhà cung cấp registry.

## 8. Tách credentials cho snapshot, release và hậu kiểm

POM có thể khai báo hai đích publication:

~~~xml
<distributionManagement>
    <repository>
        <id>corp-release</id>
        <url>https://repo.example.invalid/maven/releases/</url>
    </repository>
    <snapshotRepository>
        <id>corp-snapshot</id>
        <url>https://repo.example.invalid/maven/snapshots/</url>
    </snapshotRepository>
</distributionManagement>
~~~

| Job | Server ID | Quyền nhỏ nhất |
| --- | --- | --- |
| Tải private dependencies | `corp-read` | Read packages trong namespace dự kiến. |
| Publish version `1.1.0-SNAPSHOT` | `corp-snapshot` | Write snapshot repository. |
| Publish version `1.1.0` | `corp-release` | Write release repository. |
| Audit bản vừa publish | `corp-read` hoặc public read | Download/check metadata, checksum. |

Maven Deploy Plugin chọn `snapshotRepository` cho version có `-SNAPSHOT` khi được cấu hình; release version dùng `repository`. Chỉ một `server.id` phù hợp với **đích thực** mới cần cấp cho invocation đó.

Không dùng token quyền admin chung. Repository manager phải enforce quyền read/write và release immutability; `settings.xml` chỉ chọn credential, không tự enforce immutable artifacts.

## 9. settings-publish.xml chỉ tồn tại trong publish context

Với POM có `distributionManagement.repository.id=corp-release`, job publisher có thể có file settings:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <interactiveMode>false</interactiveMode>
    <servers>
        <server>
            <id>corp-release</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
~~~

Không cần đặt token trong file: `MAVEN_REPO_USER`/`MAVEN_REPO_TOKEN` được map qua protected job/step. Phía registry phải giới hạn token **đúng repo và namespace**. Một token được đặt tên "release" nhưng có quyền super-admin vẫn vi phạm least privilege.

**Ranh giới quan trọng:** Maven `mvn clean deploy` có thể thực thi nhiều plugins và tests **trong cùng process environment** với `MAVEN_REPO_TOKEN`. Vì vậy chỉ chạy trên trusted source ref, build extensions/plugins đã review, runner có quyền phù hợp và environment đã duyệt. Step-level secret injection không làm code trong step trở nên an toàn tự động.

## 10. Ví dụ project Maven 3, Java 17 không cần secrets để test

Cấu trúc:

~~~text
ci-maven-settings-demo/
├── pom.xml
├── src/main/java/org/example/ci/Greeting.java
└── src/test/java/org/example/ci/GreetingTest.java
~~~

Mã Java không dùng private dependencies, vì vậy verify job chỉ cần Maven Central/public approved repositories. POM dưới đây có đích publish `.invalid` để mô tả **mapping**, nên **có thể chạy `mvn verify`** nhưng **không chạy `mvn deploy`** cho đến khi cấu hình registry thật, user/permissions và version release hợp lệ.

## 11. pom.xml hoàn chỉnh cho demo

Tệp `ci-maven-settings-demo/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.ci</groupId>
    <artifactId>ci-maven-settings-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <name>CI Maven Settings Demo</name>

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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-deploy-plugin</artifactId>
                <version>3.1.4</version>
            </plugin>
        </plugins>
    </build>

    <distributionManagement>
        <repository>
            <id>corp-release</id>
            <url>https://repo.example.invalid/maven/releases/</url>
        </repository>
    </distributionManagement>
</project>
~~~

`GAV = org.example.ci:ci-maven-settings-demo:1.0.0`. Ví dụ chưa có `snapshotRepository`; chỉ có một release target để mẫu CI publish không bị mismatch. JUnit `test` không kéo vào runtime production.

Các Maven plugin versions đã pin; `maven-deploy-plugin` không tự chạy khi chỉ thực hiện `mvn verify`. Việc commit `distributionManagement` URL không có nghĩa CI đã có secret hoặc đã publish. Với Maven Central thực tế, còn cần source/Javadoc/signatures và publisher policy riêng, nên không coi POM demo là mẫu upload Central hoàn chỉnh.

## 12. Java code và test — kiểm không cần credential

Tệp `src/main/java/org/example/ci/Greeting.java`:

~~~java
package org.example.ci;

public final class Greeting {
    private Greeting() {
    }

    public static String greet(String input) {
        String name = input == null ? "" : input.strip();
        if (name.isEmpty()) {
            name = "guest";
        }
        return "Hello, " + name + "!";
    }
}
~~~

Tệp `src/test/java/org/example/ci/GreetingTest.java`:

~~~java
package org.example.ci;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class GreetingTest {
    @Test
    void trimsName() {
        assertEquals("Hello, Maven!", Greeting.greet(" Maven "));
    }

    @Test
    void defaultsToGuest() {
        assertEquals("Hello, guest!", Greeting.greet("   "));
        assertEquals("Hello, guest!", Greeting.greet(null));
    }
}
~~~

Có hai JUnit test methods và ba assertions. Java 17 hỗ trợ `String.strip()`. Chạy:

~~~bash
mvn --version
java --version
mvn -B -ntp clean verify
~~~

Sau khi Maven resolve plugins/JUnit và tests pass, Maven exit 0. Minh họa một **mảnh code gọi phương thức**:

~~~java
System.out.println(Greeting.greet(" Maven "));
~~~

**Stdout chính xác của riêng lệnh gọi trên:**

~~~text
Hello, Maven!
~~~

Không mô tả mảnh gọi API này như một class `Main` hoàn chỉnh; project là library demo, không có executable JAR manifest để chạy `java -jar`.

## 13. GitHub Actions verify.yml: không cấp deploy token

Tệp `.github/workflows/verify.yml`:

~~~yaml
name: Verify Maven without secrets

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Configure JDK 17
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Test
        run: mvn -B -ntp clean verify
~~~

Không có `secrets.*` trong YAML, không cấu hình release server, không gọi deploy. `permissions: contents: read` hạn chế quyền GitHub `GITHUB_TOKEN`, **không** tự hạn chế một external Maven token nếu bị cấp nhầm.

Với untrusted fork PR, hãy chủ động không đưa secrets vào job. Tránh `pull_request_target` kết hợp checkout PR head rồi chạy Maven trong bối cảnh có credential của base repo.

`actions/checkout@v7` và `actions/setup-java@v6` là major tags theo tài liệu GitHub hiện hành; với supply-chain policy nghiêm ngặt nên pin Actions vào reviewed commit SHAs và cập nhật có review. CI hosted runner phải hỗ trợ action/runtime version tương ứng.

## 14. GitHub Actions publish.yml: approved release, đúng step

Tệp `.github/workflows/publish.yml`:

~~~yaml
name: Publish Maven release

on:
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: maven-release
  cancel-in-progress: false

jobs:
  publish:
    if: github.ref == 'refs/heads/main'
    environment: maven-release
    runs-on: ubuntu-latest

    steps:
      - name: Checkout approved main
        uses: actions/checkout@v7
        with:
          persist-credentials: false

      - name: Set up JDK and Maven credentials template
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          server-id: corp-release
          server-username-env-var: MAVEN_REPO_USER
          server-password-env-var: MAVEN_REPO_TOKEN

      - name: Deploy approved release
        env:
          MAVEN_REPO_USER: ${{ secrets.MAVEN_REPO_USER }}
          MAVEN_REPO_TOKEN: ${{ secrets.MAVEN_REPO_TOKEN }}
        run: mvn -B -ntp clean deploy
~~~

**Cấu hình bên ngoài YAML bắt buộc:**

1. GitHub repository phải có environment `maven-release` được bảo vệ bằng required reviewers, branch/tag restrictions phù hợp và quyền truy cập theo plan; thêm dòng `environment:` **không tự bật review gate**.
2. Secrets `MAVEN_REPO_USER`, `MAVEN_REPO_TOKEN` được đặt ở environment đó, không đưa vào PR verify.
3. Registry cấp cho token write-release **đúng namespace/repository** và nên cấm ghi đè release.
4. POM `distributionManagement.repository.id=corp-release` phải khớp server ID; thay `.invalid` bằng repo thật trước khi chạy.
5. `main` phải là protected/trusted branch, POM/workflow changes đã qua review và release version không bị publish trùng.
6. Maven `clean deploy` có thể chạy tests/plugins trong step có secrets. Không dùng workflow này với untrusted checkout.
7. Sau deploy cần download/check POM/JAR/checksum từ repository đích; `BUILD SUCCESS` chưa đủ.

`workflow_dispatch` kết hợp điều kiện ref main chỉ là một lớp kiểm soát, **không** thay branch protection hay approvals. `concurrency` giúp tránh deployments đồng thời, không thay release immutability.

## 15. setup-java@v6: biến được truyền là **tên**, không phải token

Theo tài liệu `actions/setup-java@v6`, các inputs mới là:

~~~yaml
server-id: corp-release
server-username-env-var: MAVEN_REPO_USER
server-password-env-var: MAVEN_REPO_TOKEN
~~~

Nó tạo Maven server entry tương đương:

~~~xml
<server>
    <id>corp-release</id>
    <username>${env.MAVEN_REPO_USER}</username>
    <password>${env.MAVEN_REPO_TOKEN}</password>
</server>
~~~

Phân biệt:

- `${env.MAVEN_REPO_TOKEN}` là **Maven settings interpolation**.
- `${{ secrets.MAVEN_REPO_TOKEN }}` là **GitHub expression** để lấy secret value và map vào environment step.

Không đưa trực tiếp secret value vào `server-password-env-var`: tham số này **mong đợi tên env var**. Các aliases cũ `server-username`/`server-password` là deprecated theo docs mới; chọn tên mới khi viết workflow hiện hành.

`setup-java` có `settings-path` và `overwrite-settings` để kiểm đường dẫn và việc đè settings hiện hữu. Nếu job cần proxy/mirror phức tạp, quyết định rõ liệu action tạo file mới hay bạn dùng custom `-s`; không âm thầm thay toàn bộ settings của runner.

## 16. Chỉ cấp secrets trong bước cần, nhưng phải hiểu giới hạn

**Workflow-level** env chứa token khiến nhiều jobs có thể nhận nó; **job-level** env kéo dài cả job; **step-level** env chỉ đưa token vào subprocess của bước đó. Step-level là lựa chọn tốt để giảm exposure.

Tuy nhiên:

~~~text
step: mvn clean deploy (có MAVEN_REPO_TOKEN)
    validate -> compile -> test -> package -> verify -> deploy
    Maven plugins, Java tests, subprocesses có thể chạy trong step
~~~

Tất cả có thể đọc environment nếu có quyền. Vì vậy đây **không phải sandbox plugin/test**. Cần source đã review, protected checkout, least-privilege token và runner isolation. Nếu pipeline phải build untrusted code, không đưa deploy secret cùng process.

Không chia sẻ cache/workspace mà untrusted PR có thể thao túng với publisher có credential, trừ khi có cơ chế artifact integrity/provenance đáng tin.

## 17. Tạo settings runtime bằng file tạm khi không có setup-java

Trên Linux/GitHub runner có `RUNNER_TEMP`:

~~~bash
set -eu
umask 077
mkdir -p "$RUNNER_TEMP/maven-verify"
cat > "$RUNNER_TEMP/maven-verify/settings.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <interactiveMode>false</interactiveMode>
    <servers>
        <server>
            <id>corp-read</id>
            <username>${env.MAVEN_READ_USER}</username>
            <password>${env.MAVEN_READ_TOKEN}</password>
        </server>
    </servers>
</settings>
XML
chmod 600 "$RUNNER_TEMP/maven-verify/settings.xml"
mvn -B -ntp -s "$RUNNER_TEMP/maven-verify/settings.xml" verify
~~~

`<<'XML'` ngăn shell tự expand `${env.*}`; Maven sẽ đọc environment khi chạy. File này **chỉ chứa server credentials**, chưa khai báo private repository URL; URL cần được cấp qua POM/profile/mirror tương ứng.

Nếu CI khác GitHub, thay `RUNNER_TEMP` bằng thư mục tạm có quyền phù hợp. Không upload toàn bộ thư mục temp/home làm artifact, không lưu token literal trong file, không dùng shared temp giữa untrusted và release jobs.

Khi có raw token được render vào file do công cụ khác yêu cầu, dùng permissions hạn chế, tránh log/backup/cache, và cleanup sau job. Đừng chạy shell `set -x` hoặc `echo` token để debug.

## 18. Credential origin và rủi ro trùng server.id

Một POM/plugin không tin cậy có thể cố tình khai báo URL khác với cùng server ID mà runner có token. Với Maven 3.9.x, việc khớp server credentials theo ID **không nên được coi là host-bound security boundary**.

Maven Settings Reference hiện hành nói Maven **3.10.0+** có hỗ trợ credential-origin restrictions. Mảnh settings **chỉ dành cho phiên bản hỗ trợ**:

~~~xml
<server>
    <id>corp-release</id>
    <username>${env.MAVEN_REPO_USER}</username>
    <password>${env.MAVEN_REPO_TOKEN}</password>
    <repositoryOrigins>
        <repositoryOrigin>https://repo.example.invalid</repositoryOrigin>
    </repositoryOrigins>
</server>
~~~

Đây là origin dạng scheme/host/port, không phải repo path đầy đủ. Trong Maven 3.10+, `maven.repository.credentialScope` có các mô hình `origin`, `strict` và `id` theo tài liệu.

**Không đưa `repositoryOrigins` vào Maven 3.9.x demo**: bản không hỗ trợ có thể cảnh báo unknown element rồi bỏ qua, khiến bạn có cảm giác bảo vệ giả. Origin restriction là defense-in-depth cho Maven Resolver; plugin tự đọc credentials/OS environment vẫn có thể lấy token.

Biện pháp nền tảng vẫn là: trusted source, role nhỏ, protected environment, hạn chế network egress, ephemeral runner và token lifetime ngắn.

## 19. Maven password encryption không thay secret store

Maven 3 hỗ trợ mã hóa password bằng `settings-security.xml` với master secret. Tuy nhiên tài liệu chính thức Maven 3 mô tả mức bảo vệ **obfuscation-grade**, không đủ để chống người có khả năng đọc cả settings và master file hoặc chạy code cùng user.

Không commit cả:

~~~text
.m2/settings.xml
.m2/settings-security.xml
~~~

và nói “đã encrypt nên an toàn”. CI tốt hơn nên lấy secrets từ vault/CI protected environment, chỉ cấp khi job chạy, dùng token có TTL ngắn và revoke ngay khi bị lộ.

Maven 4 có cơ chế mã hóa password mới riêng; không áp dụng nguyên các bước Maven 3 cho Maven 4 mà chưa đọc tài liệu tương ứng.

## 20. OIDC và short-lived token khi provider hỗ trợ

GitHub Actions hỗ trợ OIDC để trao đổi ID token với cloud/identity provider nhằm lấy access token ngắn hạn, không lưu long-lived cloud key ở GitHub:

~~~text
trusted CI job (repo/ref/environment claims)
             |
             v
GitHub OIDC ID token
             |
             v
provider kiểm trust policy và cấp role hạn chế
             |
             v
short-lived token -> đúng repository/cloud resource
~~~

Job chỉ cần:

~~~yaml
permissions:
  contents: read
  id-token: write
~~~

**khi thật sự dùng OIDC**. `id-token: write` cho phép yêu cầu token, **không tự cấp quyền admin cloud**. Nhà cung cấp phải xác minh repository, ref/tag, environment, audience và role phù hợp.

Không giả định Maven Deploy Plugin tự biết đổi OIDC token sang Maven registry credential. Phải có action/adapter/protocol được provider hỗ trợ rồi map access token phù hợp vào settings. Nếu registry chưa hỗ trợ federation, secret store với scoped token là phương án thực tế.

## 21. Tại sao không dùng pull_request_target với source PR và secrets?

PR có thể thay `pom.xml`, plugin executions, source test files, build scripts và workflow. Những thành phần đó có thể chạy code trong Maven. Nếu `pull_request_target` dùng base repository secrets rồi checkout `head` PR để build, tác giả PR có thể tìm cách thực thi code với quyền CI nhạy cảm.

Quy trình đúng:

1. PR verify không có deploy secrets và không có write GitHub permissions.
2. Review kỹ POM/plugins/`.mvn/extensions.xml`/workflows/scripts.
3. Merge vào protected branch hoặc tạo trusted release tag theo policy.
4. Protected environment release kiểm ref, required reviewers, đúng repository.
5. Publisher checkout đúng trusted ref và chỉ tại lúc đó nhận credential.
6. Không tiêu thụ executable artifact từ untrusted job trong privileged context nếu chưa xác minh provenance.

Với private dependencies, nếu untrusted PR không được cấp read token, đó là security boundary cần giải quyết bằng trusted validation path, không phải lý do bypass và dùng deploy token.

## 22. Secrets có thể rò rỉ dù log tự masking

GitHub masks nhiều secret values trong logs, nhưng:

- Token có thể bị gửi ra ngoài qua network mà không cần xuất hiện trong log.
- Token encode/base64/URL transform có thể không bị mask.
- Plugin/test có thể ghi token vào JAR, Surefire report hoặc build artifact.
- `env`/`printenv` hoặc shell `set -x` có thể in environment.
- `mvn -X` debug output có thể chứa metadata/system properties nhạy cảm.
- Self-hosted runner có thể để lại file settings từ job khác.
- Maven repo cache có thể chứa private artifacts cần quyền kiểm soát.

**KHÔNG thực hiện trong secret-bearing job:**

~~~bash
echo "$MAVEN_REPO_TOKEN"
printenv
set -x
mvn -X deploy
~~~

Chúng được liệt kê như **phản ví dụ**, không phải lệnh cần chạy. Khi debug 401/403, chỉ xuất **server ID, repo URL đã redact nếu nhạy cảm, Maven version, HTTP status, tên env var**, không in giá trị.

Không truyền token qua `-Dpassword=...` trên CLI nếu tránh được: process args, shell history và CI logs có thể lưu giá trị.

## 23. Kiểm effective settings mà không tiết lộ password

Apache Maven Help Plugin có goal:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-settings
~~~

Với settings riêng:

~~~bash
mvn -B -ntp -s .ci/maven/settings-read.xml org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-settings
~~~

Theo tài liệu, `showPasswords` mặc định `false`. **Không bật `-DshowPasswords=true`** trên CI hoặc gửi report hiệu lực có secret cho bên ngoài. Ngay cả khi mật khẩu được ẩn, effective settings có thể tiết lộ URLs, proxies và repo IDs, nên chỉ dùng trong trusted debugging context.

Đây là công cụ kiểm YAML/Settings merge, **không** thay việc kiểm token có quyền thực tế từ registry.

## 24. Phân quyền và rotation ở cấp repository manager

Đặt tên tokens chưa đủ. Registry phải enforce:

- `corp-read` chỉ đọc packages/metadata trong approved namespace.
- `corp-snapshot` chỉ ghi snapshot artifacts trong approved repo.
- `corp-release` chỉ phát hành release namespace đã phê duyệt, không admin/delete.
- Token ký GPG hoặc cloud deploy identity là role riêng, không dùng lại Maven repo token.
- Token cần expiration/rotation, audit actor/CI run/repository/operation.
- Release repository nên cấm overwrite cùng version.
- Có negative tests: read-only không deploy được; snapshot role không ghi release.

Khi một token lộ, **xóa secret khỏi GitHub UI không đủ**: phải revoke token ở issuer, kiểm audit logs, rà soát artifacts/cache có thể chứa token, xử lý incident và tạo credential mới với policy đúng. Thay tên secret nhưng giữ nguyên token value không phải rotation.

Không dùng generic admin token để chữa `401`/`403` rồi để đó vĩnh viễn; phải xác minh auth vs authorization vs immutable repository policy.

## 25. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| PR verify cần deploy token. | Workflow dùng settings/publish credentials chung. | Tách job, chỉ public hoặc trusted read-only. |
| Maven 401 khi private dependency. | Wrong env var, server ID, mirror ID, expired token. | Kiểm names, scopes, target IDs, không in value. |
| Maven 403 khi deploy. | Token thiếu quyền hoặc repo chặn overwrite. | Kiểm server-side roles và GAV. |
| Deploy SNAPSHOT đến release endpoint. | POM thiếu snapshotRepository hoặc version sai. | Kiểm effective version/distributionManagement. |
| Mirror auth fail dù server `central` có token. | Selected mirror ID khác. | Server credential phải khớp `mirror.id`. |
| setup-java sinh settings nhưng token không được dùng. | `server-password-env-var` khác step env key. | Cùng tên env var ở action input và step. |
| Setup-java ghi đè corporate mirror settings. | `overwrite-settings` và path mặc định. | Dùng settings-path/overwrite-settings có chủ đích. |
| Protected job không chờ reviewer. | Environment rules chưa bật ở GitHub. | Cấu hình required reviewers/branch protection. |
| Release token có mặt ở `mvn verify`. | Secrets được inject ở workflow/job-level. | Chỉ inject publisher step/job. |
| Dùng `-s` nhưng test vẫn thấy token. | Process environment vẫn được share. | Tách runner/jobs và trusted source. |
| GitHub logs mask secret nhưng file artifacts lộ token. | Build script ghi secrets vào file. | Dừng/revoke, scan artifacts, sửa pipeline. |
| Maven 3.9 không hiểu `repositoryOrigins`. | Cấu hình dùng feature mới. | Dùng Maven hỗ trợ hoặc bỏ tag, vẫn hạn chế quyền. |
| Fork PR không truy cập private artifact. | Security policy không cấp secrets cho untrusted PR. | Trusted follow-up/read-only approach, không cấp deploy. |
| Plugin download từ repo không mong muốn. | Mirror/pluginRepositories không được quản lý. | Restrict repositories/egress, pin plugins. |
| Token bị xóa trong CI nhưng còn dùng được. | Chưa revoke ở provider. | Revoke và audit registry. |
| Self-hosted runner còn `~/.m2/settings.xml` của job trước. | Shared home/trust boundary. | Ephemeral runner, cleanup, dedicated identity. |

**Thứ tự điều tra:** loại CI job → event/ref trust → repository cần read hay write → id matching → profile/mirror → env mapping → token role/status → Maven version/network/SSL → registry policy.

## 26. Checklist triển khai thực tế

- [ ] Mỗi job đã được phân loại public-read, private-read, snapshot-write, release-write hoặc signing.
- [ ] Untrusted PR jobs không có deploy secrets/GPG private key.
- [ ] Settings templates không chứa credential literal, chỉ env interpolation.
- [ ] POM distributionManagement ID trùng settings server ID của publisher.
- [ ] Mirror ID và private repository ID được chọn đúng khi resolve.
- [ ] Release và snapshot token/roles không được dùng lẫn.
- [ ] Protected environment có reviewer và branch/tag restrictions thực sự.
- [ ] Secret chỉ được inject vào job/step cần, không blanket workflow env.
- [ ] Trusted source đã được review trước khi Maven chạy trong secret-bearing job.
- [ ] Build plugins/extensions và workflow actions được pin/review.
- [ ] Không upload/copy settings, printenv, private key hay token vào artifacts/caches.
- [ ] Runner không dùng shared home với untrusted jobs, có cleanup.
- [ ] Maven 3.9 không được giả định có credential origin binding của Maven 3.10+.
- [ ] OIDC chỉ bật ở jobs cần, có provider trust claims chặt.
- [ ] Kiểm 401/403 mà không in credentials hoặc `mvn -X`.
- [ ] Có plan revoke/rotate và owner/security audit log.
- [ ] Token read-only không được deploy; token snapshot không ghi release.
- [ ] Release POM/JAR được kiểm từ repository đích sau deploy.
- [ ] CI run, source SHA, GAV, checksum, approver và repo URL được lưu làm evidence.

## 27. Câu hỏi tự kiểm tra

1. **POM có nên chứa username/password không?** Không; để trong CI secret store và Maven settings runtime.
2. **Server ID có phải token không?** Không; là khóa ghép credentials với repository/mirror.
3. **`${env.MAVEN_REPO_TOKEN}` là giá trị thực không?** Không; Maven lấy value từ environment.
4. **`-s` có cô lập secrets khỏi plugins không?** Không.
5. **Mirror auth cần `central` ID hay mirror ID?** Thường phải match ID của mirror được chọn.
6. **SNAPSHOT và release cần cùng token không?** Không; nên tách quyền/repository.
7. **Job PR không có token nhưng build public dependencies có chạy được không?** Có nếu mạng/repository và plugins được phép.
8. **`actions/setup-java@v6` `server-password-env-var` là secret value hay tên biến?** Tên biến.
9. **`environment: maven-release` có tự yêu cầu approval không?** Không; phải cấu hình protection rules.
10. **`permissions: contents: read` có giới hạn quyền external Maven token không?** Không.
11. **Secrets chỉ xuất hiện trong step deploy có bảo vệ khỏi tests/plugins trong step không?** Không.
12. **Maven 3 password encryption có thay CI vault không?** Không.
13. **Maven 3.9 đã có repositoryOrigins như Maven 3.10+ chưa?** Không nên giả định.
14. **OIDC id-token:write tự cấp quyền admin cloud không?** Không; cloud trust policy quyết định.
15. **`pull_request_target` chạy code PR với secrets có nguy hiểm không?** Có.
16. **Maven 401 có nên debug bằng `echo "$TOKEN"` không?** Không.
17. **Xóa token trong CI đã đủ sau khi leak chưa?** Chưa; cần revoke tại issuer.
18. **Multi-module `-pl` có cô lập credentials per module không?** Không.
19. **BUILD SUCCESS có đủ xác nhận artifact được publish đúng không?** Không; phải kiểm remote POM/JAR/GAV/checksums.
20. **Quyền tối thiểu được chứng minh bằng gì?** Server-side role policies và negative permission tests.

## 28. Tài liệu chính thức

- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html): user/global settings, servers, mirrors, profiles, env interpolation và credential-origin restrictions trên Maven mới.
- [Apache Maven — Configuring Maven](https://maven.apache.org/guides/mini/guide-configuring-maven.html): distributionManagement và settings server ID.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html): repositories, pluginRepositories, distributionManagement, build plugins.
- [Apache Maven — Password Encryption](https://maven.apache.org/guides/mini/guide-encryption.html): giới hạn bảo vệ Maven 3 settings-security.xml.
- [Apache Maven — Password Encryption Maven 4](https://maven.apache.org/guides/mini/guide-encryption-4.html): migration và cơ chế encryption mới.
- [Apache Maven — Maven Deploy Plugin](https://maven.apache.org/plugins/maven-deploy-plugin/): deploy lifecycle và remote repository.
- [Apache Maven Help Plugin — effective-settings](https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html): xem effective settings với passwords được ẩn mặc định.
- [Apache Maven — Maven Wrapper](https://maven.apache.org/tools/wrapper/): pin Maven distribution khi project có wrapper.
- [GitHub Actions — actions/setup-java](https://github.com/actions/setup-java): Java install, Maven settings generation và biến môi trường theo phiên bản hiện hành.
- [GitHub Actions — setup-java advanced usage](https://github.com/actions/setup-java/blob/main/docs/advanced-usage.md): server IDs, generated settings, publishing.
- [GitHub Docs — Secrets](https://docs.github.com/en/actions/concepts/security/secrets): environment/repository/organization secrets.
- [GitHub Docs — Deployments and Environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments): protected environment và required reviewers.
- [GitHub Docs — OpenID Connect](https://docs.github.com/en/actions/concepts/security/openid-connect): short-lived identity tokens.
- [GitHub Docs — OIDC for Cloud Providers](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-cloud-providers): `id-token: write` và trust policies.
- [GitHub Docs — Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use): CI supply-chain hardening và untrusted input.

**Kết luận:** CI Maven cần một `settings.xml` **theo phạm vi công việc**, không phải một bản chứa mọi credential. Dùng POM để khai báo repositories/đích deploy, Maven settings để nối server ID với env-based secrets, CI protected environments để giới hạn thời điểm và ref được cấp, repository manager để giới hạn hành động read/write. Tách PR verify không secrets khỏi trusted read-only build, snapshot publication, approved release và artifact audit. Với Maven 3.9.x, không coi server ID là hostname security boundary; cần thêm source trust, isolation, egress controls, short-lived credentials và rotation. Mục tiêu không chỉ `BUILD SUCCESS` mà là **mỗi job không có quyền vượt công việc của nó**.
