# Lưu artifact rồi bàn giao đúng artifact cho môi trường tiếp theo

Trong một quy trình CI/CD đáng tin cậy, build tạo ra một artifact có định danh rõ ràng; các môi trường tiếp theo nhận và triển khai đúng artifact đó. Không build lại riêng cho staging rồi lại build một lần nữa cho production, vì hai lần build có thể tạo nội dung khác nhau dù cùng commit, cùng version hoặc cùng tên file.

Lab này thực hành một luồng phát hành nhỏ với service Java dùng Gradle. Bạn sẽ build JAR một lần, tạo release bundle gồm JAR, metadata và checksum, lưu bundle theo SHA-256, triển khai cùng bundle lên staging rồi production, xác minh digest ở mỗi chặng và cố ý làm hỏng một bản sao để kiểm tra khả năng phát hiện sai lệch.

Lab dùng thư mục local để mô phỏng artifact store và hai môi trường. Sau khi hoàn thành, bạn sẽ ánh xạ cùng quy trình sang GitHub Actions, GitLab CI và Jenkins. Khi triển khai thật, artifact store và thư mục môi trường mô phỏng sẽ được thay bằng package/container registry, object storage hoặc hệ thống deployment của tổ chức.

## 1. Kết quả cần đạt

Sau lab, bạn có thể:

- Giải thích vì sao build một lần rồi promote cùng artifact qua các môi trường.
- Phân biệt artifact, cache, workspace và release metadata.
- Tạo JAR có version và commit SHA trong manifest.
- Đóng gói artifact cùng metadata và SHA-256 checksum.
- Lưu artifact theo content digest để tránh ghi đè nhầm version.
- Triển khai cùng một bundle lên staging và production.
- Xác minh checksum trước và sau khi bàn giao.
- Phát hiện artifact bị thay đổi hoặc bị thiếu.
- Thiết kế pipeline truyền artifact giữa các job/runner độc lập.
- Ghi lại bằng chứng để truy vết source → build → artifact → deployment.

**Điều kiện hoàn thành:** digest của JAR trong artifact store, staging và production phải giống nhau; ứng dụng chạy được từ JAR đã triển khai; production chỉ được promote sau khi staging validation đạt và có quyết định approval.

## 2. Kịch bản và kiến trúc lab

Bạn đang phát hành service đơn giản tên orders-service. Bản 1.0.0 được build từ một commit cụ thể. Pipeline phải tạo một release bundle duy nhất và chuyển bundle đó qua các bước:

~~~mermaid
flowchart TD
    A[Git commit] --> B[Gradle build + test]
    B --> C[orders-service JAR]
    C --> D[Release bundle]
    D --> E[SHA-256 + metadata]
    E --> F[Artifact store theo digest]
    F --> G[Deploy staging]
    G --> H[Verify digest + smoke test]
    H --> I{Approval}
    I -- Approved --> J[Deploy production]
    I -- Rejected --> K[Stop promotion]
    J --> L[Verify digest + runtime]
    L --> M[Release record]
~~~

Cấu trúc thư mục sau khi hoàn thành:

~~~text
orders-service/
├── build.gradle
├── settings.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
├── src/
│   ├── main/java/com/example/orders/Main.java
│   └── test/java/com/example/orders/MainTest.java
├── scripts/
│   ├── package-release.sh
│   └── deploy-local.sh
├── artifact-store/
│   └── orders-service/
│       └── 1.0.0/
│           └── sha256-<digest>/
│               ├── orders-service-1.0.0.jar
│               ├── release-metadata.json
│               ├── artifact-digest.txt
│               └── SHA256SUMS
└── environments/
    ├── staging/
    │   ├── current-digest
    │   └── releases/sha256-<digest>/
    └── production/
        ├── current-digest
        └── releases/sha256-<digest>/
~~~

Artifact được lưu trong thư mục mang digest của nội dung JAR. File current-digest là con trỏ deployment hiện tại của môi trường mô phỏng; nó có thể thay đổi khi promote release mới. Thư mục release theo digest được coi là write-once trong lab. Filesystem local chưa tự cưỡng chế immutability; hệ thống thật cần policy registry/object storage, quyền ghi hạn chế và cơ chế tạo object có điều kiện để ngăn ghi đè.

## 3. Chuẩn bị môi trường

Yêu cầu:

- JDK 21.
- Gradle 8.10.2 hoặc Gradle Wrapper tương thích.
- Git.
- Bash trên Linux hoặc WSL, cùng GNU coreutils để có lệnh sha256sum. Trên macOS cần cài GNU coreutils và bảo đảm lệnh sha256sum có trong PATH.
- Có thể truy cập Gradle Plugin Portal/Maven repository ở lần build đầu để tải wrapper và JUnit.

Kiểm tra:

~~~bash
java -version
gradle --version
git --version
sha256sum --version
~~~

Tạo project:

~~~bash
mkdir orders-service
cd orders-service

mkdir -p src/main/java/com/example/orders
mkdir -p src/test/java/com/example/orders
mkdir -p scripts

gradle wrapper --gradle-version 8.10.2
~~~

Nếu bạn đã có một service Java dùng Gradle, có thể dùng project đó thay cho skeleton bên dưới; chỉ cần điều chỉnh đường dẫn JAR và tên file trong các bước tiếp theo.

## 4. Tạo ứng dụng Java nhỏ

Tạo file src/main/java/com/example/orders/Main.java:

~~~java
package com.example.orders;

public final class Main {
    private Main() {
    }

    public static String message() {
        return "orders-service ready";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Tạo file src/test/java/com/example/orders/MainTest.java:

~~~java
package com.example.orders;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class MainTest {
    @Test
    void returnsReadyMessage() {
        assertEquals("orders-service ready", Main.message());
    }
}
~~~

Test nhỏ này giúp lab có một quality gate thực tế. Khi test thất bại, pipeline phải dừng trước khi tạo và publish release bundle.

## 5. Khai báo Gradle build

Tạo settings.gradle:

~~~groovy
rootProject.name = 'orders-service'
~~~

Tạo build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'com.example'
version = providers.gradleProperty('releaseVersion').getOrElse('1.0.0')

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

application {
    mainClass = 'com.example.orders.Main'
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}

tasks.test {
    useJUnitPlatform()
}

tasks.named('jar') {
    manifest {
        attributes(
            'Main-Class': application.mainClass.get(),
            'Implementation-Title': project.name,
            'Implementation-Version': project.version.toString(),
            'Build-Commit': System.getenv('GIT_COMMIT') ?: 'local'
        )
    }
}
~~~

Manifest giúp nhận biết JAR được tạo từ version và commit nào. Đây là metadata hữu ích để truy vết, nhưng không thay thế artifact digest: cùng version/commit vẫn có thể tạo ra binary khác nếu toolchain, dependency hoặc build input khác nhau.

Nếu đây là project mới, hãy tạo commit đầu tiên trước khi đóng gói để script có source revision cụ thể:

~~~bash
git init
git add build.gradle settings.gradle gradlew gradlew.bat gradle src
git commit -m "Create orders service starter"
~~~

Nếu Git chưa có user identity, cấu hình user.name và user.email theo tài khoản của bạn trước khi commit. Với repository đã có sẵn, bảo đảm HEAD đang trỏ đến commit muốn phát hành.

Chạy test và build thử:

~~~bash
./gradlew --no-daemon clean test jar -PreleaseVersion=1.0.0
java -jar build/libs/orders-service-1.0.0.jar
~~~

Kết quả mong đợi:

~~~text
orders-service ready
~~~

Nếu test hoặc build thất bại, dừng tại đây và sửa lỗi. Không tạo release bundle từ output của một build chưa đạt quality gate.

## 6. Build một lần và tạo release bundle

Tạo scripts/package-release.sh:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

VERSION="$1"
SERVICE="orders-service"
JAR_NAME="$SERVICE-$VERSION.jar"
GIT_COMMIT="$(git rev-parse HEAD)"
export GIT_COMMIT

./gradlew --no-daemon clean test jar -PreleaseVersion="$VERSION" >&2

JAR_PATH="build/libs/$JAR_NAME"
test -f "$JAR_PATH"

JAR_DIGEST="$(sha256sum "$JAR_PATH" | awk '{print $1}')"
STORE_PARENT="$PWD/artifact-store/$SERVICE/$VERSION"
ARTIFACT_DIR="$STORE_PARENT/sha256-$JAR_DIGEST"

mkdir -p "$STORE_PARENT"
TEMP_DIR="$(mktemp -d "$STORE_PARENT/.tmp.XXXXXX")"

cp "$JAR_PATH" "$TEMP_DIR/$JAR_NAME"

cat > "$TEMP_DIR/release-metadata.json" <<EOF
{
  "service": "$SERVICE",
  "version": "$VERSION",
  "sourceCommit": "$GIT_COMMIT",
  "artifactFile": "$JAR_NAME",
  "artifactSha256": "$JAR_DIGEST",
  "builtAtUtc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

printf '%s\n' "$JAR_DIGEST" > "$TEMP_DIR/artifact-digest.txt"

(
    cd "$TEMP_DIR"
    sha256sum "$JAR_NAME" release-metadata.json artifact-digest.txt > SHA256SUMS
)

if [ -d "$ARTIFACT_DIR" ]; then
    (
        cd "$ARTIFACT_DIR"
        sha256sum -c SHA256SUMS
    )
    rm -r "$TEMP_DIR"
else
    mv "$TEMP_DIR" "$ARTIFACT_DIR"
fi

printf '%s\n' "$ARTIFACT_DIR"
~~~

Cấp quyền chạy script:

~~~bash
chmod +x scripts/package-release.sh
~~~

Chạy build release:

~~~bash
ARTIFACT_DIR="$(./scripts/package-release.sh 1.0.0)"
printf 'Artifact bundle: %s\n' "$ARTIFACT_DIR"
~~~

Tiếp tục các bước staging/production trong cùng Bash session để giữ biến ARTIFACT_DIR. Nếu mở terminal mới, gán lại ARTIFACT_DIR bằng đường dẫn bundle đã được script in ra.

Script thực hiện các việc sau:

1. Lấy commit SHA hiện tại từ Git.
2. Chạy clean test jar một lần.
3. Xác định JAR đầu ra và tính SHA-256.
4. Tạo metadata gồm service, version, commit, tên file, digest và thời điểm build.
5. Tạo SHA256SUMS cho JAR, metadata và file digest.
6. Lưu bundle trong artifact store theo version và digest.
7. Nếu bundle cùng digest đã tồn tại, xác minh bundle hiện có thay vì ghi đè.
8. Trả về đường dẫn bundle để bước deploy dùng chính xác artifact đó.

Trong lab, artifact store là thư mục local và giả định chỉ có một publisher chạy tại một thời điểm. Script minh họa chưa triển khai khóa phân tán hoặc thao tác create-if-absent an toàn khi nhiều pipeline cạnh tranh. Trong hệ thống thật, hãy dùng package registry/OCI registry hoặc object storage có immutable version, conditional create, retention và quyền ghi giới hạn.

## 7. Kiểm tra nội dung và nguồn gốc artifact

Liệt kê bundle:

~~~bash
find "$ARTIFACT_DIR" -maxdepth 1 -type f -print
cat "$ARTIFACT_DIR/release-metadata.json"
cat "$ARTIFACT_DIR/artifact-digest.txt"
~~~

Xác minh checksum:

~~~bash
(
    cd "$ARTIFACT_DIR"
    sha256sum -c SHA256SUMS
)
~~~

Kết quả mong đợi:

~~~text
orders-service-1.0.0.jar: OK
release-metadata.json: OK
artifact-digest.txt: OK
~~~

Kiểm tra manifest bên trong JAR:

~~~bash
unzip -p "$ARTIFACT_DIR/orders-service-1.0.0.jar" META-INF/MANIFEST.MF
~~~

Bạn cần thấy Implementation-Version là 1.0.0 và Build-Commit khớp commit đã ghi trong metadata.

**Lưu ý về bảo mật:** SHA256SUMS phát hiện hỏng hoặc thay đổi ngoài ý muốn khi file checksum được giữ nguyên. Nếu một kẻ có quyền thay cả JAR lẫn SHA256SUMS, checksum đơn thuần không chứng minh nguồn gốc. Production cần artifact store được kiểm soát quyền ghi, digest được ghi trong release record và chữ ký/provenance được xác minh theo policy, ví dụ Sigstore/cosign hoặc hệ thống ký artifact của tổ chức.

## 8. Viết script triển khai môi trường local

Tạo scripts/deploy-local.sh:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT="$1"
ARTIFACT_DIR="$2"

case "$ENVIRONMENT" in
    staging|production)
        ;;
    *)
        echo "Environment must be staging or production" >&2
        exit 2
        ;;
esac

test -d "$ARTIFACT_DIR"
test -f "$ARTIFACT_DIR/SHA256SUMS"
test -f "$ARTIFACT_DIR/artifact-digest.txt"

(
    cd "$ARTIFACT_DIR"
    sha256sum -c SHA256SUMS
)

EXPECTED_DIGEST="$(cat "$ARTIFACT_DIR/artifact-digest.txt")"
JAR_PATH="$(find "$ARTIFACT_DIR" -maxdepth 1 -type f -name 'orders-service-*.jar' -print -quit)"
test -n "$JAR_PATH"
JAR_NAME="$(basename "$JAR_PATH")"

ACTUAL_DIGEST="$(sha256sum "$ARTIFACT_DIR/$JAR_NAME" | awk '{print $1}')"
test "$ACTUAL_DIGEST" = "$EXPECTED_DIGEST"

TARGET_PARENT="$PWD/environments/$ENVIRONMENT/releases"
TARGET_DIR="$TARGET_PARENT/sha256-$EXPECTED_DIGEST"

mkdir -p "$TARGET_PARENT"

if [ -d "$TARGET_DIR" ]; then
    (
        cd "$TARGET_DIR"
        sha256sum -c SHA256SUMS
    )
else
    mkdir "$TARGET_DIR"
    cp -a "$ARTIFACT_DIR/." "$TARGET_DIR/"
fi

(
    cd "$TARGET_DIR"
    sha256sum -c SHA256SUMS
)

DEPLOYED_DIGEST="$(sha256sum "$TARGET_DIR/$JAR_NAME" | awk '{print $1}')"
test "$DEPLOYED_DIGEST" = "$EXPECTED_DIGEST"

OUTPUT="$(java -jar "$TARGET_DIR/$JAR_NAME")"
test "$OUTPUT" = "orders-service ready"

mkdir -p "$PWD/environments/$ENVIRONMENT"
printf '%s\n' "$DEPLOYED_DIGEST" > "$PWD/environments/$ENVIRONMENT/current-digest"

printf 'Environment: %s\n' "$ENVIRONMENT"
printf 'Artifact: %s\n' "$JAR_NAME"
printf 'SHA-256: %s\n' "$DEPLOYED_DIGEST"
printf 'Smoke test: %s\n' "$OUTPUT"
~~~

Cấp quyền chạy:

~~~bash
chmod +x scripts/deploy-local.sh
~~~

Script chỉ chấp nhận staging hoặc production. Trước khi copy, nó xác minh bundle; sau khi copy, nó xác minh lại checksum và digest của JAR. Nó chạy smoke test từ file JAR trong thư mục release trước; chỉ khi smoke test đạt mới cập nhật current-digest.

Trong ví dụ này, thư mục environments mô phỏng filesystem của môi trường. Production thật sẽ thay phần copy file bằng adapter triển khai như SSH/rsync, Kubernetes, VM deployment agent hoặc nền tảng release; phần xác minh digest vẫn phải được giữ.

## 9. Bàn giao artifact cho staging

Triển khai bundle đã lưu:

~~~bash
./scripts/deploy-local.sh staging "$ARTIFACT_DIR"
~~~

Xác minh staging đang trỏ đến digest mong đợi:

~~~bash
EXPECTED_DIGEST="$(cat "$ARTIFACT_DIR/artifact-digest.txt")"
STAGING_DIGEST="$(cat environments/staging/current-digest)"

test "$STAGING_DIGEST" = "$EXPECTED_DIGEST"
(
    cd "environments/staging/releases/sha256-$EXPECTED_DIGEST"
    sha256sum -c SHA256SUMS
)
~~~

Kiểm tra ứng dụng từ đúng file đã bàn giao:

~~~bash
java -jar "environments/staging/releases/sha256-$EXPECTED_DIGEST/orders-service-1.0.0.jar"
~~~

Kết quả mong đợi là orders-service ready. Ghi lại staging digest, deployment time, smoke-test result và artifact reference. Nếu checksum hoặc smoke test thất bại, không promote sang production.

## 10. Approval rồi promote đúng bundle sang production

Chỉ sau khi staging validation đạt, mới thực hiện bước production. Lab mô phỏng approval bằng xác nhận thủ công:

~~~bash
read -r -p "Staging passed. Type YES to approve production: " APPROVAL
test "$APPROVAL" = "YES"
~~~

Deploy cùng bundle:

~~~bash
./scripts/deploy-local.sh production "$ARTIFACT_DIR"
~~~

Xác minh hai môi trường đang dùng cùng digest:

~~~bash
EXPECTED_DIGEST="$(cat "$ARTIFACT_DIR/artifact-digest.txt")"
STAGING_DIGEST="$(cat environments/staging/current-digest)"
PRODUCTION_DIGEST="$(cat environments/production/current-digest)"

test "$STAGING_DIGEST" = "$EXPECTED_DIGEST"
test "$PRODUCTION_DIGEST" = "$EXPECTED_DIGEST"
test "$STAGING_DIGEST" = "$PRODUCTION_DIGEST"

printf 'Staging:    %s\n' "$STAGING_DIGEST"
printf 'Production: %s\n' "$PRODUCTION_DIGEST"
~~~

Kết quả phải có cùng một SHA-256 ở cả ba vị trí: artifact store, staging và production.

Không chạy lại Gradle trước khi deploy production. Nếu build lại, dù version và commit giống nhau, output vẫn có thể khác do toolchain, dependency, timestamp hoặc cấu hình. Nếu muốn phát hành một bản sửa mới, tạo version/release candidate mới, build và kiểm tra lại từ đầu.

## 11. Thử nghiệm phát hiện artifact bị thay đổi

Để chứng minh checksum thực sự được kiểm tra, tạo một bản copy riêng và sửa một byte trong JAR. Không sửa artifact gốc trong artifact store.

~~~bash
TAMPERED_DIR="$(mktemp -d)"
cp -a "$ARTIFACT_DIR/." "$TAMPERED_DIR/"
printf 'corruption' >> "$TAMPERED_DIR/orders-service-1.0.0.jar"

if (
    cd "$TAMPERED_DIR"
    sha256sum -c SHA256SUMS
); then
    echo "ERROR: tampered artifact was not detected"
    exit 1
else
    echo "PASS: checksum detected artifact modification"
fi
~~~

Kết quả mong đợi là checksum của JAR báo FAILED và script xác nhận PASS: checksum detected artifact modification.

Thử tiếp deploy bản đã bị sửa:

~~~bash
if ./scripts/deploy-local.sh staging "$TAMPERED_DIR"; then
    echo "ERROR: corrupted artifact was deployed"
    exit 1
else
    echo "PASS: deployment rejected corrupted artifact"
fi
~~~

Deploy phải dừng trước khi cập nhật current-digest. Nếu script vẫn triển khai, kiểm tra lại thứ tự xác minh và điều kiện dừng.

## 12. Tình huống lỗi và cách xử lý

| Tình huống | Dấu hiệu | Hành động |
|---|---|---|
| Build/test thất bại | Gradle trả non-zero | Không tạo hoặc publish bundle |
| JAR không tồn tại | Không có file theo version mong đợi | Kiểm tra Gradle output và version |
| Bundle đã tồn tại cùng digest | Artifact path đã có | Xác minh checksum và tái sử dụng |
| Cùng version nhưng digest khác | Có artifact khác nội dung dưới version đó | Dừng, điều tra; không ghi đè |
| Checksum thất bại trước deploy | File thiếu hoặc bị sửa | Loại bundle khỏi promotion, kiểm tra nguồn và tải lại từ nguồn tin cậy |
| Copy sang staging bị gián đoạn | Target directory thiếu file | Không đánh dấu deploy thành công; xử lý bản copy dở dang theo runbook |
| Staging smoke test thất bại | Ứng dụng không đáp ứng | Dừng promotion; điều tra hoặc phát hành candidate mới |
| Production approval bị từ chối | Không có quyết định promote | Giữ artifact ở trạng thái đã kiểm thử; không deploy |
| Production digest khác staging | Artifact handoff sai | Dừng release, xác minh deployment và rollback theo quy trình |
| Deploy command timeout | Không rõ môi trường đã nhận artifact chưa | Query deployment state và reconcile trước khi retry |

Nếu target directory tồn tại nhưng thiếu file hoặc checksum không hợp lệ, script dừng. Trong hệ thống thật, nên dùng upload vào staging location, xác minh đầy đủ rồi atomic promote/activate để tránh người dùng nhìn thấy release copy chưa hoàn chỉnh.

## 13. Tích hợp vào GitHub Actions

Sau khi lab local hoạt động, có thể đưa luồng artifact handoff vào workflow. Job build tạo bundle và upload một lần; job staging và production tải cùng artifact từ workflow run đó.

Ví dụ workflow .github/workflows/release.yml:

~~~yaml
name: Build and promote artifact

on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Build and test once
        run: |
          GIT_COMMIT="$GITHUB_SHA" ./gradlew --no-daemon clean test jar -PreleaseVersion=1.0.0

      - name: Create release bundle
        run: |
          mkdir -p dist/release
          cp build/libs/orders-service-1.0.0.jar dist/release/
          cd dist/release
          DIGEST="$(sha256sum orders-service-1.0.0.jar | awk '{print $1}')"
          printf '%s\n' "$DIGEST" > artifact-digest.txt
          printf '{"service":"orders-service","version":"1.0.0","commit":"%s","artifactSha256":"%s"}\n' "$GITHUB_SHA" "$DIGEST" > release-metadata.json
          sha256sum orders-service-1.0.0.jar artifact-digest.txt release-metadata.json > SHA256SUMS

      - name: Upload immutable workflow artifact
        uses: actions/upload-artifact@v4
        with:
          name: orders-release-bundle
          path: dist/release/
          if-no-files-found: error
          retention-days: 14

  deploy_staging:
    needs: build
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4

      - uses: actions/download-artifact@v4
        with:
          name: orders-release-bundle
          path: dist/release/

      - name: Verify artifact
        run: |
          cd dist/release
          sha256sum -c SHA256SUMS

      - name: Deploy staging
        run: ./scripts/deploy.sh staging dist/release

      - name: Verify staging
        run: ./scripts/verify-environment.sh staging dist/release

  deploy_production:
    needs: deploy_staging
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - uses: actions/download-artifact@v4
        with:
          name: orders-release-bundle
          path: dist/release/

      - name: Verify artifact again
        run: |
          cd dist/release
          sha256sum -c SHA256SUMS

      - name: Deploy production
        run: ./scripts/deploy.sh production dist/release

      - name: Verify production
        run: ./scripts/verify-environment.sh production dist/release
~~~

Workflow này là skeleton. Bạn cần cấu hình environment protection cho production trong repository settings để yêu cầu reviewer theo chính sách. Các script deploy/verify phải triển khai vào môi trường thật và xác minh digest ở runtime. Trong production job, tải lại artifact cùng tên từ chính workflow run; không checkout source rồi build lại.

Action trong ví dụ dùng tag version để dễ đọc. Với policy supply-chain nghiêm ngặt, pin action theo full commit SHA đã được review. Artifact của workflow có retention; nếu cần promote sau nhiều ngày hoặc qua workflow khác, hãy publish bundle vào package/OCI registry hoặc object storage bất biến, sau đó truyền artifact digest/reference thay vì dựa vào workflow artifact tạm thời.

## 14. Ánh xạ sang GitLab CI và Jenkins

Các nền tảng khác có cơ chế handoff tương đương về mục tiêu, nhưng semantics và phạm vi lưu trữ khác nhau.

| Nền tảng | Cơ chế handoff trong pipeline | Khi cần lưu lâu dài |
|---|---|---|
| GitHub Actions | Upload/download workflow artifact | Package/container registry hoặc release storage |
| GitLab CI | Job artifacts kết hợp needs/dependencies | Package/container registry hoặc generic package registry |
| Jenkins | stash/unstash trong cùng Pipeline; archiveArtifacts | Artifact manager, Nexus, Artifactory hoặc OCI registry |

### 14.1. GitLab CI

Job build có thể publish JAR thành job artifact; job deploy khai báo needs để tải artifact từ đúng job:

~~~yaml
stages:
  - build
  - staging
  - production

build_release:
  stage: build
  image: gradle:8.10-jdk21
  script:
    - |
      GIT_COMMIT="$CI_COMMIT_SHA" ./gradlew --no-daemon clean test jar -PreleaseVersion=1.0.0
      mkdir -p dist/release
      cp build/libs/orders-service-1.0.0.jar dist/release/
      cd dist/release
      DIGEST="$(sha256sum orders-service-1.0.0.jar | awk '{print $1}')"
      printf '%s\n' "$DIGEST" > artifact-digest.txt
      printf '{"service":"orders-service","version":"1.0.0","commit":"%s","artifactSha256":"%s"}\n' "$CI_COMMIT_SHA" "$DIGEST" > release-metadata.json
      sha256sum orders-service-1.0.0.jar artifact-digest.txt release-metadata.json > SHA256SUMS
      cd "$CI_PROJECT_DIR"
  artifacts:
    name: orders-release-bundle
    paths:
      - dist/release/
    expire_in: 14 days

deploy_staging:
  stage: staging
  needs:
    - job: build_release
      artifacts: true
  environment:
    name: staging
  script:
    - cd dist/release
    - sha256sum -c SHA256SUMS
    - cd ../..
    - ./scripts/deploy.sh staging dist/release

deploy_production:
  stage: production
  needs:
    - job: build_release
      artifacts: true
    - job: deploy_staging
      artifacts: false
  environment:
    name: production
  when: manual
  script:
    - cd dist/release
    - sha256sum -c SHA256SUMS
    - cd ../..
    - ./scripts/deploy.sh production dist/release
~~~

Ví dụ minh họa luồng job artifacts. Cần cấu hình rules và protected environment/approval theo GitLab instance/tier. Artifact expiration phải dài hơn thời gian promotion dự kiến; nếu release cần giữ lâu dài, publish vào registry có retention policy.

### 14.2. Jenkins

Trong cùng một Jenkins Pipeline, stash/unstash có thể chuyển bundle giữa agent hoặc stage. Khi cần giữ artifact qua nhiều build hoặc nhiều pipeline, dùng artifact repository.

~~~groovy
pipeline {
    agent any

    stages {
        stage('Build once') {
            steps {
                checkout scm
                sh '''
                    GIT_COMMIT="$(git rev-parse HEAD)" ./gradlew --no-daemon clean test jar -PreleaseVersion=1.0.0
                    mkdir -p dist/release
                    cp build/libs/orders-service-1.0.0.jar dist/release/
                    cd dist/release
                    DIGEST="$(sha256sum orders-service-1.0.0.jar | awk '{print $1}')"
                    printf '%s\n' "$DIGEST" > artifact-digest.txt
                    printf '{"service":"orders-service","version":"1.0.0","commit":"%s","artifactSha256":"%s"}\n' "$(git -C ../.. rev-parse HEAD)" "$DIGEST" > release-metadata.json
                    sha256sum orders-service-1.0.0.jar artifact-digest.txt release-metadata.json > SHA256SUMS
                '''
                stash name: 'orders-release-bundle',
                      includes: 'dist/release/**'
            }
        }

        stage('Deploy staging') {
            steps {
                unstash 'orders-release-bundle'
                sh 'sha256sum -c dist/release/SHA256SUMS'
                sh './scripts/deploy.sh staging dist/release'
            }
        }

        stage('Approve production') {
            steps {
                input message: 'Staging passed. Approve production promotion?'
            }
        }

        stage('Deploy production') {
            steps {
                unstash 'orders-release-bundle'
                sh 'sha256sum -c dist/release/SHA256SUMS'
                sh './scripts/deploy.sh production dist/release'
            }
        }
    }
}
~~~

Stash phù hợp cho handoff trong cùng Pipeline và thường không thay thế artifact repository có retention/provenance lâu dài. Nếu Jenkins có nhiều controller hoặc pipeline tách biệt, hãy dùng registry/artifact manager và tham chiếu bằng digest. Production approval cần RBAC và approver policy; input step một mình không xác định ai có quyền phê duyệt.

## 15. Phân biệt artifact, cache và workspace

| Thành phần | Mục đích | Có dùng làm nguồn deploy không? |
|---|---|---|
| Workspace | File tạm của job/runner | Không mặc định; có thể bị xóa hoặc thay đổi |
| Cache | Tăng tốc bằng cách tái sử dụng dữ liệu có thể tái tạo | Không |
| Job/workflow artifact | Bàn giao file giữa job hoặc giữ output trong thời hạn | Có thể dùng trong flow ngắn nếu integrity/retention phù hợp |
| Package/OCI registry | Lưu artifact có version/digest và policy truy cập | Có, thường phù hợp cho promotion |
| Release record | Liên kết source, artifact, approval và deployment | Là bằng chứng truy vết, không nhất thiết chứa binary |

Không dùng cache để chuyển JAR cần deploy. Cache có thể hết hạn, eviction, restore sai key hoặc bị ghi bởi workflow khác. Artifact phát hành cần định danh, kiểm tra integrity, quyền ghi và retention riêng.

## 16. Release record và khả năng truy vết

Mỗi lần promotion nên tạo hoặc cập nhật release record gồm:

- Service và version.
- Source repository, commit SHA và branch/ref.
- Pipeline run/build ID.
- Artifact name, coordinates và SHA-256 digest.
- Metadata/provenance/signature reference.
- Environment và deployment ID.
- Thời điểm staging/production.
- Approval identity và decision.
- Checksum, smoke test và post-deploy verification result.
- Rollback reference nếu release phải quay lui.

Ví dụ record:

~~~json
{
  "service": "orders-service",
  "version": "1.0.0",
  "commit": "a1b2c3d4",
  "artifactDigest": "sha256:abc123...",
  "buildRun": "ci-1842",
  "deployments": {
    "staging": {
      "status": "verified",
      "digest": "sha256:abc123..."
    },
    "production": {
      "status": "verified",
      "digest": "sha256:abc123..."
    }
  }
}
~~~

Record chỉ hợp lệ khi digest trong deployment evidence được lấy từ môi trường đang chạy hoặc artifact đã được hệ thống đích xác nhận, không chỉ copy từ metadata do build job tự khai báo.

## 17. Bài tập mở rộng

Sau khi hoàn thành luồng cơ bản, thực hiện các bài sau:

1. Build version 1.0.1 từ commit mới và so sánh digest với 1.0.0.
2. Thử chạy lại package script cho cùng version và cùng nội dung; xác minh bundle cùng digest được tái sử dụng.
3. Thử thay source nhưng giữ nguyên version; xác minh digest khác và giải thích vì sao không được ghi đè artifact cũ.
4. Xóa một file trong bản copy staging rồi chạy checksum; xác minh deploy/verification dừng.
5. Tạo một bundle mới nhưng cố tình đưa nhầm bundle 1.0.0 vào production promotion của release 1.0.1; thiết kế kiểm tra expected version/commit/digest để từ chối.
6. Thêm SBOM và provenance reference vào release metadata.
7. Thêm chữ ký artifact và xác minh chữ ký trước khi deploy.
8. Thay local artifact store bằng package registry hoặc object storage; chỉ truyền digest/reference giữa các pipeline.
9. Cấu hình production approval và ghi lại approver trong release record.
10. Diễn tập rollback bằng cách chuyển current-digest về release digest trước đó sau khi xác minh artifact cũ còn tồn tại và tương thích.

## 18. Tiêu chí nghiệm thu và bằng chứng cần lưu

| Tiêu chí | Bằng chứng |
|---|---|
| Build/test chỉ chạy một lần cho release candidate | Pipeline log/build run ID |
| Bundle có JAR, metadata và SHA256SUMS | Danh sách file trong artifact store |
| Artifact được lưu theo digest | Đường dẫn content-addressed |
| Checksum hợp lệ trước deploy | Kết quả sha256sum -c |
| Staging chạy đúng artifact | Runtime output và staging current-digest |
| Production chạy đúng artifact đã test | Production current-digest khớp staging |
| Artifact bị sửa bị từ chối | Log tamper test thất bại checksum |
| Production có approval | Approval/deployment record |
| Có thể truy về source | Commit SHA trong metadata và release record |

Checklist hoàn thành:

- [ ] Gradle test và build đạt.
- [ ] JAR có version và commit trong manifest.
- [ ] Release bundle chứa JAR, metadata, artifact digest và SHA256SUMS.
- [ ] Artifact store không ghi đè nội dung đã phát hành.
- [ ] Checksum được xác minh trước khi deploy.
- [ ] Staging deploy từ artifact store, không build lại.
- [ ] Smoke test staging đạt.
- [ ] Production được approval trước khi promote.
- [ ] Production deploy từ cùng artifact bundle/digest.
- [ ] Digest staging và production trùng nhau.
- [ ] Tamper test chứng minh artifact sai bị từ chối.
- [ ] Release record liên kết commit, digest, approval và deployment.

## 19. Câu hỏi tự kiểm tra

**1. Vì sao không build lại artifact ở production?**

Vì build lần hai có thể tạo nội dung khác do dependency, toolchain, timestamp hoặc cấu hình thay đổi. Promote cùng artifact đã test giúp bảo đảm production chạy đúng binary đã được xác minh.

**2. SHA-256 checksum chứng minh điều gì?**

Nó giúp phát hiện nội dung khác với nội dung được checksum mô tả. Nếu cả artifact và checksum cùng bị thay thế, checksum không chứng minh được nguồn gốc; cần chữ ký, provenance và kiểm soát quyền ghi.

**3. Vì sao không dùng cache làm artifact handoff?**

Cache có thể hết hạn, bị eviction, restore sai key hoặc đến từ nguồn không tin cậy. Artifact phát hành cần version/digest, retention và release record rõ ràng.

**4. Vì sao staging và production phải có cùng digest?**

Để chứng minh hai môi trường đang chạy cùng nội dung đã được kiểm tra. Nếu digest khác, cần dừng promotion và xác minh artifact thực tế.

**5. Khi upload artifact thành công nhưng deploy staging thất bại, có cần build lại không?**

Không nhất thiết. Trước hết điều tra deployment, xác minh bundle còn nguyên và tiếp tục từ artifact đã lưu nếu nó vẫn hợp lệ. Chỉ tạo artifact mới khi source hoặc build inputs cần thay đổi.

Lab hoàn tất khi một artifact có thể đi từ build đến staging và production mà không bị build lại, mỗi chặng đều xác minh cùng digest, có approval trước production và có bằng chứng truy vết đầy đủ. Đây là nền tảng để mở rộng sang registry promotion, ký artifact, SBOM, provenance và release automation trong môi trường thực tế.
