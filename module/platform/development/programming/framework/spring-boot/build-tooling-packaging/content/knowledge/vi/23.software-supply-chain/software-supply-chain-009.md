# Lưu chứng cứ nguồn gốc bản dựng và liên kết chúng với artifact đã phát hành

## 1. Vì sao một file JAR cần có chứng cứ nguồn gốc?

Một nhóm phát triển có thể build ứng dụng Spring Boot thành công, upload file JAR lên trang release và triển khai nó lên production. Nhưng vài tuần sau, đội vận hành nhận được một file có cùng tên và version từ một nguồn khác. Họ cần trả lời:

- File này được tạo từ repository nào và commit nào?
- Workflow, builder và toolchain nào đã tạo nó?
- Dependencies và đầu vào nào đã được sử dụng?
- Ai hoặc hệ thống nào đã xác nhận thông tin đó?
- File tải về có đúng là artifact đã được kiểm thử/phát hành không?
- Image đang chạy trong Kubernetes có đúng image mà release team đã duyệt không?

Chỉ ghi tên file, version hoặc Git commit vào release notes là chưa đủ. Tên file và tag có thể bị thay thế; một người có thể sửa metadata hoặc upload một binary khác với cùng tên.

Cách làm chắc chắn hơn là tạo **build provenance attestation**: một bản khai có cấu trúc mô tả artifact được tạo ra như thế nào, gắn với **digest mật mã của chính artifact**, rồi được ký bởi một danh tính builder/workflow có thể xác minh. Khi phát hành, ta giữ liên kết giữa source commit, lần chạy CI, attestation và file/image đã phát hành.

Bài học thuộc chủ đề **Chuỗi cung ứng**. Chúng ta sẽ làm việc với SLSA provenance, in-toto Statement, DSSE, OCI digest, SBOM CycloneDX, GitHub Artifact Attestations, Sigstore/Cosign và BuildKit. Ví dụ chính dùng Maven + Java 17 + Spring Boot, sau đó mở rộng sang container image.

## 2. Phân biệt bốn loại bằng chứng

Các thuật ngữ này thường xuất hiện cùng nhau nhưng trả lời những câu hỏi khác nhau.

| Bằng chứng | Câu hỏi được trả lời | Nội dung chính |
| --- | --- | --- |
| **Checksum / digest** | Đây có phải đúng những bytes đã được ghi nhận không? | SHA-256 của JAR, image manifest hoặc file |
| **Build provenance** | Artifact được tạo từ đâu, bởi builder nào, bằng quy trình nào? | Source, builder, build type, inputs, invocation, output subject |
| **SBOM** | Artifact chứa những thành phần phần mềm nào? | Dependencies, versions, package identifiers, hashes, licenses tùy công cụ |
| **Signature / attestation envelope** | Ai ký bản khai và chữ ký có hợp lệ không? | Chữ ký, certificate/identity, timestamp/transparency proof |

Một file SHA-256 sidecar như **app.jar.sha256** giúp phát hiện file thay đổi nếu người kiểm tra có một digest đáng tin cậy. Nhưng checksum một mình không nói ai build file hoặc từ source nào.

SBOM mô tả thành phần; nó không tự chứng minh ứng dụng đã được build từ commit đã duyệt. Provenance mô tả quá trình; nó không tự liệt kê đầy đủ mọi package trong runtime image nếu build platform không ghi nhận những thành phần đó.

Chữ ký chứng minh một danh tính đã ký nội dung được xác định. Nó không tự chứng minh mọi claim bên trong là đúng. Ta phải kiểm tra **chữ ký, danh tính, subject digest, predicate type và chính sách build**.

## 3. Chuỗi liên kết từ source đến release

Mục tiêu là tạo một chuỗi có thể truy vết:

~~~text
Git repository + protected tag/commit
                |
                v
CI workflow + builder identity
                |
                v
Build inputs / toolchain / dependencies
                |
                v
Maven package + tests + SBOM
                |
                v
Artifact bytes -> SHA-256 digest
                |
                v
Signed in-toto / SLSA provenance attestation
                |
                v
Release asset or OCI registry image
                |
                v
Release record links artifact digest + attestation
                |
                v
Consumer verifies before install/deploy
~~~

Có hai danh tính cần phân biệt:

- **Source identity**: repository, branch/tag và commit đã cung cấp source.
- **Builder identity**: workflow/service thực sự chạy build và ký provenance.

Một commit có thể được build bởi nhiều workflows khác nhau. Một workflow có thể chạy trên các commits khác nhau. Vì vậy không chỉ lưu một Git SHA; cần liên kết source identity với builder/workflow identity và output digest trong cùng provenance.

### 3.1. Các giá trị cần liên kết

| Thành phần | Ví dụ | Mục đích |
| --- | --- | --- |
| Repository | github.com/acme/catalog-service | Nơi lưu source |
| Source ref | refs/tags/v1.0.0 | Nhãn release |
| Source commit | 40 ký tự Git SHA | Xác định chính xác source tree |
| Workflow | .github/workflows/release.yml | Xác định quy trình build |
| Workflow run | run ID + attempt | Xác định một lần thực thi |
| Builder | GitHub-hosted runner / trusted builder | Xác định nền tảng build |
| Toolchain | Java 17, Maven Wrapper, plugin versions | Giải thích môi trường build |
| Dependencies | groupId:artifactId:version + digest khi có | Ghi nhận đầu vào |
| Artifact subject | target/app.jar + sha256 digest | Gắn provenance vào file thật |
| Release reference | release URL / registry digest | Nơi consumer lấy artifact |

**Source commit SHA không phải artifact digest.** Commit hash xác định Git object; SHA-256 của JAR xác định bytes của file được phát hành. Hai giá trị có vai trò riêng.

## 4. Digest: định danh không phụ thuộc tên file

### 4.1. Vì sao tên file và tag không đủ?

Hai file đều có thể mang tên:

~~~text
catalog-service-1.0.0.jar
~~~

nhưng bytes bên trong khác nhau. Tương tự, một Docker tag như:

~~~text
registry.example.com/acme/catalog-service:1.0.0
~~~

là một tham chiếu có thể được cập nhật để trỏ tới image khác. Tag hữu ích cho con người, nhưng không phải định danh bất biến của nội dung.

Một digest dùng hash mật mã để định danh nội dung. Ví dụ:

~~~text
sha256:4a1f... (64 ký tự hex)
~~~

Trong ví dụ thực tế, phải có đủ 64 ký tự hex; phần rút gọn ở đây chỉ minh họa định dạng.

### 4.2. Tạo SHA-256 cho JAR

Linux/macOS:

~~~bash
sha256sum target/catalog-service-1.0.0.jar
~~~

Lưu checksum:

~~~bash
sha256sum target/catalog-service-1.0.0.jar > target/catalog-service-1.0.0.jar.sha256
~~~

Kiểm tra file:

~~~bash
sha256sum -c target/catalog-service-1.0.0.jar.sha256
~~~

Nếu file khớp, output thường có dạng:

~~~text
target/catalog-service-1.0.0.jar: OK
~~~

Windows PowerShell:

~~~powershell
Get-FileHash .\target\catalog-service-1.0.0.jar -Algorithm SHA256
~~~

**Lưu ý:** kiểm tra checksum chỉ có giá trị khi file checksum được lấy từ một kênh tin cậy. Nếu attacker thay cả JAR và file .sha256, hai file vẫn có thể khớp nhau. Provenance có chữ ký và identity verification giúp kiểm tra nguồn gốc của digest.

### 4.3. Digest của container image

Với OCI image, digest thường xác định manifest hoặc image index. Ví dụ:

~~~text
ghcr.io/acme/catalog-service@sha256:012345...
~~~

Dùng **image@sha256:digest** khi cần tham chiếu chính xác nội dung đã xác minh. Tag vẫn có thể được dùng để người vận hành tìm release dễ dàng, nhưng deployment policy nên khóa vào digest đã duyệt.

Đối với multi-platform image, một digest có thể xác định **image index** chứa các platform manifests; digest của manifest linux/amd64 có thể khác manifest linux/arm64. Khi điều tra, phải xác định attestation subject đang ràng buộc index hay một platform manifest.

Theo OCI Image Specification, descriptor chứa media type, digest và kích thước bytes; consumer nên xác minh nội dung tải về khớp digest trước khi xử lý. Nguồn: https://github.com/opencontainers/image-spec/blob/main/descriptor.md

## 5. Provenance là gì?

**Build provenance** là metadata có cấu trúc mô tả artifact được tạo ra như thế nào, với đầu vào nào và bởi builder nào. Nó có thể trả lời:

- Source repository/commit nào được dùng?
- Build type hoặc pipeline nào chạy?
- Tham số bên ngoài nào ảnh hưởng build?
- Những dependencies/materials nào đã được resolve?
- Builder identity là gì?
- Build invocation bắt đầu/kết thúc khi nào?
- Output artifact nào được tạo, với digest nào?

SLSA định nghĩa một predicate cho build provenance trong khuôn khổ in-toto Attestation Framework. Predicate URI hiện dùng:

~~~text
https://slsa.dev/provenance/v1
~~~

**Không tự viết một JSON rồi gọi đó là provenance đáng tin.** Điều quan trọng là thông tin được tạo bởi builder có trust boundary rõ ràng, được ký/xác thực và có thể kiểm tra độc lập.

### 5.1. Các trường quan trọng trong SLSA provenance v1

Một SLSA provenance predicate có hai nhóm chính:

| Nhóm | Trường | Ý nghĩa |
| --- | --- | --- |
| Build definition | buildType | Mẫu/quy trình build đã chạy |
| Build definition | externalParameters | Đầu vào do caller/tenant bên ngoài kiểm soát |
| Build definition | internalParameters | Tham số do build platform quản lý |
| Build definition | resolvedDependencies | Dependencies/materials đã được resolve |
| Run details | builder.id | Định danh builder |
| Run details | metadata.invocationId | Định danh lần build |
| Run details | metadata.startedOn / finishedOn | Thời điểm build |
| Run details | byproducts | Các output phụ nếu có |
| Statement | subject | Artifact đầu ra và digest |

SLSA yêu cầu external parameters phải đầy đủ ở Build Level 3; đây là điểm quan trọng vì nếu còn một input ngoài chưa được ghi nhận, người kiểm tra không thể tái dựng đầy đủ build definition.

### 5.2. Ví dụ Statement rút gọn

JSON dưới đây chỉ minh họa cấu trúc; giá trị giả định và **không phải attestation có chữ ký**:

~~~json
{
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [
    {
      "name": "catalog-service-1.0.0.jar",
      "digest": {
        "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
      }
    }
  ],
  "predicateType": "https://slsa.dev/provenance/v1",
  "predicate": {
    "buildDefinition": {
      "buildType": "https://example.com/buildtypes/maven-release/v1",
      "externalParameters": {
        "repository": "https://github.com/acme/catalog-service",
        "ref": "refs/tags/v1.0.0"
      },
      "resolvedDependencies": [
        {
          "uri": "git+https://github.com/acme/catalog-service",
          "digest": {
            "gitCommit": "0123456789abcdef..."
          }
        }
      ]
    },
    "runDetails": {
      "builder": {
        "id": "https://github.com/acme/catalog-service/actions"
      },
      "metadata": {
        "invocationId": "123456789-1",
        "startedOn": "2026-11-09T02:00:00Z",
        "finishedOn": "2026-11-09T02:03:00Z"
      }
    }
  }
}
~~~

Đây là **mẫu giản lược để học cấu trúc**. Một provenance thực tế phải tuân schema và semantics của build platform; không tự gán builder.id hoặc buildType tùy ý rồi coi claim là đã được xác minh.

### 5.3. Subject là điểm liên kết quan trọng nhất

Trong Statement, **subject** xác định artifact mà attestation đang nói tới. Với file JAR, subject thường có tên file và SHA-256. Với image, subject dùng tên image và digest.

Nếu provenance nói về:

~~~text
catalog-service-1.0.0.jar + sha256:AAA...
~~~

nhưng release asset thực tế có digest:

~~~text
sha256:BBB...
~~~

thì provenance không chứng minh nguồn gốc cho file release đang có. Phải tạo lại hoặc tìm đúng attestation tương ứng với digest BBB; không sửa subject trong JSON bằng tay.

## 6. in-toto Statement, Envelope và DSSE

in-toto Attestation Framework tách các phần:

1. **Predicate**: nội dung claim theo schema cụ thể, ví dụ SLSA provenance hoặc CycloneDX.
2. **Statement**: gắn predicate với subject artifact và nêu predicate type.
3. **Envelope**: định dạng bao bọc và xử lý xác thực/chữ ký.
4. **Bundle**: cách nhóm attestation và tài liệu xác minh liên quan.

DSSE (Dead Simple Signing Envelope) là một định dạng envelope được sử dụng rộng rãi để ký payload theo cách có thể xác minh.

Sơ đồ:

~~~text
Artifact bytes
     |
     v
SHA-256 digest
     |
     v
in-toto Statement
  subject + predicateType + predicate
     |
     v
DSSE envelope
     |
     v
Signature + certificate / transparency evidence
     |
     v
Attestation bundle
~~~

**Statement không tự có chữ ký.** Một JSON Statement lưu trong repository có thể bị thay đổi. Cần xác minh envelope/chữ ký, certificate chain hoặc trust root và transparency evidence theo hệ thống sử dụng.

## 7. SBOM khác provenance như thế nào?

**Software Bill of Materials (SBOM)** là danh mục các thành phần phần mềm trong artifact hoặc trong quá trình build. Nó có thể liệt kê:
- Tên component, version, package URL (purl).
- Supplier/author và license nếu công cụ thu thập được.
- Hash của component.
- Quan hệ dependency.
- Metadata định danh tài liệu SBOM.

SBOM hỗ trợ inventory, vulnerability scanning, license review và incident response. Nhưng SBOM không tự chứng minh source commit hoặc builder identity.

### 7.1. CycloneDX cho Maven

CycloneDX Maven Plugin có thể tạo SBOM cho dependency graph trực tiếp và bắc cầu của Maven project.

Thêm plugin vào POM:

~~~xml
<plugin>
    <groupId>org.cyclonedx</groupId>
    <artifactId>cyclonedx-maven-plugin</artifactId>
    <version>2.9.3</version>
    <executions>
        <execution>
            <phase>package</phase>
            <goals>
                <goal>makeAggregateBom</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <outputFormat>json</outputFormat>
        <outputName>bom</outputName>
    </configuration>
</plugin>
~~~

Với cấu hình này, output thường là:

~~~text
target/bom.json
~~~

Goal **makeAggregateBom** hữu ích cho Maven multi-module reactor vì nó tổng hợp dependency BOM của các module. Goal **makeBom** tạo BOM theo từng module; **makePackageBom** dành cho packaging như WAR/EAR theo hỗ trợ của plugin.

Plugin version cần được quản lý và cập nhật như những dependency/plugin khác. Ví dụ dùng 2.9.3 để có một phiên bản release cụ thể; kiểm tra compatibility với CycloneDX schema mà hệ thống nhận SBOM hỗ trợ.

### 7.2. SBOM của JAR không nhất thiết là SBOM của container image

CycloneDX Maven plugin mô tả Maven project dependencies. Một container image còn có thể chứa:
- Run image/base OS packages.
- JRE và native libraries.
- Files được buildpack hoặc Dockerfile đưa vào.
- Agent/monitoring binaries.
- Các packages không thuộc Maven dependency graph.

Vì vậy, nếu phát hành container image, nên tạo **image SBOM** từ builder/tooling phù hợp và gắn nó với digest của image. Không dùng SBOM của JAR để tuyên bố đã liệt kê đầy đủ mọi package trong image.

## 8. Tạo project Maven minh họa

Ví dụ dùng Java 17 và Spring Boot 3.5.16. Version cụ thể phục vụ bài học; dự án thật cần chọn nhánh Spring Boot còn được tổ chức hỗ trợ.

### 8.1. Cấu trúc thư mục

~~~text
provenance-demo/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/...
└── src/
    ├── main/java/com/example/provenance/
    │   ├── ProvenanceDemoApplication.java
    │   └── BuildController.java
    ├── main/resources/application.properties
    └── test/java/com/example/provenance/
        └── BuildControllerTest.java
~~~

Maven Wrapper phải được tạo bằng Spring Initializr hoặc Maven Wrapper plugin; chỉ có POM không tự sinh scripts và wrapper metadata.

### 8.2. Main class

Tệp **src/main/java/com/example/provenance/ProvenanceDemoApplication.java**:

~~~java
package com.example.provenance;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProvenanceDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProvenanceDemoApplication.class, args);
    }
}
~~~

### 8.3. Controller

Tệp **src/main/java/com/example/provenance/BuildController.java**:

~~~java
package com.example.provenance;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BuildController {

    @GetMapping("/build")
    public String build() {
        return "provenance-demo-ok";
    }
}
~~~

Khi ứng dụng chạy thành công, GET /build trả body chính xác:

~~~text
provenance-demo-ok
~~~

### 8.4. application.properties

~~~properties
spring.application.name=provenance-demo
server.port=8080
~~~

### 8.5. Test

Tệp **src/test/java/com/example/provenance/BuildControllerTest.java**:

~~~java
package com.example.provenance;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BuildControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void buildEndpointReturnsExpectedBody() throws Exception {
        mvc.perform(get("/build"))
                .andExpect(status().isOk())
                .andExpect(content().string("provenance-demo-ok"));
    }
}
~~~

Test xác minh source behavior trước khi phát hành. Nó không thay thế việc xác minh provenance, digest hoặc container image.

### 8.6. POM đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>provenance-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>

            <plugin>
                <groupId>org.cyclonedx</groupId>
                <artifactId>cyclonedx-maven-plugin</artifactId>
                <version>2.9.3</version>
                <executions>
                    <execution>
                        <phase>package</phase>
                        <goals>
                            <goal>makeAggregateBom</goal>
                        </goals>
                    </execution>
                </executions>
                <configuration>
                    <outputFormat>json</outputFormat>
                    <outputName>bom</outputName>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**project.build.outputTimestamp** giúp những plugins có hỗ trợ tạo archive với timestamp ổn định; nó không tự bảo đảm mọi build metadata đều deterministic. Giá trị trong POM là mốc minh họa, release policy có thể lấy từ metadata của commit/tag đã chốt.

### 8.7. Build và xác định outputs

Linux/macOS:

~~~bash
./mvnw --version
./mvnw -B -ntp clean verify
~~~

Với Maven project này, outputs dự kiến:

~~~text
target/provenance-demo-1.0.0.jar
target/bom.json
~~~

Xác nhận files:

~~~bash
test -f target/provenance-demo-1.0.0.jar
test -f target/bom.json
sha256sum target/provenance-demo-1.0.0.jar target/bom.json
git rev-parse HEAD
git status --short
~~~

Trên Windows dùng **mvnw.cmd** và **Get-FileHash**. Nếu POM thay finalName/classifier hoặc plugin configuration, tên file thực có thể khác; hãy dùng chính artifact được phát hành.

## 9. Tạo provenance attestation trong GitHub Actions

GitHub Artifact Attestations sử dụng OIDC identity và Sigstore để tạo signed attestations. Với binary, action **actions/attest** có thể tự tính digest từ **subject-path**, sau đó tạo SLSA build provenance attestation.

Workflow phải cấp quyền tối thiểu cần thiết:
- **id-token: write** để action nhận OIDC token và xin certificate ký.
- **attestations: write** để lưu attestation.
- **contents: read** để checkout source.
- **artifact-metadata: write** nếu workflow cần tạo linked artifact storage records.
- **contents: write** chỉ khi workflow tạo/upload GitHub Release.
- **packages: write** khi publish image lên GHCR.

### 9.1. Workflow build và attest JAR

Tạo **.github/workflows/release.yml**:

~~~yaml
name: Build and attest release

on:
  push:
    tags:
      - "v*"

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest

    permissions:
      contents: write
      id-token: write
      attestations: write
      artifact-metadata: write

    steps:
      - name: Checkout source
        uses: actions/checkout@v6

      - name: Set up Java
        uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: "17"
          cache: maven

      - name: Build, test and generate SBOM
        run: ./mvnw -B -ntp clean verify

      - name: Generate build provenance
        id: provenance
        uses: actions/attest@v4
        with:
          subject-path: target/provenance-demo-1.0.0.jar

      - name: Generate SBOM attestation
        id: sbom
        uses: actions/attest@v4
        with:
          subject-path: target/provenance-demo-1.0.0.jar
          sbom-path: target/bom.json

      - name: Create checksum
        run: sha256sum target/provenance-demo-1.0.0.jar > target/provenance-demo-1.0.0.jar.sha256

      - name: Create release evidence index
        env:
          PROVENANCE_URL: ${{ steps.provenance.outputs.attestation-url }}
          SBOM_ATTESTATION_URL: ${{ steps.sbom.outputs.attestation-url }}
          SOURCE_COMMIT: ${{ github.sha }}
          SOURCE_REF: ${{ github.ref }}
          WORKFLOW_RUN: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
        run: |
          python - <<'PY'
          import hashlib
          import json
          import os
          from pathlib import Path

          artifact = Path("target/provenance-demo-1.0.0.jar")
          digest = hashlib.sha256(artifact.read_bytes()).hexdigest()

          record = {
              "artifact": artifact.name,
              "sha256": digest,
              "sourceCommit": os.environ["SOURCE_COMMIT"],
              "sourceRef": os.environ["SOURCE_REF"],
              "workflowRun": os.environ["WORKFLOW_RUN"],
              "provenanceAttestation": os.environ["PROVENANCE_URL"],
              "sbomAttestation": os.environ["SBOM_ATTESTATION_URL"]
          }

          Path("target/release-evidence.json").write_text(
              json.dumps(record, indent=2) + "\n",
              encoding="utf-8"
          )
          PY

      - name: Publish release assets
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          if gh release view "$GITHUB_REF_NAME" >/dev/null 2>&1; then
            gh release upload "$GITHUB_REF_NAME" target/provenance-demo-1.0.0.jar target/provenance-demo-1.0.0.jar.sha256 target/bom.json target/release-evidence.json --clobber
          else
            gh release create "$GITHUB_REF_NAME" target/provenance-demo-1.0.0.jar target/provenance-demo-1.0.0.jar.sha256 target/bom.json target/release-evidence.json --generate-notes
          fi
~~~

Đây là workflow minh họa cho một tag release. Trong môi trường production:
- Pin GitHub Actions theo full commit SHA hoặc dùng dependency lockfile theo policy; tag action có thể thay đổi.
- Bảo vệ release tags và kiểm soát ai được phép tạo tag.
- Đặt version của artifact động từ Maven metadata thay vì hardcode nếu release workflow dùng nhiều versions.
- Tách job có quyền publish khỏi job build/test khi cần giới hạn blast radius.
- Kiểm tra repository/plan có hỗ trợ Artifact Attestations. GitHub Free/Pro/Team chỉ hỗ trợ trong public repositories; private/internal repositories cần GitHub Enterprise Cloud theo tài liệu hiện hành.

### 9.2. Điều gì được ký?

Bước **Generate build provenance** dùng JAR tại subject-path, tính digest và tạo attestation gắn với artifact. Bước **Generate SBOM attestation** gắn tài liệu CycloneDX với cùng subject JAR.

Hai attestation có predicate khác nhau:
- Provenance mô tả source/build process/builder.
- SBOM attestation gắn BOM với artifact và cho phép kiểm tra components.

Không dùng riêng URL attestation làm định danh artifact; luôn lưu cả **artifact SHA-256** và link attestation. Nếu file JAR bị thay đổi sau bước attest, digest sẽ khác và verification phải fail.

### 9.3. Attestation URL và bundle

Action có thể xuất:
- **attestation-url**: liên kết tới bản ghi attestation trong GitHub.
- **bundle-path**: đường dẫn tới Sigstore bundle JSON trên runner.
- **attestation-id**: ID của bản ghi.

Có thể lưu bundle như một release evidence file hoặc artifact CI để phục vụ offline verification theo policy. Nếu bundle được upload riêng, cần kiểm tra nó gắn đúng subject digest và giữ nguyên bytes của bundle. Không sửa JSON bundle sau khi action tạo chữ ký.

## 10. Xác minh provenance của JAR trước khi sử dụng

Cài GitHub CLI và đăng nhập bằng tài khoản có quyền đọc repository/attestation. Kiểm tra phiên bản:

~~~bash
gh --version
gh auth status
~~~

Xác minh file JAR:

~~~bash
gh attestation verify target/provenance-demo-1.0.0.jar --repo ORG/REPO
~~~

Lệnh này xác minh attestation tương ứng với digest của file được đưa vào và repository đã chỉ định. Với policy chặt hơn, kiểm tra signer workflow và source ref:

~~~bash
gh attestation verify target/provenance-demo-1.0.0.jar --repo ORG/REPO --signer-workflow ORG/REPO/.github/workflows/release.yml --source-ref refs/tags/v1.0.0
~~~

Tên **ORG/REPO** và tag là placeholder; thay bằng repository/tag thật. Nếu dùng reusable workflow, signer identity là reusable workflow đã ký attestation, không nhất thiết là caller workflow; cần chọn đúng **signer-workflow** hoặc **signer-repo**.

GitHub CLI mặc định kiểm tra predicate type **https://slsa.dev/provenance/v1**. Nếu xác minh SBOM attestation, dùng **--predicate-type** với đúng URI predicate được ghi trong Statement; không giả định mọi version CycloneDX đều có cùng versioned URI.

### 10.1. Xem nội dung verification result

~~~bash
gh attestation verify target/provenance-demo-1.0.0.jar --repo ORG/REPO --format json
~~~

Kết quả JSON có thể chứa:
- Certificate identity và OIDC issuer.
- Verified timestamps từ transparency log hoặc timestamp authority.
- Statement subject và digest.
- Predicate type và predicate data.

Khi xây policy tự động, phải phân biệt claim nào đến từ certificate/transparency evidence và claim nào là nội dung predicate do build workflow tạo. Nếu attacker kiểm soát workflow execution, họ có thể giả mạo một số trường predicate; trusted builder và signer workflow isolation giúp giảm rủi ro.

### 10.2. Xác minh checksum sau download

Người dùng tải release asset:

~~~bash
sha256sum -c provenance-demo-1.0.0.jar.sha256
~~~

Sau đó xác minh attestation của file đã tải:

~~~bash
gh attestation verify provenance-demo-1.0.0.jar --repo ORG/REPO
~~~

Hai phép kiểm tra bổ sung cho nhau. Checksum phát hiện file không khớp digest được công bố; attestation xác minh digest đó có claim nguồn gốc được ký bởi identity mong đợi.

## 11. Liên kết provenance với OCI image đã phát hành

Với container image, subject phải là **digest của image manifest/index**, không phải digest của JAR nằm bên trong và cũng không phải tag mutable.

Quy trình:
1. Build image và push lên registry.
2. Lấy digest output từ builder.
3. Tạo attestation dùng full image name và digest.
4. Publish/ghi lại tag release như nhãn dễ đọc.
5. Deploy bằng image digest đã được xác minh.

### 11.1. GitHub Actions + Buildx + GHCR

Ví dụ workflow fragment (cần thêm vào job container release hoặc job riêng):

~~~yaml
permissions:
  contents: read
  id-token: write
  attestations: write
  packages: write
  artifact-metadata: write

steps:
  - name: Log in to GHCR
    uses: docker/login-action@v3
    with:
      registry: ghcr.io
      username: ${{ github.actor }}
      password: ${{ github.token }}

  - name: Build and push image
    id: image
    uses: docker/build-push-action@v6
    with:
      context: .
      push: true
      tags: ghcr.io/${{ github.repository }}:${{ github.sha }}
      provenance: mode=max
      sbom: true

  - name: Generate signed image provenance
    id: image-attestation
    uses: actions/attest@v4
    with:
      subject-name: ghcr.io/${{ github.repository }}
      subject-digest: ${{ steps.image.outputs.digest }}
      push-to-registry: true
~~~

Trong image attestation:
- **subject-name** là fully qualified image name, không thêm tag.
- **subject-digest** là SHA-256 digest do Buildx trả về, dạng sha256:...
- **push-to-registry=true** yêu cầu lưu attestation ở registry; action cũng có thể tạo linked artifact storage records khi workflow có quyền phù hợp.

BuildKit **provenance=mode=max** và **sbom=true** tạo thêm build attestations. GitHub **actions/attest** tạo signed attestation theo GitHub OIDC identity. Đây là hai cơ chế có thể bổ sung nhau, không phải cùng một chữ ký hay cùng một nguồn trust.

### 11.2. Xác minh image attestation

Đăng nhập registry rồi xác minh:

~~~bash
docker login ghcr.io
gh attestation verify oci://ghcr.io/ORG/IMAGE:TAG --repo ORG/REPO
~~~

Trong deployment policy, nên lấy digest đã được build/publish và xác minh, rồi dùng:

~~~text
ghcr.io/ORG/IMAGE@sha256:IMAGE_DIGEST
~~~

Đối với một multi-platform image, hãy biết digest subject đang xác minh là image index hay platform-specific manifest. Không thay digest bằng tag sau khi đã xác minh; tag có thể trỏ tới artifact khác ở lần pull sau.

## 12. BuildKit provenance và SBOM

Docker Buildx có thể tạo attestation trong quá trình build:

~~~bash
docker buildx build --tag ghcr.io/acme/catalog-service:1.0.0 --provenance=mode=max --sbom=true --push .
~~~

Các cờ:
- **--provenance=mode=max** yêu cầu provenance chi tiết hơn mức tối thiểu.
- **--sbom=true** yêu cầu SBOM attestation.
- **--push** xuất image và attestations lên registry.

BuildKit tạo provenance dạng in-toto JSON và gắn attestations vào image index/manifest theo cơ chế storage của BuildKit. **Minimal provenance** có thể được tạo mặc định; dùng mode=max khi cần thêm thông tin build. Không để secrets trong Docker ARG/ENV vì build metadata có thể làm lộ các giá trị cấu hình không nên công khai.

### 12.1. Vì sao không thấy attestation trong Docker local image?

Default Docker Engine image store có thể không lưu/persist attestations. Docker documentation nêu attestations sẽ tồn tại khi push trực tiếp lên registry với default image store; một lựa chọn khác là dùng containerd image store hỗ trợ attestations.

Vì vậy:
- Nếu build local với **--load**, đừng giả định provenance/SBOM vẫn nằm trong local image store.
- Nếu cần consumer lấy evidence từ registry, build/push trực tiếp và kiểm tra registry artifacts.
- Nếu dùng containerd image store, kiểm tra Docker Engine version và storage configuration tương ứng.

### 12.2. BuildKit provenance có phải chữ ký không?

Không nên đồng nhất hai khái niệm. BuildKit tạo build attestation metadata. Để xác minh signer identity và authenticity, cần một cơ chế signature/attestation phù hợp như Sigstore/Cosign hoặc GitHub Artifact Attestations.

Trong release policy, xác định rõ:
- Nguồn provenance: BuildKit, GitHub Actions, buildpacks hay builder nội bộ.
- Nguồn chữ ký/identity: Sigstore OIDC, KMS key, hardware key hoặc signing service.
- Vị trí lưu attestation: GitHub API, OCI registry referrers, bundle store.
- Quy tắc xác minh: subject digest, predicate type, issuer, workflow identity và builder.

## 13. Cosign/Sigstore cho registry không phụ thuộc GitHub

Nếu tổ chức không dùng GitHub Artifact Attestations, **Sigstore Cosign** là một lựa chọn phổ biến để ký image và xác minh attestation. Cosign hỗ trợ key-based và keyless signing; với keyless, danh tính OIDC được ràng buộc vào certificate ngắn hạn và transparency log.

Một ví dụ verify attestation trên image đã được ký theo SLSA provenance:

~~~bash
cosign verify-attestation --type slsaprovenance --certificate-identity-regexp '^https://github.com/ORG/REPO/.github/workflows/release.yml@refs/tags/v.*$' --certificate-oidc-issuer https://token.actions.githubusercontent.com ghcr.io/ORG/IMAGE@sha256:IMAGE_DIGEST
~~~

Đây là lệnh **xác minh**. Regex identity phải khớp certificate SAN thật do hệ thống ký phát hành; không copy nguyên placeholder. Nếu dùng key-based signing, xác minh với public key đã được phân phối qua kênh tin cậy.

Có thể dùng Rego/CUE policy với Cosign để kiểm tra predicate contents ngoài chữ ký. **Chữ ký hợp lệ nhưng predicate sai policy vẫn phải bị từ chối.**

## 14. Gắn bằng chứng với GitHub Release

Một release nên có một bộ thông tin dễ tìm:

~~~text
Release v1.0.0
├── provenance-demo-1.0.0.jar
├── provenance-demo-1.0.0.jar.sha256
├── bom.json
├── release-evidence.json
└── GitHub attestation record / bundle
~~~

Vai trò:
- JAR: binary được cài đặt.
- SHA-256: checksum sidecar để phát hiện thay đổi.
- bom.json: SBOM để kiểm tra thành phần.
- release-evidence.json: index liên kết commit, artifact digest, workflow run, provenance URL, SBOM URL.
- Attestation: claim có chữ ký, gắn với subject digest.

### 14.1. Ví dụ release-evidence.json

~~~json
{
  "release": "v1.0.0",
  "source": {
    "repository": "https://github.com/acme/provenance-demo",
    "ref": "refs/tags/v1.0.0",
    "commit": "0123456789abcdef0123456789abcdef01234567"
  },
  "build": {
    "workflow": ".github/workflows/release.yml",
    "runId": "123456789",
    "builder": "GitHub Actions"
  },
  "artifact": {
    "name": "provenance-demo-1.0.0.jar",
    "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "releaseAsset": "https://github.com/acme/provenance-demo/releases/download/v1.0.0/provenance-demo-1.0.0.jar"
  },
  "evidence": {
    "provenanceAttestation": "https://github.com/acme/provenance-demo/attestations/123",
    "sbomAttestation": "https://github.com/acme/provenance-demo/attestations/124",
    "sbom": "bom.json"
  }
}
~~~

Đây là **mẫu chỉ mục**, không phải bản provenance đã ký. File này giúp con người tìm bằng chứng; consumer vẫn phải xác minh attestation cryptographically và so digest của release asset.

### 14.2. Không rebuild sau khi attest rồi upload một file khác

Trình tự đúng:
1. Build/test.
2. Tạo SBOM.
3. Tính digest và tạo attestation.
4. Upload **đúng bytes đó** lên release.
5. Consumer tải file, tính lại digest và xác minh attestation.

Nếu chạy lại Maven sau khi attestation rồi upload JAR mới, dù cùng tên/version, digest có thể khác. Nếu cần build lại, tạo provenance mới và cập nhật release/evidence một cách có kiểm soát.

## 15. Tạo evidence cho Spring Boot image bằng Buildpacks

Nếu dùng Maven **spring-boot:build-image** hoặc Cloud Native Buildpacks, image được tạo bởi builder/buildpacks thay vì Dockerfile tự viết. Provenance cần ghi nhận:
- Source commit/repository.
- Maven command và plugin version.
- Builder image và buildpack IDs/versions.
- Run image reference/digest.
- Java version/JDK provider.
- Dependency inputs và application artifact digest.
- Final OCI image digest.

Không ghi chung chung “built by Maven” nếu builder thực tế là Paketo/CNB. Builder identity và buildpack versions là phần quan trọng của supply chain.

Với Spring Boot buildpacks:
1. Pin builder/run image theo version hoặc digest.
2. Lưu Maven Wrapper, POM, plugin versions và dependency lock/management policy.
3. Build image trên CI runner có identity được kiểm soát.
4. Lấy final registry digest.
5. Tạo signed attestation với image digest làm subject.
6. Giữ SBOM của application và SBOM của image nếu phạm vi inventory yêu cầu.
7. Xác minh attestation trước khi deploy.

Nếu builder không tự xuất SLSA provenance phù hợp, CI có thể dùng một trusted workflow để tạo provenance cho final image. Phải chắc chắn digest subject là **image đã được export**, không phải một intermediate JAR hoặc builder cache.

## 16. Những gì phải kiểm tra khi verify provenance

Một lệnh verify trả success mới chỉ là bước đầu. Consumer cần có **policy** cụ thể.

### 16.1. Subject

- Tên artifact có đúng artifact mong đợi?
- Digest có đúng với file/image đang chuẩn bị sử dụng?
- Digest algorithm có được chấp nhận (thường SHA-256)?
- Có nhầm tag với digest không?

### 16.2. Source identity

- Repository có đúng organization/project được tin cậy?
- Source commit có phải commit/tag đã duyệt?
- Tag có được bảo vệ hoặc xác minh chữ ký theo release policy?
- Workflow run có chạy từ đúng source ref?

### 16.3. Builder identity

- Builder ID có thuộc hệ thống được tổ chức phê duyệt?
- Workflow path có đúng release workflow?
- Signer repository có đúng?
- OIDC issuer/certificate chain/transparency evidence có hợp lệ?
- Có dùng reusable trusted workflow khi cần isolation không?

### 16.4. Build inputs

- Java, Maven, Spring Boot Plugin versions có đúng policy?
- Builder/buildpack/run image có được pin?
- Dependencies có được resolve từ repository tin cậy?
- Có build arguments hoặc environment values ngoài dự kiến?
- Có dùng untrusted cache hoặc artifacts từ pull request không?

### 16.5. Predicate type và completeness

- Predicate có đúng SLSA provenance v1?
- Có subject digest và buildDefinition?
- External parameters có đầy đủ theo yêu cầu của level/policy?
- Resolved dependencies có đủ để giải thích đầu vào?
- Builder ID có được trust platform đánh giá không?

**Không chấp nhận chỉ vì JSON có trường repository và commit**. Các trường có thể do workflow tự khai. Phải xác minh identity đã ký và mức đảm bảo của builder.

## 17. SLSA levels: không tự nhận level chỉ vì có file provenance

SLSA là một bộ tiêu chuẩn giúp mô tả và tăng dần mức bảo vệ supply chain. Build provenance là một thành phần quan trọng, nhưng các SLSA Build Levels còn đặt yêu cầu về build platform, isolation, provenance completeness và khả năng chống can thiệp.

Không tuyên bố “đạt SLSA Level 3” chỉ vì:
- Có file JSON tên provenance.
- Dùng một GitHub Action sinh attestation.
- Có chữ ký Cosign.
- Có SBOM.
- CI workflow đã chạy thành công.

Cần đánh giá chính xác builder, trust boundary, cách source/config được kiểm soát, mức đầy đủ của parameters/dependencies, cách signer được tách khỏi untrusted caller và cách consumer xác minh.

SLSA v1.2 mô tả Build Level 3 yêu cầu externalParameters đầy đủ, tức không còn một input ngoài chưa được ghi nhận có thể tác động build. Đây là lý do workflow và builder isolation quan trọng.

## 18. Bảo vệ workflow và builder identity

Một provenance có chữ ký vẫn có thể mang claim sai nếu workflow/build context đã bị attacker kiểm soát. Một số biện pháp:

- Dùng protected branches/tags và yêu cầu review cho release workflow.
- Không cho untrusted pull request truy cập release credentials hoặc signing permissions.
- Tách job build/test khỏi job publish/sign nếu cần trust boundary rõ.
- Dùng reusable trusted workflows hoặc managed builders có policy riêng.
- Pin GitHub Actions theo full commit SHA hoặc dependency lockfile.
- Hạn chế permissions của GITHUB_TOKEN theo từng job.
- Không đưa secrets vào Docker build args, Maven command line hoặc environment bị ghi vào provenance.
- Không dùng mutable builder/action tags cho release quan trọng mà không có quy trình kiểm soát.
- Giới hạn quyền publish image và release asset.
- Giám sát thay đổi workflow files và branch protection rules.

### 18.1. Pull request và fork

Build cho pull request từ fork nên có quyền thấp, không có quyền publish/sign release. Nếu workflow kiểm tra code không tin cậy, attacker có thể cố thay đổi script để lấy token hoặc tạo artifact giả.

Chỉ build release từ ref đã được phê duyệt. Khi cần kiểm tra pull request, tạo CI artifact tạm và không ký nó bằng release identity được consumer tin cậy.

### 18.2. Self-hosted runners

Self-hosted runners cần được bảo vệ như build infrastructure. Một runner bị compromise có thể ảnh hưởng đến source checkout, build outputs và signing context. Dùng ephemeral runners, cô lập jobs, cập nhật host, giới hạn network và không dùng cùng một runner cho workloads tin cậy và không tin cậy nếu không có isolation mạnh.

## 19. Lưu trữ và vòng đời evidence

Provenance chỉ hữu ích nếu consumer và auditor có thể tìm lại khi cần.

Nên xác định:
- Attestation được lưu ở GitHub API, OCI registry, transparency log hay evidence store nội bộ.
- Bundle offline có được lưu cùng release không.
- SBOM có được giữ cùng release và theo version không.
- Build logs và workflow run retention bao lâu.
- Image registry retention có xóa artifact referrers/attestations không.
- Ai được phép xóa/sửa release assets.
- Cách replicate evidence giữa registry regions/accounts.
- Quy trình thu hồi hoặc đánh dấu artifact bị compromised.

Không chỉ giữ URL tới một workflow run nếu run/log có thể hết retention. Lưu bundle/attestation ở nơi lâu dài theo policy, kèm digest và metadata giúp truy xuất.

### 19.1. Release record tối thiểu

Một record release nên chứa:
- Product/module + version.
- Git repository + commit + tag.
- Artifact file name + SHA-256.
- OCI image name + digest nếu có.
- Builder/workflow identity + run ID.
- Provenance attestation URL/ID/bundle.
- SBOM URL/digest/format/schema version.
- Test/security scan results.
- Release date và người/automation phê duyệt.

Record này là index cho evidence, không thay chữ ký hoặc attestation.

## 20. Incident response: khi phát hiện một dependency có CVE

Giả sử một thư viện trong Spring Boot service bị phát hiện lỗ hổng nghiêm trọng. Đội security cần biết release nào bị ảnh hưởng.

Quy trình:
1. Dùng SBOM để tìm artifacts chứa package/version bị ảnh hưởng.
2. Dùng provenance để xác định source commit, build run và dependency resolution đã tạo artifact.
3. Tìm image digests/releases đã phát hành từ artifact đó.
4. Xác định deployment nào đang chạy digest bị ảnh hưởng.
5. Build bản sửa từ source đã review.
6. Tạo SBOM/provenance mới, xác minh digest và signer.
7. Publish image mới, deploy bằng digest mới.
8. Lưu evidence cho release cũ và mới để audit.

Không sửa SBOM của release cũ để nó trông như không có package dễ tổn thương. SBOM phải mô tả artifact thực tế đã được phát hành. Tạo SBOM mới cho artifact mới, giữ liên kết rõ ràng giữa các version.

## 21. Kiểm tra provenance khi triển khai Kubernetes

Một pipeline tốt không chỉ verify ở máy developer. Deployment admission/policy layer có thể yêu cầu:
- Image reference dùng digest.
- Có provenance attestation.
- Subject digest khớp image đang deploy.
- Signer workflow/repository đúng.
- Source ref/commit thuộc release được phép.
- Builder nằm trong allowlist.
- SBOM tồn tại và vượt vulnerability/license policy.

Ví dụ manifest:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog-service
  template:
    metadata:
      labels:
        app: catalog-service
    spec:
      containers:
        - name: app
          image: ghcr.io/acme/catalog-service@sha256:0123456789abcdef...
          ports:
            - containerPort: 8080
~~~

Digest rút gọn chỉ minh họa; Kubernetes image reference phải dùng digest đầy đủ hợp lệ. Admission controller/policy engine có thể từ chối image nếu provenance không đạt policy trước khi Pod được tạo.

**Không triển khai chỉ bằng tag mutable** nếu yêu cầu audit đòi biết chính xác bytes đã được chạy. Ghi digest vào deployment record để liên kết runtime workload với release evidence.

## 22. Những sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Chỉ lưu Git SHA | Không xác định bytes artifact | Ghi subject digest và provenance |
| Chỉ lưu SHA-256 sidecar | Không xác định ai tạo file | Verify signed attestation |
| Dùng tag image thay digest | Tag có thể bị di chuyển | Deploy image@sha256 |
| Attest JAR rồi upload bản JAR khác | Subject digest không còn khớp | Upload đúng file đã attest |
| SBOM bị gọi là provenance | SBOM mô tả components, không mô tả builder | Tạo cả hai |
| Provenance JSON không chữ ký | Có thể bị sửa | Dùng signed envelope và verify |
| Chỉ kiểm tra chữ ký | Có thể đúng signer nhưng sai source/policy | Enforce repo, workflow, ref, builder, predicate |
| Chỉ tin các trường predicate | Workflow bị compromise có thể khai sai | Trust builder/certificate, isolate signing |
| Đưa secret vào build args | Có thể lộ trong logs/metadata | Dùng secret mounts/bindings an toàn |
| Dùng workflow PR để ký release | Untrusted code có thể ảnh hưởng signer | Tách build/test PR khỏi release signing |
| Chỉ SBOM của JAR cho image | Bỏ sót OS/JRE/buildpack packages | Tạo image SBOM riêng |
| Dùng mutable builder tag không kiểm soát | Build lại có thể dùng builder khác | Pin version/digest và record builder |
| Xóa attestation cùng image | Mất evidence khi audit | Quản lý retention/referrers/bundle |
| Dùng local Docker Image ID làm registry digest | Không phải cùng identifier | Lấy manifest digest từ registry/build output |
| Không phân biệt image index và platform manifest | So nhầm subject | Ghi rõ platform/digest type |
| Nhận SLSA level chỉ từ tool | Tool không đảm bảo toàn bộ requirements | Đánh giá builder và verification controls |

## 23. Checklist cho một release có provenance

### Source và build
- [ ] Build từ commit/tag đã chốt.
- [ ] Working tree sạch hoặc mọi thay đổi đã được ghi nhận.
- [ ] Maven Wrapper/JDK/plugin versions được quản lý.
- [ ] Dependencies được resolve từ repository được phê duyệt.
- [ ] Workflow và builder identity được xác định.
- [ ] Untrusted PR không có quyền ký/publish release.

### Artifact và SBOM
- [ ] Tests/build checks PASS trước khi ký.
- [ ] Artifact file được định danh bằng SHA-256.
- [ ] CycloneDX/SPDX SBOM được tạo đúng scope.
- [ ] Image có SBOM riêng nếu release là container.
- [ ] SBOM format/schema và digest được ghi lại.

### Provenance và signature
- [ ] Statement subject trỏ tới đúng artifact digest.
- [ ] Predicate type đúng SLSA provenance v1 hoặc policy đã chọn.
- [ ] Builder/workflow identity được xác minh.
- [ ] Source repository/ref/commit khớp release.
- [ ] Signature/certificate/issuer/transparency evidence PASS.
- [ ] Build inputs và resolved dependencies đáp ứng policy.

### Publish và deploy
- [ ] Upload đúng bytes đã attest.
- [ ] Release evidence index lưu artifact digest và attestation URL/bundle.
- [ ] Container image được tham chiếu bằng digest.
- [ ] Consumer verify trước khi cài đặt/deploy.
- [ ] Admission/deployment policy từ chối artifacts không đạt.
- [ ] Attestation, SBOM và release records được lưu theo retention policy.

## 24. Bài tập tự kiểm tra

**Câu 1.** Vì sao Git commit SHA không thể thay cho JAR SHA-256?

**Đáp án:** Commit SHA định danh source tree; JAR SHA-256 định danh bytes của binary đã build. Cùng commit có thể tạo nhiều binaries nếu toolchain, dependencies hoặc inputs khác.

**Câu 2.** Provenance và SBOM khác nhau thế nào?

**Đáp án:** Provenance mô tả cách artifact được tạo; SBOM liệt kê components có trong artifact/phạm vi được quét. Một release nên có cả hai nếu policy yêu cầu.

**Câu 3.** Vì sao phải đưa digest vào subject?

**Đáp án:** Subject gắn attestation với đúng bytes. Nếu chỉ dùng tên hoặc tag, tham chiếu có thể được thay bằng artifact khác mà tên vẫn giữ nguyên.

**Câu 4.** Attestation có chữ ký hợp lệ có đảm bảo mọi claim đều đúng không?

**Đáp án:** Không. Cần tin builder identity, kiểm tra predicate contents, nguồn workflow, trust boundary và chính sách đầu vào.

**Câu 5.** Tại sao cần kiểm tra signer-workflow?

**Đáp án:** Để đảm bảo attestation được ký bởi đúng release workflow hoặc trusted reusable workflow, không chỉ bởi một workflow bất kỳ trong repository.

**Câu 6.** Có thể dùng SBOM của JAR cho container image không?

**Đáp án:** Nó có thể mô tả Maven dependencies nhưng thường chưa đủ cho toàn image vì base OS, JRE và native packages có thể nằm ngoài Maven graph.

**Câu 7.** Vì sao deploy bằng image digest tốt hơn tag?

**Đáp án:** Digest xác định manifest content. Tag là tham chiếu có thể được di chuyển tới image khác.

**Câu 8.** BuildKit provenance và GitHub signed attestation có phải một thứ không?

**Đáp án:** Không. BuildKit tạo build metadata attestation; GitHub Artifact Attestations thêm cơ chế signed identity/trust phù hợp. Có thể dùng bổ sung và phải biết nơi lưu từng loại.

**Câu 9.** Sau khi attest, có được rebuild rồi upload JAR mới cùng tên không?

**Đáp án:** Không nếu muốn giữ liên kết. File mới có thể có digest khác; phải tạo attestation mới và cập nhật release evidence.

**Câu 10.** Có thể tuyên bố SLSA Build Level 3 chỉ vì workflow dùng actions/attest@v4 không?

**Đáp án:** Không. Còn phải đáp ứng yêu cầu về trusted builder, isolation, completeness của inputs/provenance và các controls khác.

## 25. Tài liệu tham khảo chính thức

- SLSA v1.2 — Build Provenance: https://slsa.dev/spec/v1.2/build-provenance
- SLSA — Verifying Artifacts: https://slsa.dev/spec/v1.2/verifying-artifacts
- in-toto Attestation Framework: https://github.com/in-toto/attestation
- in-toto Predicate — CycloneDX: https://github.com/in-toto/attestation/blob/main/spec/predicates/cyclonedx.md
- GitHub Actions — Using artifact attestations: https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations
- GitHub CLI — gh attestation verify: https://cli.github.com/manual/gh_attestation_verify
- GitHub Actions — actions/attest: https://github.com/actions/attest
- GitHub Actions — Secure use / pin actions: https://docs.github.com/en/actions/reference/security/secure-use
- Sigstore Cosign — verify-attestation: https://github.com/sigstore/cosign/blob/main/doc/cosign_verify-attestation.md
- OCI Image Specification — Content descriptors and digests: https://github.com/opencontainers/image-spec/blob/main/descriptor.md
- OCI Image Specification — Image manifest: https://github.com/opencontainers/image-spec/blob/main/manifest.md
- Docker — Build attestations: https://docs.docker.com/build/metadata/attestations/
- Docker Buildx — build provenance and SBOM options: https://docs.docker.com/reference/cli/docker/buildx/build/
- CycloneDX Maven Plugin — makeAggregateBom: https://cyclonedx.github.io/cyclonedx-maven-plugin/makeAggregateBom-mojo.html
- CycloneDX — SBOM standard: https://cyclonedx.org/
