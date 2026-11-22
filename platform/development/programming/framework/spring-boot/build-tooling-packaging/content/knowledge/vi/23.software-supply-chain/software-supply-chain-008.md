# Quản lý secrets cho Maven settings, Gradle credentials và registry trong CI

## 1. Mục tiêu

Dự án Spring Boot có thể cần credentials để tải dependencies từ Maven repository riêng, resolve Gradle plugins nội bộ, publish artifacts, pull CNB builder/run images hoặc push OCI application image. Nếu đặt username, password hay token trực tiếp trong POM, Gradle build script, Dockerfile hoặc script CI, chúng có thể lọt vào Git, logs, cache, build artifacts hoặc container image.

Bài này trình bày ba kênh độc lập:

1. **Maven settings:** credentials cho repository, mirror và deployment đặt trong settings.xml, ghép theo server ID.
2. **Gradle credentials:** repository khai báo loại credential; Gradle lấy giá trị từ Gradle properties/environment variables bằng typed API.
3. **Spring Boot image registry:** credentials pull builder/run images và credentials publish application image được cấu hình riêng; có thể dùng Docker credential helper/store.

Mục tiêu là phân biệt đúng secret, cấu hình các công cụ mà không hard-code password, cấp secret từ CI secret store, ngăn rò rỉ qua command line/logs/cache và xử lý sự cố credential bị lộ. Ví dụ sử dụng Maven, Gradle Kotlin DSL, Spring Boot 3.5 và GitHub Actions.

## 2. Phân loại secrets

| Loại credential | Consumer | Vị trí phù hợp | Không nên đặt ở |
| --- | --- | --- | --- |
| Maven repository read | Maven resolver | User/CI settings.xml | POM được commit |
| Maven artifact publish | Maven Deploy Plugin | settings.xml, server ID khớp deployment ID | Tham số CLI -Dpassword |
| Gradle dependency repo | Gradle resolver | Typed credentials + Gradle properties/env | Literal trong build script |
| Gradle plugin repo | Gradle plugin resolver | pluginManagement + properties/env | Version catalog |
| Gradle publishing | Gradle publishing task | Publishing repository + typed credentials | Project gradle.properties được commit |
| CNB builder/run registry | Spring Boot plugin/Docker client | builderRegistry hoặc Docker credential helper | Maven servers |
| OCI image publish | Spring Boot plugin/Docker client | publishRegistry hoặc Docker credential helper | Dockerfile/image environment |
| Application runtime secret | Ứng dụng khi chạy | Secret manager/orchestrator | JAR, image layer, application.properties |

Các kênh này không tự cấp quyền cho nhau. Maven server ID không tự cấp quyền Docker registry; Docker login không làm Maven có quyền đọc private Maven repository. Dùng credential riêng cho từng mục đích và chỉ cấp quyền tối thiểu: read-only khi chỉ tải dependencies, write/push khi phát hành.

## 3. Maven: settings.xml và server ID

### 3.1. POM mô tả repository; settings giữ credentials

Maven định nghĩa repository download trong repositories, plugin repository trong pluginRepositories và repository publish trong distributionManagement của POM. Thông tin username/password thuộc môi trường của người chạy build, vì vậy đặt trong settings.xml.

~~~xml
<repositories>
    <repository>
        <id>internal-maven</id>
        <url>${env.MAVEN_REPO_URL}</url>
    </repository>
</repositories>

<distributionManagement>
    <repository>
        <id>internal-releases</id>
        <url>${env.MAVEN_DEPLOY_URL}</url>
    </repository>
</distributionManagement>
~~~

internal-maven là ID để tải dependency; internal-releases là ID để deploy artifact. ID không phải username hoặc URL. Environment variables cung cấp endpoint theo môi trường.

### 3.2. settings.xml với environment interpolation

File user settings thường ở ~/.m2/settings.xml trên Linux/macOS hoặc %USERPROFILE%/.m2/settings.xml trên Windows.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
          https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <servers>
        <server>
            <id>internal-maven</id>
            <username>${env.MAVEN_REPO_USERNAME}</username>
            <password>${env.MAVEN_REPO_PASSWORD}</password>
        </server>
        <server>
            <id>internal-releases</id>
            <username>${env.MAVEN_PUBLISH_USERNAME}</username>
            <password>${env.MAVEN_PUBLISH_PASSWORD}</password>
        </server>
    </servers>
</settings>
~~~

Maven hỗ trợ environment interpolation cho các giá trị trong settings. File chỉ lưu tên biến; giá trị thực được cấp bởi môi trường:

- MAVEN_REPO_USERNAME/MAVEN_REPO_PASSWORD cho quyền đọc.
- MAVEN_PUBLISH_USERNAME/MAVEN_PUBLISH_PASSWORD cho quyền deploy.
- Nếu biến không được cấp, repository có thể trả lỗi xác thực; CI nên fail rõ khi thiếu biến bắt buộc.
- Không commit settings cá nhân có credential thật. Settings thực nằm ở user home hoặc thư mục tạm của runner.

### 3.3. ID phải khớp repository, mirror hoặc deployment target

Maven ghép credential bằng **ID**, không ghép theo hostname:

- Server ID phải khớp repository ID của request.
- Deployment server ID phải khớp distributionManagement repository ID.
- Nếu Maven dùng mirror, credentials thường được tra theo ID của mirror đang được sử dụng.
- Plugin repository có ID riêng và có thể cần server entry riêng.

Ví dụ mirror:

~~~xml
<mirrors>
    <mirror>
        <id>company-mirror</id>
        <mirrorOf>*</mirrorOf>
        <url>${env.MAVEN_MIRROR_URL}</url>
    </mirror>
</mirrors>
~~~

Nếu request được route qua company-mirror, server credentials phải có ID company-mirror. Nếu repository ID là internal-maven nhưng settings chỉ có server ID maven-user, Maven không tự ghép chúng chỉ vì URL cùng host.

### 3.4. Dùng settings file riêng trong CI

Khi project đã có Maven Wrapper, chỉ định settings file bằng tùy chọn -s:

~~~bash
./mvnw -s "$RUNNER_TEMP/maven-settings.xml" -B -ntp clean verify
~~~

PowerShell:

~~~powershell
.\mvnw.cmd -s "$env:RUNNER_TEMP/maven-settings.xml" -B -ntp clean verify
~~~

File tạm nên có quyền đọc hạn chế, không upload thành artifact và được dọn theo retention policy. Nếu file chỉ chứa environment references thì secret values vẫn đến từ environment của Maven process. Xóa file sau build không giúp nếu trước đó đã cache/upload hoặc in nội dung ra logs.

### 3.5. Maven password encryption không phải secret vault

Maven 3 có lệnh encrypt master password, settings-security.xml và encrypt password để lưu password ở dạng mã hóa/obfuscated. Tuy nhiên tài liệu Maven 3 lưu ý master password được mã hóa bằng **hard-coded key**. Hãy coi cơ chế này là obfuscation, không phải vault hoặc bảo vệ mạnh trước người có thể đọc các file liên quan.

Thực hành:

- Dùng CI secret store/Vault để cấp credentials lúc build.
- Nếu dùng Maven encryption trên máy developer, vẫn bảo vệ quyền đọc ~/.m2 và account hệ điều hành.
- Không commit settings.xml hoặc settings-security.xml chứa dữ liệu thật.
- Không truyền password bằng -Dpassword hoặc command-line arguments dễ xuất hiện trong process list.
- Maven 4 có hướng dẫn encryption riêng; không trộn hướng dẫn/file format Maven 3 và Maven 4 khi chưa xác nhận version.

## 4. Gradle: typed credentials và Gradle properties

### 4.1. Repository khai báo loại credential

Gradle Kotlin DSL:

~~~kotlin
import org.gradle.api.credentials.PasswordCredentials

dependencyResolutionManagement {
    repositories {
        maven {
            name = "internalRepo"
            url = uri(providers.environmentVariable("INTERNAL_REPO_URL").get())
            credentials(PasswordCredentials::class)
        }
    }
}
~~~

Với repository name internalRepo, Gradle tra hai properties: internalRepoUsername và internalRepoPassword. Typed API cho build biết loại credential cần dùng mà không chứa literal password trong script. URL không phải secret; có thể lấy từ biến môi trường riêng theo môi trường chạy.

### 4.2. Cấp Gradle credentials qua environment variables

Gradle hỗ trợ project properties từ environment variables có prefix ORG_GRADLE_PROJECT_. Với ví dụ trên, CI cấp:

~~~bash
ORG_GRADLE_PROJECT_internalRepoUsername
ORG_GRADLE_PROJECT_internalRepoPassword
~~~

GitHub Actions environment:

~~~yaml
env:
  ORG_GRADLE_PROJECT_internalRepoUsername: ${{ secrets.INTERNAL_REPO_USERNAME }}
  ORG_GRADLE_PROJECT_internalRepoPassword: ${{ secrets.INTERNAL_REPO_PASSWORD }}
~~~

Property names phải khớp repository name. Nếu đổi name thành companyMaven, hai properties cũng phải đổi thành companyMavenUsername và companyMavenPassword. Không truyền secret bằng -PinternalRepoPassword: command-line arguments có thể bị quan sát bởi process khác hoặc ghi vào audit logs.

### 4.3. gradle.properties cho developer workstation

Một lựa chọn là file Gradle User Home, thường ở ~/.gradle/gradle.properties hoặc thư mục GRADLE_USER_HOME. File có thể chứa hai property internalRepoUsername và internalRepoPassword; developer điền giá trị tại máy cá nhân, lấy từ password manager/secret store của tổ chức.

File này lưu plain text:

- Không commit file có credentials vào project.
- Ưu tiên Gradle User Home thay vì project-root gradle.properties.
- Trên POSIX, giới hạn quyền, ví dụ chmod 700 ~/.gradle và chmod 600 ~/.gradle/gradle.properties.
- Không dùng chung Gradle User Home có credentials giữa user/CI jobs có mức tin cậy khác nhau.
- Xóa/rotate credential khi user rời team hoặc quyền truy cập không còn cần thiết.

Project gradle.properties phù hợp với non-secret build properties như version hoặc JVM settings. Không dùng nó làm nơi lưu password chỉ vì tiện.

### 4.4. Plugin repository và dependency repository là hai cấu hình

Gradle resolve plugins trong pluginManagement, tách khỏi repositories dùng cho application dependencies:

~~~kotlin
import org.gradle.api.credentials.PasswordCredentials

pluginManagement {
    repositories {
        maven {
            name = "companyPlugins"
            url = uri(providers.environmentVariable("PLUGIN_REPO_URL").get())
            credentials(PasswordCredentials::class)
        }
        gradlePluginPortal()
    }
}
~~~

CI cấp ORG_GRADLE_PROJECT_companyPluginsUsername và ORG_GRADLE_PROJECT_companyPluginsPassword. Credentials của internalRepo không tự dùng cho companyPlugins.

### 4.5. Gradle publishing repository

Với maven-publish:

~~~kotlin
import org.gradle.api.credentials.PasswordCredentials

publishing {
    repositories {
        maven {
            name = "companyReleases"
            url = uri(providers.environmentVariable("PUBLISH_REPO_URL").get())
            credentials(PasswordCredentials::class)
        }
    }
}
~~~

CI cấp ORG_GRADLE_PROJECT_companyReleasesUsername và ORG_GRADLE_PROJECT_companyReleasesPassword. Tách quyền đọc dependencies khỏi quyền deploy; job chỉ chạy test/compile không cần publish token.

### 4.6. Configuration Cache, Provider và Gradle Daemon

Gradle Configuration Cache lưu task graph/state trên đĩa. Nếu build đọc secret eager trong configuration rồi gán vào custom task fields, giá trị có thể bị serialize vào state. Gradle mã hóa cache, nhưng không nên coi đó là vault hoặc đặt cache ở network share mà nhiều người đọc được.

- Dùng typed repository credentials API để Gradle tra properties.
- Với task cần env secret, dùng Provider lazy như providers.environmentVariable("TOKEN") và chỉ resolve khi thực thi.
- Tránh gọi System.getenv("TOKEN") sớm trong configuration rồi ghi giá trị ra task state/logs.
- Hạn chế quyền truy cập .gradle/configuration-cache và Gradle User Home.
- Không commit .gradle/, cache hoặc credential files.
- Kiểm compatibility Configuration Cache của plugin/task đang dùng.

Gradle Daemon là JVM sống lâu giữa các build. Trên runner dùng chung hoặc build code không tin cậy, cô lập Gradle User Home/daemon theo job và tránh tái sử dụng process qua trust boundaries.

## 5. Spring Boot: builderRegistry và publishRegistry

### 5.1. Tách pull và push

Khi chạy spring-boot:build-image hoặc bootBuildImage, plugin có thể cần:

1. Pull **builder image** chứa buildpacks và CNB lifecycle.
2. Pull **run image** dùng làm nền runtime.
3. Push **application image** nếu bật publish.

| Thuộc tính | Quyền | Mục đích |
| --- | --- | --- |
| docker.builderRegistry | Pull/read | Auth khi builder/run image ở private registry |
| docker.publishRegistry | Push/write | Auth khi publish application image |
| docker.host | Docker Engine API | Địa chỉ daemon, không phải registry password |

Maven settings server credentials và Gradle repository credentials không tự động trở thành Docker registry credentials.

### 5.2. Maven Plugin: environment interpolation

Đặt snippet sau trong spring-boot-maven-plugin ở build/plugins:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <image>
            <name>${env.IMAGE_NAME}</name>
            <publish>true</publish>
        </image>
        <docker>
            <builderRegistry>
                <username>${env.BUILDER_REGISTRY_USERNAME}</username>
                <password>${env.BUILDER_REGISTRY_PASSWORD}</password>
            </builderRegistry>
            <publishRegistry>
                <username>${env.IMAGE_REGISTRY_USERNAME}</username>
                <password>${env.IMAGE_REGISTRY_PASSWORD}</password>
            </publishRegistry>
        </docker>
    </configuration>
</plugin>
~~~

Đây là plugin snippet, không phải POM độc lập. Maven lấy values từ environment của process.

- builderRegistry chỉ cần nếu builder/run images cần xác thực.
- publishRegistry chỉ cần nếu output image cần push.
- publish=true bật publish; nếu chỉ muốn local image, không bật publish và không cấp push token.
- IMAGE_NAME phải là image reference có registry/repository/tag phù hợp.
- Nếu registry public hoặc Docker credential helper đã xử lý, có thể bỏ credentials tương ứng.

### 5.3. Gradle BootBuildImage: Provider lazy

Trong build.gradle.kts đã apply Spring Boot Gradle Plugin:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

tasks.named<BootBuildImage>("bootBuildImage") {
    imageName.set(providers.environmentVariable("IMAGE_NAME"))
    publish.set(true)

    docker {
        builderRegistry {
            username.set(
                providers.environmentVariable("BUILDER_REGISTRY_USERNAME")
            )
            password.set(
                providers.environmentVariable("BUILDER_REGISTRY_PASSWORD")
            )
        }
        publishRegistry {
            username.set(
                providers.environmentVariable("IMAGE_REGISTRY_USERNAME")
            )
            password.set(
                providers.environmentVariable("IMAGE_REGISTRY_PASSWORD")
            )
        }
    }
}
~~~

Provider được nối vào Gradle task properties, tránh hard-code secret và tránh tự đọc environment sớm trong build script. CI phải cấp đúng các biến. Nếu builder public hoặc image chỉ được tạo local, bỏ cấu hình không cần thiết.

### 5.4. Docker config và credential helpers

Spring Boot plugins có thể đọc Docker CLI config (thường $HOME/.docker/config.json) để tìm auth nếu không khai báo trực tiếp. Docker có thể dùng credential helper/store hoặc static auth.

Static auth trong config có thể chỉ là Base64-encoded username/password, **không phải encryption**. Không commit config.json hoặc upload nó thành artifact. Trên runner, ưu tiên helper/secret integration, hoặc config tạm có permission hạn chế và được dọn sau job.

Docker login dùng password qua stdin:

~~~bash
printf '%s' "$REGISTRY_TOKEN" | docker login "$REGISTRY_HOST" --username "$REGISTRY_USERNAME" --password-stdin
~~~

Không dùng docker login -p TOKEN hoặc truyền token làm command-line argument. Không echo "$REGISTRY_TOKEN" ra console. Nếu không có credential helper, file Docker config có thể chứa auth Base64; bảo vệ quyền đọc và vòng đời file.

### 5.5. Build local khác publish

spring-boot:build-image/bootBuildImage có thể tạo image vào daemon store mà không publish. Khi publish:

- Image name phải chứa đúng registry/repository/tag.
- publishRegistry hoặc Docker credential helper cần quyền push.
- Builder pull thành công không chứng minh push permission có sẵn.
- Image ở remote daemon không tự xuất hiện trong Docker Desktop local.
- Nếu local image tồn tại nhưng registry không có, kiểm publish flag và push logs thay vì đổi Docker host.

## 6. Build-time secrets và runtime secrets

Có ba thời điểm sử dụng:

**Dependency resolution:** Maven/Gradle cần credentials để tải thư viện/plugin. Cấp cho process build qua settings/properties. Không đưa password vào application source.

**CNB builder:** Buildpack có thể cần proxy hoặc credentials để tải artifact trong lifecycle. Biến environment của Spring Boot plugin không phải generic secret vault; buildpack có thể log hoặc ghi một số dữ liệu vào output. Nếu buildpack cần secret trong lúc build, dùng secret binding/credential integration mà builder hỗ trợ, mount read-only khi có thể và xác minh giá trị không vào image layers.

**Application runtime:** Database password/API key phải được cấp khi container chạy từ secret manager/orchestrator, ví dụ Kubernetes Secret hoặc cloud secret manager. Không bake vào application.properties, Dockerfile ENV, buildpack image environment hoặc JAR.

Credential tải dependency không phải credential runtime; credential pull builder không phải credential push application image.

## 7. CI: đưa secrets từ secret store vào đúng job

### 7.1. Quy trình release

Một job release nên:

1. Checkout revision đã được tin cậy.
2. Chọn JDK và Maven/Gradle Wrapper đã review.
3. Lấy secret từ CI secret store/Vault hoặc OIDC.
4. Tạo settings/properties/config tạm có permission hạn chế.
5. Chạy test/verify trước publish.
6. Build image và publish với quyền tối thiểu.
7. Xác minh image tag/digest.
8. Dọn temporary settings, Docker config và workspace theo retention policy.

Không cấp publish secrets cho mọi pull request. Job kiểm thử code chưa review nên chạy không có release secrets; nếu cần private dependencies, dùng read-only token hoặc mirror/proxy dành riêng cho CI.

### 7.2. GitHub Actions Maven snippet

Ví dụ release workflow chỉ chạy trên tag. Environment production có thể gắn approval/protection rules:

~~~yaml
name: publish-image

on:
  push:
    tags:
      - "v*"

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: production
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"

      - name: Verify and publish
        shell: bash
        env:
          MAVEN_REPO_USERNAME: ${{ secrets.MAVEN_REPO_USERNAME }}
          MAVEN_REPO_PASSWORD: ${{ secrets.MAVEN_REPO_PASSWORD }}
          BUILDER_REGISTRY_USERNAME: ${{ secrets.BUILDER_REGISTRY_USERNAME }}
          BUILDER_REGISTRY_PASSWORD: ${{ secrets.BUILDER_REGISTRY_PASSWORD }}
          IMAGE_REGISTRY_USERNAME: ${{ secrets.IMAGE_REGISTRY_USERNAME }}
          IMAGE_REGISTRY_PASSWORD: ${{ secrets.IMAGE_REGISTRY_PASSWORD }}
        run: |
          set -eu
          install -d -m 700 "$RUNNER_TEMP/maven"
          cat > "$RUNNER_TEMP/maven/settings.xml" <<'EOF'
          <settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
            <servers>
              <server>
                <id>internal-maven</id>
                <username>${env.MAVEN_REPO_USERNAME}</username>
                <password>${env.MAVEN_REPO_PASSWORD}</password>
              </server>
            </servers>
          </settings>
          EOF
          chmod 600 "$RUNNER_TEMP/maven/settings.xml"
          ./mvnw -s "$RUNNER_TEMP/maven/settings.xml" -B -ntp clean verify
          ./mvnw -s "$RUNNER_TEMP/maven/settings.xml" -B -ntp spring-boot:build-image
~~~

Ví dụ giả định POM đã cấu hình publish và publishRegistry. Nếu builder/run images public, bỏ builder credentials. Nếu chỉ tạo local image, bỏ publish config và không cấp push token. File settings tạm chứa environment references, không chứa secret values thực.

### 7.3. GitHub Actions Gradle environment

Với repository Gradle tên internalRepo, cấp:

~~~yaml
env:
  ORG_GRADLE_PROJECT_internalRepoUsername: ${{ secrets.INTERNAL_REPO_USERNAME }}
  ORG_GRADLE_PROJECT_internalRepoPassword: ${{ secrets.INTERNAL_REPO_PASSWORD }}
  BUILDER_REGISTRY_USERNAME: ${{ secrets.BUILDER_REGISTRY_USERNAME }}
  BUILDER_REGISTRY_PASSWORD: ${{ secrets.BUILDER_REGISTRY_PASSWORD }}
  IMAGE_REGISTRY_USERNAME: ${{ secrets.IMAGE_REGISTRY_USERNAME }}
  IMAGE_REGISTRY_PASSWORD: ${{ secrets.IMAGE_REGISTRY_PASSWORD }}
~~~

Sau đó:

~~~bash
./gradlew --no-daemon clean test bootBuildImage
~~~

Các biến ORG_GRADLE_PROJECT_... cấp Gradle properties cho repository; các biến registry được BootBuildImage Provider đọc. Không lưu chúng trong project gradle.properties.

### 7.4. Forked pull requests và quyền workflow

GitHub Actions không cấp repository secrets thông thường cho workflow chạy từ forked pull request (ngoại lệ có quy tắc riêng cho GITHUB_TOKEN với quyền bị giới hạn). Vì vậy:

- Chạy unit tests/compile trên PR mà không cần publish credentials.
- Nếu cần private dependency, cấp read-only token theo policy hoặc dùng CI mirror.
- Chỉ cấp publish secret trong release job/protected environment.
- Không dùng pull_request_target rồi checkout/thực thi code không tin cậy với secrets.
- Giới hạn branch/tag được phép deploy và người có quyền tạo release.
- Pin action versions/commit SHAs theo chính sách supply-chain của tổ chức.

### 7.5. OIDC và token ngắn hạn

Nếu cloud/registry hỗ trợ OpenID Connect, CI có thể chứng minh identity workflow để nhận credential ngắn hạn thay cho static access key. Trust policy nên giới hạn repository, branch/tag, environment và audience. Workflow cần permission id-token: write nếu provider yêu cầu.

OIDC không tự động hoạt động với mọi Maven repository hoặc Docker registry; provider phải hỗ trợ federation. Nếu không, dùng token ngắn hạn có scope nhỏ và rotation định kỳ.

## 8. Ngăn secret lọt vào logs, cache và artifacts

### 8.1. Không in environment hoặc bật debug bừa bãi

Không dùng các lệnh này trong job chứa secrets:

~~~bash
env
printenv
echo "$MAVEN_REPO_PASSWORD"
set -x
mvn -X
./gradlew --debug
~~~

env/printenv có thể dump toàn bộ biến; shell trace ghi lệnh đã expand; Maven -X/Gradle --debug có thể in cấu hình/metadata nhạy cảm. Dùng set -eu thay vì set -x. Nếu secret động cần mask, gọi cơ chế mask của CI trước khi giá trị có thể xuất hiện trong logs; masking không thay việc tránh log.

### 8.2. Không upload file nhạy cảm

Không cache hoặc upload các file này:

- ~/.m2/settings.xml và settings-security.xml.
- ~/.gradle/gradle.properties có credential.
- $DOCKER_CONFIG/config.json.
- Temporary Maven settings/Docker config.
- Gradle Configuration Cache hoặc Gradle User Home chứa state nhạy cảm.
- Logs có request headers, token hoặc environment dumps.

Dùng .gitignore/.dockerignore để ngăn file local nhạy cảm vào repository/build context. Không ghi secret vào generated source, application resources, manifest hay build metadata.

### 8.3. Docker config và image layers

Nếu không có credential helper, Docker config có thể lưu Base64 auth. Bảo vệ file như plaintext: không commit, không đưa vào Docker context, không upload thành artifact. Trên runner ephemeral, dùng DOCKER_CONFIG tạm với quyền hạn chế và dọn sau job.

Không đưa registry token vào Dockerfile ARG/ENV, image label, CNB build environment hoặc image layer. Nếu cần buildpack truy cập private artifact, dùng secret binding/credential mechanism chuyên dụng mà buildpack hỗ trợ.

### 8.4. Gradle cache và daemon

Gradle User Home chứa credentials, plugin/dependency cache, init scripts và daemon state. Hạn chế quyền truy cập thư mục này và không dùng chung writable home giữa CI jobs khác trust level. Configuration Cache được mã hóa nhưng vẫn cần bảo vệ cache directory/key. Remote build cache nên giới hạn quyền push cho trusted builds; untrusted PR builds nên pull-only hoặc namespace riêng.

### 8.5. Khi secret đã lộ

Coi credential đã xuất hiện trong logs, artifacts, Git hoặc image là **đã bị lộ**:

1. Revoke/rotate credential ngay.
2. Kiểm audit logs để biết tài nguyên nào có thể đã được truy cập.
3. Giới hạn/xóa log hoặc artifact nhạy cảm theo retention policy.
4. Kiểm cache, Docker image, Git history và workflow artifacts.
5. Cấp credential mới với quyền tối thiểu.
6. Sửa nguyên nhân làm secret được in/đóng gói; chỉ xóa một dòng log là chưa đủ.

## 9. Troubleshooting

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Maven HTTP 401 khi resolve | Server ID không khớp repository/mirror | So ID request thực tế với server ID |
| Maven download được nhưng deploy 401 | Thiếu server ID của distributionManagement | Thêm deploy credentials riêng |
| Maven mirror không nhận credentials | Server entry đặt ID repository gốc thay vì mirror | Khớp ID mirror thực tế |
| Maven env placeholder không resolve | CI không cấp env hoặc tên biến sai | Kiểm tên biến không in value, kiểm đúng Maven process |
| Maven encrypted password bị coi là plaintext | Hiểu nhầm Maven 3 encryption thành vault | Dùng CI secret store; bảo vệ settings/security files |
| Gradle báo thiếu credentials | Property names không khớp repository name | Kiểm name và repoNameUsername/Password |
| Gradle plugin repo không resolve | Chỉ cấu hình credentials ở dependency repo | Thêm credentials trong pluginManagement |
| Gradle secret xuất hiện trong Git diff | Literal trong build script/project properties | Revoke nếu đã commit, chuyển sang user home/env, kiểm Git history |
| Gradle Configuration Cache chứa dữ liệu nhạy cảm | Secret đọc eager ở configuration | Dùng typed API/Provider lazy, giới hạn cache access |
| Spring Boot không pull builder | Thiếu builderRegistry auth hoặc Docker credential helper | Kiểm builder/run registry credentials |
| Pull builder OK, push app 401 | Builder read credential không có push quyền | Kiểm publishRegistry và publish permission |
| Docker login OK nhưng plugin không auth | Khác user/DOCKER_CONFIG/context | Kiểm config của đúng Maven/Gradle process |
| Registry auth thất bại | Token hết hạn/scope sai/registry host sai | Kiểm quyền pull/push, tag và endpoint |
| Secrets rỗng trên fork PR | CI không chuyển secrets cho fork | Không yêu cầu release secrets trong PR job |
| Token xuất hiện trong logs | Shell trace/debug/echo/command args | Rotate, audit, sửa logging và workflow |
| Runtime app thiếu DB secret | Secret chưa inject lúc deploy | Dùng orchestrator/secret manager, không bake vào image |

Quy trình debug: xác định **pha** (dependency, plugin, builder pull, image push, runtime), xác định **consumer**, kiểm **ID/property name**, kiểm secret được cấp cho đúng job, xác minh quyền read/pull hay write/push, rồi mới thay đổi cấu hình. Không in password/token để xác nhận.

## 10. Bài tập và đáp án

**Bài 1.** POM repository ID là internal-maven nhưng settings server ID là maven-user. Maven có ghép theo hostname không?

**Đáp án:** Không. Maven ghép bằng ID. Server ID phải khớp repository/mirror ID thực tế.

**Bài 2.** Có thể commit settings.xml nếu password đã mã hóa bằng Maven 3 không?

**Đáp án:** Không nên. Maven 3 encryption không phải secret vault; file vẫn phải được bảo vệ như chứa plaintext.

**Bài 3.** Gradle repository tên internalRepo. CI cần property names nào?

**Đáp án:** ORG_GRADLE_PROJECT_internalRepoUsername và ORG_GRADLE_PROJECT_internalRepoPassword.

**Bài 4.** PasswordCredentials có tự thêm dependency vào classpath không?

**Đáp án:** Không. Nó chỉ khai báo cách xác thực repository; dependency phải được khai báo riêng.

**Bài 5.** Pull builder thành công nhưng push image trả 401. Cần xem thuộc tính nào?

**Đáp án:** docker.publishRegistry và quyền publish. builderRegistry chỉ dành cho pull builder/run image.

**Bài 6.** Maven settings có server credentials. Spring Boot plugin có tự dùng nó cho Docker registry không?

**Đáp án:** Không mặc định. Dùng publishRegistry/builderRegistry hoặc Docker credential helper/config.

**Bài 7.** Vì sao docker login -p TOKEN không nên dùng?

**Đáp án:** Token nằm trong command-line arguments. Dùng --password-stdin hoặc credential helper.

**Bài 8.** Gradle đọc System.getenv("TOKEN") eager khi configure task. Rủi ro?

**Đáp án:** Secret có thể lọt vào task/configuration state/cache. Dùng Provider lazy và typed credentials API.

**Bài 9.** GitHub fork PR không nhận secret. Đây có phải lỗi tên biến?

**Đáp án:** Không nhất thiết. GitHub không cấp repository secrets thông thường cho fork PR workflows. PR job nên không cần release credentials.

**Bài 10.** Database password của app chạy Kubernetes nên nằm đâu?

**Đáp án:** Secret manager/Kubernetes Secret và inject lúc runtime. Không ghi vào JAR, Dockerfile hoặc image layer.

## 11. Checklist trước khi merge/release

- [ ] Mỗi credential có mục đích rõ: repository read, artifact publish, builder pull, image publish hay runtime.
- [ ] Maven credentials nằm trong user/CI settings.xml; POM không có password literal.
- [ ] Maven server ID khớp repository/mirror/deployment ID thực tế.
- [ ] Maven environment variables được cấp cho đúng process và không in ra logs.
- [ ] Không coi Maven 3 password encryption là vault.
- [ ] Gradle dùng credentials(PasswordCredentials::class) hoặc typed API phù hợp.
- [ ] Gradle repository name và property identity khớp; CI cấp đúng ORG_GRADLE_PROJECT_...
- [ ] Gradle credentials không nằm trong project gradle.properties được commit.
- [ ] Gradle User Home, Configuration Cache và Daemon được giới hạn quyền truy cập.
- [ ] Spring Boot builderRegistry chỉ có quyền pull cần thiết.
- [ ] Spring Boot publishRegistry chỉ có quyền push repository/tag được phép.
- [ ] Docker credential helper/store được ưu tiên; static Base64 auth được bảo vệ như plaintext.
- [ ] Settings files, Gradle properties, Docker config và caches không bị upload/cache.
- [ ] Không dùng set -x, mvn -X, Gradle --debug hoặc env trong job chứa secrets.
- [ ] Docker login dùng --password-stdin, không truyền token qua command line.
- [ ] Release secrets chỉ được cấp cho trusted branch/tag/environment.
- [ ] OIDC/token ngắn hạn được ưu tiên khi provider hỗ trợ.
- [ ] Runtime secrets được inject khi deploy, không bake vào JAR/image.
- [ ] Có quy trình revoke/rotate/audit khi secret bị lộ.

## 12. Tài liệu chính thức

- Apache Maven — Settings Reference: https://maven.apache.org/settings.html
- Apache Maven — Password Encryption (Maven 3): https://maven.apache.org/guides/mini/guide-encryption.html
- Apache Maven — Password Encryption (Maven 4): https://maven.apache.org/guides/mini/guide-encryption-4.html
- Gradle — Supported Protocols / Handling Credentials: https://docs.gradle.org/current/userguide/supported_repository_protocols.html
- Gradle — Securing the Build Tool: https://docs.gradle.org/current/userguide/securing_build_tool.html
- Gradle — Configuration Cache Requirements: https://docs.gradle.org/current/userguide/configuration_cache_requirements.html
- Gradle — Build Environment Configuration: https://docs.gradle.org/current/userguide/build_environment.html
- Spring Boot 3.5 — Maven Packaging OCI Images: https://docs.spring.io/spring-boot/3.5/maven-plugin/build-image.html
- Spring Boot 3.5 — Gradle Packaging OCI Images: https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging-oci-image.html
- Docker — Login and Password STDIN: https://docs.docker.com/reference/cli/docker/login/
- Docker — Credential Stores: https://docs.docker.com/reference/cli/docker/login/#credential-stores
- GitHub Actions — Using secrets in a workflow: https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
- GitHub Actions — OpenID Connect: https://docs.github.com/en/actions/concepts/security/openid-connect

**Kết luận:** Maven dùng settings.xml với server ID; Gradle dùng typed credentials và Gradle properties; Spring Boot tách credentials pull builder/run images khỏi publish application image. CI nên lấy secrets từ secret store hoặc OIDC, cấp trong phạm vi job tin cậy, tránh command-line/logs/cache/artifacts và giữ application runtime secrets ngoài JAR/container image.