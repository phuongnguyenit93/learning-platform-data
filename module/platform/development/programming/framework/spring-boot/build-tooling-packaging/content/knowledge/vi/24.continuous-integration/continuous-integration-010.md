# Đính kèm checksum, SBOM và metadata vào kết quả CI cho Spring Boot

## 1. Mục tiêu: mỗi bản build phải có bộ bằng chứng đi cùng artifact

Một pipeline CI không nên chỉ trả về dòng BUILD SUCCESS và một file JAR. Người nhận artifact cần trả lời được:

- **Artifact này là file nào?** Tên, version, định dạng, kích thước và SHA-256 là gì?
- **Nó được build từ source nào?** Git repository, commit, ref/tag và build run nào?
- **Nó chứa thành phần phần mềm nào?** Dependencies trực tiếp/gián tiếp, phiên bản, package URL (PURL), quan hệ phụ thuộc và license được ghi trong SBOM ra sao?
- **Image đã publish là image nào?** Registry, immutable digest, builder/base image và SBOM của image ở đâu?
- **Ai/điều gì xác nhận kết quả?** Checksum, chữ ký và build provenance có thể được xác minh thế nào?
- **CI giữ kết quả bao lâu, ai được tải và làm sao tái kiểm chứng sau khi tải về?**

**Bộ release evidence** (bằng chứng phát hành) nên đi cùng JAR/WAR hoặc container image:

~~~text
release-evidence/
├── release-demo.jar
├── application-sbom.cdx.json
├── image-sbom.cdx.json             # nếu có OCI image
├── build-metadata.json
├── SHA256SUMS
├── SHA256SUMS.sigstore.json        # nếu ký checksum manifest
├── provenance.intoto.jsonl        # nếu CI xuất provenance
└── buildx-metadata.json            # nếu dùng Docker Buildx
~~~

Tên file là ví dụ. Không phải mọi dự án đều cần tất cả các file; **JAR, SBOM tương ứng, metadata và checksum** là bộ tối thiểu hữu ích. Với sản phẩm container, thêm image digest và SBOM quét từ image đã build. Chữ ký/provenance được bổ sung khi release policy yêu cầu.

Bài dùng **Java 17 và Spring Boot 3.3.13**, minh họa Maven và Gradle, định dạng SBOM **CycloneDX 1.6**, SHA-256, GitHub Actions, Syft và Cosign. Đây là bộ phiên bản tham khảo để người học chạy; hãy pin phiên bản plugin/tool được tổ chức duyệt và kiểm tra compatibility của build tool hiện tại. Các lệnh dưới đây là hướng dẫn, không phải kết quả CI đã chạy.

## 2. Phân biệt bốn loại bằng chứng

| Thành phần | Câu hỏi nó trả lời | Nó không chứng minh điều gì? |
| --- | --- | --- |
| **Checksum (SHA-256)** | Bytes của file hiện tại có giống bytes tại thời điểm checksum được tạo không? | Không tự chứng minh ai tạo file hoặc file có nguồn gốc đáng tin. |
| **SBOM** | Artifact/image được mô tả có những thành phần phần mềm nào? | Không tự chứng minh artifact đã được scan lỗ hổng, không bảo đảm phát hiện mọi thành phần. |
| **Build metadata** | Source commit, build run, toolchain, artifact path/digest và các thông tin build là gì? | File JSON tự tạo không tự chứng minh metadata là chính xác hay được ký. |
| **Build provenance / attestation** | Builder đáng tin đã tạo artifact nào, từ input và quy trình nào? | Không thay thế kiểm tra chữ ký, trust policy hoặc kiểm tra SBOM/vulnerability. |

### 2.1. Checksum là kiểm tra toàn vẹn bytes

SHA-256 nhận bytes của file và trả về digest 256-bit (64 ký tự hex). Nếu một byte trong JAR thay đổi, digest gần như chắc chắn thay đổi.

Checksum giúp phát hiện artifact bị lỗi khi upload/download/copy, file bị thay sau khi tạo evidence, người nhận tải nhầm file/version hoặc artifact được lưu ở hai nơi có bytes khác nhau.

Nhưng nếu attacker có thể thay cả JAR **và** SHA256SUMS, họ có thể tạo checksum mới tương ứng. Vì vậy checksum manifest phải được bảo vệ bằng **chữ ký/attestation đáng tin**, hoặc được phân phối qua kênh có tính toàn vẹn và identity được xác thực.

### 2.2. SBOM là danh mục thành phần phần mềm

**Software Bill of Materials (SBOM)** là bản kê khai components của một software deliverable. Với ứng dụng Java, SBOM có thể mô tả component gốc (group/name/version), dependency trực tiếp và gián tiếp, phiên bản được build tool giải quyết sau conflict resolution/constraints, PURL, supplier, license, external references và dependency graph khi có metadata.

SBOM hỗ trợ kiểm kê, rà soát license, truy tìm dependency bị ảnh hưởng bởi CVE và chia sẻ thông tin chuỗi cung ứng với người nhận artifact. **SBOM không phải báo cáo vulnerability**: cần chạy SCA/vulnerability scanner riêng và ghi lại scanner/database version, thời điểm scan, policy và kết quả.

### 2.3. Build metadata giúp truy ngược bản build

Metadata thường là JSON hoặc properties, gắn các thông tin:

- Repository và commit SHA đầy đủ.
- Branch/tag/ref và build run ID/URL.
- Java/JDK, Maven/Gradle Wrapper, Spring Boot và plugin versions.
- Artifact filename, size và SHA-256.
- SBOM format/schema, filename và SHA-256.
- Image reference **theo digest**, builder/base image nếu áp dụng.
- Thời điểm bắt đầu/kết thúc build và builder identity.

Metadata nên là **non-secret**. Không ghi access token, private URL có credential, environment dump, password, signing private key hoặc toàn bộ command line có secret.

### 2.4. Provenance là attestation có thể xác minh

**SLSA build provenance** mô tả output artifact, builder, build type, input parameters và resolved dependencies theo một định dạng có cấu trúc. Provenance được tạo bởi **build platform đáng tin**, gắn với digest của output và có cơ chế xác thực.

Một file build-metadata.json tự tạo rất hữu ích cho con người và pipeline, nhưng **không tự động là SLSA provenance**. Không ghi nhãn SLSA level cho file JSON tự khai báo; mức SLSA phụ thuộc security properties và quy trình của build platform.

## 3. Pipeline tổng thể và thứ tự tạo evidence

~~~text
Checkout source + record commit
           |
           v
Compile / Test / Package
           |
           +--> Spring Boot build-info (non-secret, optional)
           |
           v
Generate CycloneDX SBOM for application dependencies
           |
           v
Validate artifact + SBOM outputs
           |
           v
SHA-256 application JAR + SBOM
           |
           v
Build image (if the deliverable is an OCI image)
           |
           +--> Resolve immutable image digest
           +--> Generate image SBOM from that digest
           |
           v
Write build-metadata.json
           |
           v
Generate SHA256SUMS for final evidence files
           |
           v
Sign checksum manifest / image / attest provenance
           |
           v
Upload immutable CI artifact + retention policy
           |
           v
Consumer downloads → verifies signature → checks SHA-256 → reviews SBOM
~~~

**Tại sao checksum phải tạo sau package?** Nếu JAR còn được repackage, filter resource hoặc thay file sau khi hash, checksum đã ghi không còn mô tả artifact cuối cùng.

**Tại sao metadata được tạo sau SBOM/image?** Khi đó metadata có thể ghi digest của JAR, SBOM và image đúng với deliverables cuối. SHA256SUMS tạo cuối cùng để bao phủ cả JAR, SBOM và metadata; không đưa chính SHA256SUMS vào danh sách của nó (tránh vòng lặp).

## 4. Spring Boot build-info: metadata nhỏ bên trong JAR

Spring Boot có thể tạo META-INF/build-info.properties để ứng dụng/Actuator hiển thị build coordinates và thông tin bổ sung. Đây là **metadata nằm trong archive**; nó không thay thế file metadata bên ngoài chứa checksum/SBOM.

### 4.1. Maven build-info

Thêm execution sau vào cấu hình spring-boot-maven-plugin đang dùng:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>build-info</id>
            <goals>
                <goal>build-info</goal>
            </goals>
            <configuration>
                <additionalProperties>
                    <java.version>${java.version}</java.version>
                </additionalProperties>
                <excludeInfoProperties>
                    <excludeInfoProperty>time</excludeInfoProperty>
                </excludeInfoProperties>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đây là **mảnh plugin để hợp nhất vào POM**, không thay toàn bộ plugin configuration hiện có. Spring Boot Maven Plugin sinh file dưới target/classes/META-INF/build-info.properties để nó được đóng vào JAR.

- group, artifact, name, version mô tả tọa độ project.
- additionalProperties thêm dữ liệu không nhạy cảm như Java version.
- Loại time nếu ưu tiên reproducible build: timestamp thay đổi có thể làm nội dung JAR thay đổi dù source/dependencies không đổi.
- Nếu cần build timestamp chính xác, có thể giữ time và ghi nhận nó trong metadata; phải chấp nhận archive có thể khác giữa các lần build.

Khi Actuator được cấu hình để hiển thị build information, BuildProperties có thể được dùng trong info endpoint. **Không public endpoint build metadata nội bộ** nếu chính sách không cho phép lộ version/commit/internal references.

### 4.2. Gradle bootBuildInfo

Trong build.gradle Groovy DSL:

~~~groovy
springBoot {
    buildInfo {
        excludes = ['time']
    }
}
~~~

Spring Boot Gradle Plugin tạo task bootBuildInfo, sinh META-INF/build-info.properties để đưa vào Boot JAR. Chạy:

~~~bash
./gradlew clean test bootBuildInfo bootJar
~~~

Nếu cần thêm property, có thể dùng properties.additional với giá trị non-secret. Không đưa token, URL có credential hoặc private key vào buildInfo. Nếu build JVM khác Java toolchain dùng để compile, hãy ghi riêng **JDK build** và **Java target/toolchain** trong metadata để không gây hiểu nhầm.

### 4.3. Vì sao vẫn cần build-metadata.json?

Build-info trong JAR thường chỉ chứa tọa độ project và một số properties. Nó không nhất thiết có SHA-256 của chính JAR, SHA-256 của SBOM/image digest, CI run URL/identity, builder ID và resolved inputs đầy đủ, chữ ký và provenance có thể verify độc lập.

Do đó hãy dùng build-info cho khả năng nhận diện app tại runtime, còn **metadata ngoài archive** cho release evidence.

## 5. Maven: tạo CycloneDX SBOM cho Spring Boot

### 5.1. Cấu hình plugin

Ví dụ dưới dùng cyclonedx-maven-plugin phiên bản 2.9.1, hỗ trợ CycloneDX 1.6. Đặt plugin vào build/plugins của POM:

~~~xml
<plugin>
    <groupId>org.cyclonedx</groupId>
    <artifactId>cyclonedx-maven-plugin</artifactId>
    <version>2.9.1</version>
    <executions>
        <execution>
            <id>generate-sbom</id>
            <phase>verify</phase>
            <goals>
                <goal>makeBom</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <projectType>application</projectType>
        <schemaVersion>1.6</schemaVersion>
        <outputFormat>all</outputFormat>
        <outputName>bom</outputName>
        <includeBomSerialNumber>true</includeBomSerialNumber>
        <includeCompileScope>true</includeCompileScope>
        <includeRuntimeScope>true</includeRuntimeScope>
        <includeProvidedScope>false</includeProvidedScope>
        <includeSystemScope>false</includeSystemScope>
        <includeTestScope>false</includeTestScope>
        <includeLicenseText>false</includeLicenseText>
    </configuration>
</plugin>
~~~

Giải thích:

- makeBom tạo BOM cho module Maven hiện tại.
- projectType=application mô tả component gốc là ứng dụng.
- schemaVersion=1.6 chọn CycloneDX schema; consumer scanner phải hỗ trợ version này.
- outputFormat=all tạo cả JSON và XML.
- outputName=bom với output directory mặc định là target, nên có target/bom.json và target/bom.xml.
- includeCompileScope/includeRuntimeScope giữ các dependency liên quan đến ứng dụng; provided, system và test được bỏ khỏi ví dụ runtime-focused. Điều chỉnh scope theo cách project thực sự đóng gói và phân phối dependencies.
- BOM serial number giúp nhận diện document; nó **không phải checksum hay chữ ký**.

makeBom phù hợp khi tạo SBOM cho một module. Với Maven multi-module, dùng makeAggregateBom ở root nếu artifact phát hành đại diện cho **toàn bộ reactor**; có thể tạo thêm BOM theo từng module. Đừng gắn aggregate SBOM của cả monorepo vào một JAR con nếu nó mô tả nhiều component hơn artifact đó.

### 5.2. Chạy build và xác nhận output

Với Maven Wrapper:

~~~bash
./mvnw --batch-mode clean verify
test -s target/release-demo.jar
test -s target/bom.json
test -s target/bom.xml
~~~

Đặt finalName là release-demo trong build section nếu muốn executable JAR có đường dẫn target/release-demo.jar. Nếu không đặt, dùng đúng filename do Maven thực tế tạo; không giả định file .jar.original là Boot executable archive.

Kiểm tra JSON parse và schema declaration bằng jq:

~~~bash
jq -e '.bomFormat == "CycloneDX" and .specVersion == "1.6"' target/bom.json
~~~

Kết quả thành công là một JSON object được in ra và exit code bằng 0; nếu parse/schema declaration không đúng, job phải fail hoặc chuyển sang bước điều tra. Kiểm tra JSON syntax **không thay thế** schema validation bằng CycloneDX CLI/consumer validator.

### 5.3. SBOM scope và multi-module

Maven plugin có thể mô tả compile, provided, runtime, system, test scopes. SBOM phải phản ánh **đúng ranh giới sản phẩm**:

- Với executable Boot JAR, tập runtime dependencies thường quan trọng nhất.
- Test libraries không thuộc runtime deliverable thông thường.
- provided có thể do môi trường chạy cung cấp, nhưng vẫn nên có SBOM riêng nếu yêu cầu supply-chain cần theo dõi chúng.
- Multi-module application nên tạo aggregate SBOM cho toàn sản phẩm hoặc từng component kèm SBOM aggregate, tùy release structure.

Đừng tùy tiện loại một dependency khỏi SBOM chỉ để giảm cảnh báo; nếu component thực sự có mặt trong sản phẩm, phải giữ khả năng truy vết.

## 6. Gradle: tạo CycloneDX SBOM

### 6.1. Cấu hình plugin

Ví dụ Groovy DSL dùng org.cyclonedx.bom phiên bản 3.4.0. Plugin 3.x yêu cầu Gradle 8.4 trở lên; kiểm tra Gradle Wrapper tương thích với Spring Boot plugin đang dùng.

Trong build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
    id 'org.cyclonedx.bom' version '3.4.0'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.apache.commons:commons-lang3:3.14.0'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootJar') {
    archiveFileName = 'release-demo.jar'
}

tasks.cyclonedxDirectBom {
    projectType = 'application'
    includeConfigs = ['runtimeClasspath']
    skipConfigs = ['(?i).*test.*']
}
~~~

Đây là ví dụ build file đầy đủ cho một project demo; thêm các dependency thực tế của ứng dụng. Trong dự án thật, pin Spring Boot/Gradle/plugin versions theo release matrix của project và kiểm tra phiên bản Gradle Wrapper:

~~~bash
./gradlew --version
~~~

### 6.2. Chạy task và đường dẫn output

Với một module:

~~~bash
./gradlew clean test bootBuildInfo bootJar cyclonedxDirectBom
test -s build/libs/release-demo.jar
test -s build/reports/cyclonedx-direct/bom.json
~~~

CycloneDX Gradle plugin tạo Direct SBOM tại build/reports/cyclonedx-direct/bom.json và .xml theo default. includeConfigs=['runtimeClasspath'] chọn cấu hình runtime; skipConfigs loại test configurations theo regex khớp toàn bộ tên. includeConfigs và skipConfigs là quy tắc chọn configuration, không phải tên dependency.

Trong multi-project build:

- cyclonedxDirectBom tạo SBOM theo từng project.
- cyclonedxBom tạo Aggregate SBOM tại root từ những Direct SBOM được bật.
- Chỉ gắn aggregate BOM vào artifact phát hành nếu aggregate thực sự mô tả đúng tập subprojects tạo thành sản phẩm đó.

Nếu thay đổi cấu hình Direct SBOM cho nhiều subprojects, áp dụng quy tắc nhất quán cho từng project đóng góp vào aggregate; không mặc định một config ở root tự động áp dụng mọi thuộc tính xuống tất cả subprojects.

### 6.3. Kiểm tra schema declaration

~~~bash
jq -e '.bomFormat == "CycloneDX" and .specVersion == "1.6"' build/reports/cyclonedx-direct/bom.json
~~~

Plugin 3.x có thể chọn schema 1.7 qua cấu hình schemaVersion nếu consumer hỗ trợ. Đừng nâng schema chỉ vì có phiên bản mới; hãy kiểm tra SBOM intake service, scanner và policy engine của bên nhận trước.

## 7. SBOM cho JAR và SBOM cho OCI image không giống nhau

CycloneDX Maven/Gradle plugin mô tả dependency graph của project theo build tool. Nó hữu ích cho JAR/WAR nhưng **không tự mô tả đầy đủ mọi package trong final container image**.

| SBOM | Phạm vi | Cách tạo điển hình |
| --- | --- | --- |
| Application/project SBOM | Project coordinates và dependency graph Maven/Gradle. | CycloneDX Maven/Gradle plugin. |
| Binary/archive SBOM | Thành phần được nhận diện trong JAR/WAR/ZIP thực tế. | Archive-aware scanner, có thể kết hợp project SBOM. |
| Container image SBOM | App files, JRE, OS packages, libraries và thành phần trong OCI image. | Image scanner như Syft sau khi image đã build. |
| Build environment SBOM | Toolchain/build dependencies/builder image. | Inventory riêng cho builder/build environment nếu policy yêu cầu. |

JAR có thể khai báo Spring Web và Commons Lang; final image từ Paketo/Docker còn có Java runtime, OS libraries, CA certificates và các packages khác. Nếu chỉ upload project SBOM, consumer **không thể kết luận đã kiểm kê toàn bộ image**.

### 7.1. Tạo image SBOM bằng Syft

Sau khi image đã được publish, xác định **immutable digest** của image (không chỉ tag):

~~~bash
IMAGE_REF_DIGEST=registry.example.invalid/team/release-demo@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef

syft "$IMAGE_REF_DIGEST" \
  -o cyclonedx-json=dist/release-evidence/image-sbom.cdx.json
~~~

Địa chỉ registry.example.invalid và digest ở trên chỉ là ví dụ định dạng, không phải image có thật. Thay bằng digest được registry/build tool trả về. Nếu scanner hỗ trợ registry auth, cấp quyền pull image theo secret store, không ghi password vào command line/log.

Syft có thể xuất CycloneDX JSON/XML và các định dạng khác. Kiểm tra version scanner và format/schema trước khi gửi SBOM cho consumer. Đối với image multi-architecture, ghi rõ platform/manifest digest và bảo đảm scan đúng manifest/platform mà production sẽ chạy.

### 7.2. Tag khác digest

Tag như release-demo:1.0.0 có thể được di chuyển tới image khác. Digest sha256:... xác định nội dung manifest cụ thể. Metadata nên ghi:

~~~json
{
  "image": {
    "tag": "registry.example.invalid/team/release-demo:1.0.0",
    "digest": "sha256:...",
    "immutableReference": "registry.example.invalid/team/release-demo@sha256:..."
  }
}
~~~

Đây là cấu trúc minh họa; thay bằng giá trị thật từ registry. **Không tự lấy docker image inspect .Id rồi gọi đó là manifest digest**: image config ID và registry manifest digest là các digest khác nhau. Lấy digest từ push output, Buildx metadata hoặc registry API phù hợp.

## 8. Tạo SHA-256 manifest cho artifact và SBOM

### 8.1. Chuẩn bị một thư mục evidence

Với Maven, sau clean verify và CycloneDX generation:

~~~bash
mkdir -p dist/release-evidence
cp target/release-demo.jar dist/release-evidence/
cp target/bom.json dist/release-evidence/application-sbom.cdx.json
~~~

Với Gradle, thay hai nguồn copy bằng:

~~~bash
mkdir -p dist/release-evidence
cp build/libs/release-demo.jar dist/release-evidence/
cp build/reports/cyclonedx-direct/bom.json \
  dist/release-evidence/application-sbom.cdx.json
~~~

Nếu phân phối cả XML, copy thêm file .xml. Không copy target/, build/, .gradle/, .m2/, .env, settings credentials hoặc toàn bộ workspace vào evidence bundle.

### 8.2. Sinh manifest bằng GNU sha256sum

Chạy tại project root:

~~~bash
(
  cd dist/release-evidence
  sha256sum release-demo.jar application-sbom.cdx.json > SHA256SUMS
  sha256sum --check SHA256SUMS
)
~~~

Ví dụ output khi các file hợp lệ:

~~~text
release-demo.jar: OK
application-sbom.cdx.json: OK
~~~

Đây là output kiểm tra, không phải digest cụ thể. File SHA256SUMS chứa digest thực và relative path của hai file. Người nhận cần chạy verify **trong cùng thư mục evidence** để path khớp.

Khi đã có build-metadata.json, thêm file đó vào manifest:

~~~bash
(
  cd dist/release-evidence
  sha256sum release-demo.jar application-sbom.cdx.json build-metadata.json > SHA256SUMS
  sha256sum --check SHA256SUMS
)
~~~

Nếu có image-sbom.cdx.json, thêm tên file đó vào danh sách. Nếu ký checksum manifest, tạo chữ ký **sau khi manifest đã ổn định**; không sửa manifest sau khi ký.

### 8.3. Kiểm tra trên Windows PowerShell

PowerShell có thể tính hash:

~~~powershell
Get-FileHash .\dist\release-evidence\release-demo.jar -Algorithm SHA256
Get-FileHash .\dist\release-evidence\application-sbom.cdx.json -Algorithm SHA256
~~~

Để kiểm tra một digest mong đợi đã đọc từ manifest:

~~~powershell
$expected = "PUT_THE_EXPECTED_64_HEX_DIGEST_HERE"
$actual = (Get-FileHash .\dist\release-evidence\release-demo.jar -Algorithm SHA256).Hash.ToLowerInvariant()

if ($actual -ne $expected.ToLowerInvariant()) {
    throw "SHA-256 mismatch for release-demo.jar"
}
"SHA-256 verified"
~~~

PUT_THE_EXPECTED_64_HEX_DIGEST_HERE là giá trị checksum lấy từ manifest đáng tin cậy, không phải chuỗi được dùng như secret hoặc giá trị mặc định. Trong automation, parse dòng tương ứng của SHA256SUMS và so sánh tự động, không copy thủ công.

### 8.4. Kiểm tra sau khi download

Người nhận cần tải artifact và toàn bộ evidence từ cùng release/run; xác minh chữ ký của SHA256SUMS nếu có; chạy sha256sum --check SHA256SUMS; đảm bảo JAR/SBOM filename trong manifest đúng deliverable đang đánh giá; đọc metadata và đối chiếu commit/build ID/image digest; chỉ sau đó mới sử dụng hoặc triển khai artifact.

**Không tin checksum manifest chỉ vì nó nằm cạnh file JAR.** Nếu manifest không được ký, nó vẫn có thể bị thay cùng artifact.

## 9. Tạo build-metadata.json bên ngoài archive

### 9.1. Cấu trúc metadata đề xuất

~~~json
{
  "schemaVersion": 1,
  "source": {
    "repository": "example-org/release-demo",
    "commit": "40-hex-character-git-commit",
    "ref": "refs/tags/v1.0.0"
  },
  "build": {
    "id": "ci-run-12345",
    "url": "https://ci.example.invalid/runs/12345",
    "tool": "Maven",
    "toolVersion": "3.9.x",
    "javaVersion": "17",
    "springBootVersion": "3.3.13"
  },
  "artifacts": [
    {
      "role": "application",
      "file": "release-demo.jar",
      "sha256": "64-hex-character-digest"
    },
    {
      "role": "application-sbom",
      "format": "CycloneDX JSON",
      "specVersion": "1.6",
      "file": "application-sbom.cdx.json",
      "sha256": "64-hex-character-digest"
    }
  ],
  "image": {
    "immutableReference": "registry.example.invalid/team/release-demo@sha256:...",
    "sbomFile": "image-sbom.cdx.json"
  }
}
~~~

Các chuỗi digest/repository/run ở trên là ví dụ định dạng, không phải dữ liệu thật. Không dùng giá trị mẫu này làm metadata production. Nếu artifact không phải container image, có thể bỏ object image.

Metadata có thể thêm builder, runner, startedAt, finishedAt, workflow, dependencyLockfileHash, buildArguments (chỉ non-secret) và testSummary. Giữ schema nhỏ, có version, không đưa mọi environment variable vào JSON.

### 9.2. Sinh metadata trong Bash bằng jq

Ví dụ cho GitHub-hosted Ubuntu runner và Maven. jq tạo JSON có escaping đúng, tránh nối chuỗi thủ công:

~~~bash
set -eo pipefail

ARTIFACT=dist/release-evidence/release-demo.jar
SBOM=dist/release-evidence/application-sbom.cdx.json

ARTIFACT_SHA=$(sha256sum "$ARTIFACT" | awk '{print $1}')
SBOM_SHA=$(sha256sum "$SBOM" | awk '{print $1}')
SOURCE_COMMIT=$(git rev-parse HEAD)
SOURCE_REF=$GITHUB_REF
BUILD_ID=$GITHUB_RUN_ID
BUILD_URL=$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID
JAVA_VERSION=$(java -version 2>&1 | head -n 1)
MAVEN_VERSION=$(./mvnw -version | head -n 1)

if [ -z "$BUILD_ID" ]; then BUILD_ID=local; fi
if [ -z "$SOURCE_REF" ]; then SOURCE_REF=local; fi

jq -n \
  --arg repository "$GITHUB_REPOSITORY" \
  --arg commit "$SOURCE_COMMIT" \
  --arg ref "$SOURCE_REF" \
  --arg buildId "$BUILD_ID" \
  --arg buildUrl "$BUILD_URL" \
  --arg javaVersion "$JAVA_VERSION" \
  --arg mavenVersion "$MAVEN_VERSION" \
  --arg artifactSha "$ARTIFACT_SHA" \
  --arg sbomSha "$SBOM_SHA" \
  '{
    schemaVersion: 1,
    source: {
      repository: $repository,
      commit: $commit,
      ref: $ref
    },
    build: {
      id: $buildId,
      url: $buildUrl,
      tool: "Maven",
      toolVersion: $mavenVersion,
      javaVersion: $javaVersion,
      springBootVersion: "3.3.13"
    },
    artifacts: [
      {
        role: "application",
        file: "release-demo.jar",
        sha256: $artifactSha
      },
      {
        role: "application-sbom",
        format: "CycloneDX JSON",
        specVersion: "1.6",
        file: "application-sbom.cdx.json",
        sha256: $sbomSha
      }
    ]
  }' > dist/release-evidence/build-metadata.json

(
  cd dist/release-evidence
  sha256sum release-demo.jar application-sbom.cdx.json build-metadata.json > SHA256SUMS
  sha256sum --check SHA256SUMS
)
~~~

Đoạn trên giả định các file Maven/CI đã tồn tại và environment variables của GitHub Actions có thể đọc được. Với CI khác, thay các biến repository/ref/run URL bằng biến tương ứng của platform. Với Gradle, thay MAVEN_VERSION bằng output ./gradlew --version và sửa artifact/SBOM paths theo task output.

**Không đưa token hoặc secret vào jq --arg chỉ để ghi metadata.** Metadata chỉ chứa thông tin cần thiết để truy vết artifact.

### 9.3. Metadata bên trong và bên ngoài phải khớp

Nếu JAR có META-INF/build-info.properties, kiểm tra group/artifact/version của nó khớp build-metadata.json. Git commit có thể chỉ xuất hiện trong metadata ngoài. Nếu muốn nhúng commit vào build-info, chỉ đưa commit SHA không nhạy cảm; cân nhắc reproducibility và không nhúng branch name chứa thông tin nội bộ nếu không cần.

Nếu metadata ngoài nói JAR là version 1.0.0 nhưng archive build-info ghi 0.9.0-SNAPSHOT, **pipeline phải fail** thay vì upload một bộ evidence mâu thuẫn.

## 10. Gắn image digest và image SBOM vào evidence

Nếu CI tạo OCI image, hãy thu thập digest **sau khi image được push**. Với Docker Buildx, có thể yêu cầu file metadata:

~~~bash
IMAGE_TAG=registry.example.invalid/team/release-demo:1.0.0

docker buildx build \
  --push \
  --tag "$IMAGE_TAG" \
  --metadata-file dist/release-evidence/buildx-metadata.json \
  .

IMAGE_DIGEST=$(jq -r '."containerimage.digest"' dist/release-evidence/buildx-metadata.json)
IMAGE_REF_DIGEST=$IMAGE_TAG@$IMAGE_DIGEST
printf '%s\n' "$IMAGE_REF_DIGEST" > dist/release-evidence/image-reference.txt
~~~

containerimage.digest là digest của image manifest/build output được Buildx báo. Kiểm tra metadata file có giá trị hợp lệ và bắt đầu bằng sha256: trước khi tiếp tục. Nếu dùng Spring Boot build-image/bootBuildImage hoặc một CI builder khác, lấy digest từ output/registry tương ứng thay vì giả định Buildx metadata tồn tại.

Tạo SBOM cho đúng image digest:

~~~bash
syft "$IMAGE_REF_DIGEST" \
  -o cyclonedx-json=dist/release-evidence/image-sbom.cdx.json
~~~

Sau đó tính checksum cho image SBOM và cập nhật build-metadata.json để có image.immutableReference, image.digest và image.sbomFile. **Tạo lại SHA256SUMS sau lần cập nhật cuối cùng**:

~~~bash
(
  cd dist/release-evidence
  sha256sum release-demo.jar application-sbom.cdx.json \
    image-sbom.cdx.json build-metadata.json image-reference.txt > SHA256SUMS
  sha256sum --check SHA256SUMS
)
~~~

buildx-metadata.json có thể được giữ như raw build output nếu cần audit, nhưng kiểm tra nội dung trước khi upload. Không đưa secret, credential hoặc toàn bộ builder environment vào metadata file.

## 11. Ký checksum và xác minh chữ ký

### 11.1. Vì sao cần ký manifest?

SHA-256 phát hiện thay đổi so với manifest. Chữ ký giúp người nhận xác minh **manifest được tạo bởi identity được tin cậy**. Với keyless signing, CI lấy danh tính ngắn hạn qua OIDC; không cần commit private signing key vào repository.

Dùng Cosign/Sigstore cho checksum manifest:

~~~bash
cosign sign-blob --yes \
  --bundle dist/release-evidence/SHA256SUMS.sigstore.json \
  dist/release-evidence/SHA256SUMS
~~~

Bundle chứa signature/certificate/transparency-log evidence theo Sigstore workflow. Lưu bundle cùng SHA256SUMS; bundle không được đưa vào chính checksum manifest vừa ký (tránh vòng lặp). Nếu dùng key-managed/KMS signing, tuân thủ key custody và rotation policy của tổ chức.

### 11.2. Verify trước khi sử dụng artifact

Người nhận phải biết **expected signer identity** và OIDC issuer qua policy đáng tin, không lấy identity từ chính file đang kiểm tra:

~~~bash
cosign verify-blob dist/release-evidence/SHA256SUMS \
  --bundle dist/release-evidence/SHA256SUMS.sigstore.json \
  --certificate-identity "$EXPECTED_SIGNER_IDENTITY" \
  --certificate-oidc-issuer "$EXPECTED_OIDC_ISSUER"

(
  cd dist/release-evidence
  sha256sum --check SHA256SUMS
)
~~~

Verify chữ ký thành công chỉ xác nhận chữ ký/identity/bundle theo trust options được cung cấp. Consumer vẫn phải kiểm tra signer đó có quyền tạo release cho project/repository/branch hay không. Sau đó mới xác minh từng file bằng manifest.

### 11.3. Ký container image theo digest

Nếu sản phẩm là OCI image, ký immutable reference:

~~~bash
cosign sign --yes "$IMAGE_REF_DIGEST"
~~~

Verify với identity/issuer đã được phê duyệt:

~~~bash
cosign verify "$IMAGE_REF_DIGEST" \
  --certificate-identity "$EXPECTED_SIGNER_IDENTITY" \
  --certificate-oidc-issuer "$EXPECTED_OIDC_ISSUER"
~~~

Không ký tag mutable rồi coi tag đó là identity cố định; dùng digest để ràng buộc chữ ký với image contents cụ thể. Đối với SBOM/provenance, dùng attestation workflow theo policy; Cosign hỗ trợ attestations gắn với image. Chữ ký image **không tự xác nhận SBOM đầy đủ**; cần kiểm tra predicate và digest/subject được attestation tham chiếu.

## 12. Build provenance và SLSA

Một bộ release evidence tốt có thể chứa build-metadata.json (metadata do pipeline tạo, dễ đọc cho con người), SHA256SUMS (checksum của các file evidence), SHA256SUMS.sigstore.json (chữ ký của manifest), provenance.intoto.jsonl (provenance/attestation từ build platform đáng tin) và SBOM (inventory dependencies/image).

SLSA provenance thường mô tả:

- **Subject:** artifact output được định danh bằng cryptographic digest.
- **Build definition/type:** quy trình build được dùng.
- **External parameters:** input/parameters do caller truyền vào.
- **Resolved dependencies:** source commit và dependencies/build inputs đã resolve, khi nền tảng biết.
- **Builder identity:** build platform chịu trách nhiệm thực thi và ghi provenance.
- **Run details:** invocation ID, thời gian và thông tin build run.

**Không tự viết một JSON tùy ý rồi gắn nhãn SLSA L2/L3.** Build level phụ thuộc trust boundary, cách provenance được tạo/giữ toàn vẹn và isolation của build platform. Hãy bật provenance generation/attestation native từ CI platform được tổ chức tin cậy, rồi kiểm tra nó gắn với **đúng digest**.

### 12.1. SBOM và provenance có quan hệ nhưng không thay thế nhau

- SBOM trả lời: “thành phần nào được khai báo/phát hiện trong sản phẩm?”
- Provenance trả lời: “artifact này được tạo bởi builder nào, từ inputs nào, theo quy trình nào?”
- Checksum trả lời: “bytes hiện tại có khớp digest không?”
- Signature trả lời: “identity được tin cậy có ký digest/manifest này không?”

Một SBOM có thể được tạo sau build bằng scanner; provenance cần phản ánh quy trình thực tế và được build platform xác thực. Một signature không chứng minh nội dung SBOM đúng nếu scanner/attestation process không đáng tin.

## 13. GitHub Actions: upload bộ evidence vào kết quả CI

Ví dụ dưới minh họa Maven build, upload evidence và đặt retention. Nó giả định các bước trước đã tạo JAR, target/bom.json, build-metadata.json, SHA256SUMS và signature bundle nếu đã ký.

~~~yaml
name: Spring Boot release evidence

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: read
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Build, test and generate SBOM
        run: ./mvnw --batch-mode clean verify

      - name: Verify expected outputs
        run: |
          test -s target/release-demo.jar
          test -s target/bom.json
          test -s target/bom.xml
          jq -e '.bomFormat == "CycloneDX" and .specVersion == "1.6"' target/bom.json

      - name: Assemble release evidence
        run: |
          mkdir -p dist/release-evidence
          cp target/release-demo.jar dist/release-evidence/
          cp target/bom.json dist/release-evidence/application-sbom.cdx.json
          # Tạo build-metadata.json và SHA256SUMS theo mục 9.

      - name: Upload evidence
        uses: actions/upload-artifact@v7
        with:
          name: spring-boot-release-evidence-${{ github.run_id }}
          path: |
            dist/release-evidence/
          if-no-files-found: error
          retention-days: 30
~~~

Đây là **fragment workflow** để ghép vào pipeline thực tế; step Assemble release evidence phải chạy đầy đủ script tạo metadata/checksum, và nếu policy yêu cầu thì ký manifest/provenance trước khi upload. Không để comment placeholder ở pipeline release cuối.

GitHub Actions upload-artifact hỗ trợ tên artifact, paths, if-no-files-found và retention-days. Retention thực tế còn bị giới hạn bởi repository/organization/enterprise policy. Với GitHub Enterprise Server, kiểm tra action version tương thích với phiên bản GHES; không mặc định mọi version mới đều hỗ trợ GHES.

### 13.1. Giữ artifact theo run và release

- Dùng tên duy nhất theo run ID/version/commit để không ghi đè nhầm kết quả build khác.
- if-no-files-found: error giúp pipeline fail khi thiếu JAR/SBOM.
- Chọn retention theo chính sách; 30 ngày trong ví dụ không phải yêu cầu phổ quát.
- Không bật include-hidden-files: true nếu không có nhu cầu đã kiểm tra, vì hidden files có thể chứa .env/settings.
- Với release cần lưu lâu dài, publish evidence vào artifact repository/release storage có retention và access control phù hợp; CI run artifact có thể tự hết hạn.
- Giữ JAR, SBOM, metadata, checksum, signature và provenance trong cùng release namespace hoặc liên kết bằng digest.

### 13.2. GitLab CI tương đương

GitLab có thể giữ cùng bộ file bằng artifacts:

~~~yaml
build:
  stage: build
  script:
    - ./mvnw --batch-mode clean verify
    - test -s target/release-demo.jar
    - test -s target/bom.json
  artifacts:
    when: always
    name: "spring-boot-evidence-$CI_PIPELINE_ID"
    paths:
      - target/release-demo.jar
      - target/bom.json
      - dist/release-evidence/
    expire_in: 30 days
~~~

Đây là cấu hình minh họa; tạo metadata/checksum/signature trước khi artifact upload và dùng secret/OIDC integration theo GitLab instance thực tế. when: always hữu ích để giữ logs/reports khi job fail, nhưng **không** được coi evidence chưa đạt QA là release được phép phát hành. Tách diagnostic artifacts khỏi release artifacts nếu pipeline có failure.

## 14. Kiểm tra evidence trước khi upload

### 14.1. Artifact tồn tại và đúng loại

Maven:

~~~bash
test -s target/release-demo.jar
file target/release-demo.jar
jar tf target/release-demo.jar
~~~

Gradle:

~~~bash
test -s build/libs/release-demo.jar
file build/libs/release-demo.jar
jar tf build/libs/release-demo.jar
~~~

Kiểm tra executable JAR thực sự chứa BOOT-INF/classes, BOOT-INF/lib, manifest/Boot loader. Nếu build tạo *-plain.jar, không chọn nhầm plain archive. Nếu là WAR, kiểm tra đúng layout WEB-INF/.

### 14.2. SBOM parse và scope

- Parse JSON/XML thành công.
- bomFormat là CycloneDX, specVersion đúng version mong đợi.
- metadata.component đúng project/artifact/version.
- Component count/dependency graph hợp lý với dependency report.
- Test-only dependencies không lọt vào runtime SBOM nếu policy không yêu cầu.
- Multi-module aggregate chỉ bao gồm project thực sự đóng góp vào release.
- Không có thông tin secret trong component properties/external references.
- Lưu tool/plugin version đã tạo SBOM.

### 14.3. Hash và file mapping

- Tên file trong SHA256SUMS trỏ tới file thực tế.
- Hash được tính sau khi JAR/SBOM đã hoàn tất.
- sha256sum --check pass trên chính thư mục evidence sẽ upload.
- Nếu metadata có digest, nó khớp digest trong manifest.
- Nếu có image, image reference là digest, không chỉ tag.
- Nếu có chữ ký, verify được bằng identity/issuer trong trust policy.

### 14.4. Không lộ secret trong evidence

Không upload .m2/settings.xml, gradle.properties có credential, .env, keystore, private key, token, Docker auth config hoặc toàn bộ workspace vào evidence bundle. SBOM/metadata có thể tiết lộ dependency/private package names và repository/source URLs; đặt access control phù hợp.

## 15. Kiểm tra và tái sử dụng evidence ở downstream pipeline

Một deployment job hoặc release consumer có thể thực hiện:

~~~bash
# 1. Xác minh chữ ký manifest theo identity được trust policy cho phép.
cosign verify-blob dist/release-evidence/SHA256SUMS \
  --bundle dist/release-evidence/SHA256SUMS.sigstore.json \
  --certificate-identity "$EXPECTED_SIGNER_IDENTITY" \
  --certificate-oidc-issuer "$EXPECTED_OIDC_ISSUER"

# 2. Xác minh bytes của mọi file đã kê khai.
(
  cd dist/release-evidence
  sha256sum --check SHA256SUMS
)

# 3. Kiểm tra SBOM JSON và metadata.
jq -e '.bomFormat == "CycloneDX"' \
  dist/release-evidence/application-sbom.cdx.json
jq -e '.schemaVersion == 1 and .source.commit != ""' \
  dist/release-evidence/build-metadata.json
~~~

Nếu chưa ký manifest, bỏ bước chữ ký nhưng phải hiểu rằng checksum không tự xác thực nguồn gốc. Production release policy nên yêu cầu chữ ký/attestation và chỉ chấp nhận signer/builder identity đã được allowlist.

Downstream có thể dùng SBOM để quét CVE bằng scanner có vulnerability database cập nhật, so sánh dependency với denylist/license policy, tìm artifact bị ảnh hưởng khi CVE mới xuất hiện, kiểm tra dependency version được phê duyệt và lưu inventory cho audit/release compliance.

**Kết quả scanner cũng phải được gắn với đúng SBOM/artifact digest.** Ghi scanner name/version, database timestamp, policy ID và thời điểm scan; không gộp một scan của commit khác vào release hiện tại.

## 16. Những lỗi phổ biến

| Hiện tượng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| target/bom.json không tồn tại. | Plugin execution không chạy, goal/phase sai hoặc build fail trước verify. | Kiểm tra CycloneDX plugin, execution phase và log; fail pipeline nếu output bắt buộc. |
| SBOM chỉ có dependencies trực tiếp. | Resolution/configuration scope hoặc aggregate/module selection chưa đúng. | Kiểm tra plugin config, resolved dependency graph và direct/aggregate goal. |
| SBOM có test libraries trong runtime list. | Plugin đang scan test configuration/scope. | Chọn runtimeClasspath hoặc includeTestScope=false phù hợp với artifact boundary. |
| Aggregate SBOM chứa cả project không phát hành. | Dùng toàn reactor/monorepo thay vì component boundary. | Dùng Direct SBOM hoặc giới hạn projects tham gia aggregate theo release. |
| SBOM không liệt kê OS/JRE packages. | Đang dùng project dependency SBOM, không phải image SBOM. | Scan image digest bằng image-aware tool như Syft. |
| Checksum đổi sau khi build. | JAR/SBOM bị sửa, repackage sau hash, build-info time hoặc file path trỏ artifact khác. | Hash sau bước cuối cùng; so artifact identity và build inputs. |
| sha256sum --check báo FAILED. | File thay đổi, download sai, manifest path sai hoặc archive bị lỗi. | Dừng publish/deploy; tải lại từ nguồn đáng tin và điều tra. |
| Checksum pass nhưng artifact không đáng tin. | Manifest và file có thể bị thay cùng nhau. | Verify chữ ký/attestation và signer identity; checksum riêng không đủ. |
| Metadata ghi commit khác artifact. | Build workspace bẩn hoặc checkout/ref thay trong pipeline. | Checkout commit cố định, record git rev-parse HEAD trong cùng job, không lấy branch name làm commit identity. |
| Metadata JSON invalid. | Ghép chuỗi thủ công làm hỏng escaping hoặc newline. | Dùng jq/JSON serializer và parse lại trước upload. |
| Build-info time làm JAR thay đổi mỗi lần. | Timestamp được nhúng trong archive. | Exclude time nếu cần reproducibility hoặc ghi rõ policy build-time. |
| Image SBOM khác image được deploy. | Scan tag mutable hoặc scan image local khác digest đã push. | Scan immutable image@sha256:... và ghi digest vào metadata. |
| CI upload thiếu SBOM. | Glob/path sai hoặc step upload chạy trước generation. | Dùng explicit paths và if-no-files-found: error. |
| Artifact CI hết hạn trước audit. | Retention ngắn hơn yêu cầu release/compliance. | Publish evidence vào long-term artifact repository với retention/access policy. |
| Cosign verify fail. | Signer identity/issuer không khớp, bundle thiếu hoặc OIDC trust policy sai. | Xác minh expected identity/issuer và sign step; không bỏ verify để pipeline pass. |
| SBOM được ký nhưng không gắn đúng JAR. | Attestation không ràng buộc subject digest hoặc file SBOM bị thay. | Attest đúng artifact digest, hash SBOM và verify subject/predicate. |
| Provenance JSON tự tạo bị gắn nhãn SLSA level. | Nhầm metadata với provenance do builder tạo. | Dùng native trusted build platform provenance; không tự tuyên bố level. |
| Evidence bundle chứa .env hoặc credentials. | Upload cả workspace/hidden files. | Chỉ upload allowlist evidence paths; secret scan và kiểm tra file list trước upload. |
| Checksum manifest không bao gồm metadata cuối cùng. | Metadata được sửa sau khi tạo SHA256SUMS. | Sinh metadata xong rồi tạo manifest; nếu metadata đổi, tạo lại manifest và chữ ký. |
| Manifest tự hash chính nó. | Cố đưa SHA256SUMS vào danh sách của nó. | Không đưa manifest vào chính manifest; ký file manifest riêng. |

## 17. Reproducibility, retention và bảo mật evidence

### 17.1. Build reproducibility

Checksum cho biết bytes có khớp hay không; reproducible build giúp cùng source/inputs tạo output giống nhau. Muốn tăng khả năng tái lập:

- Pin JDK/toolchain, Maven/Gradle Wrapper và plugin versions.
- Khóa dependency versions và kiểm tra dependency integrity.
- Ghi builder/run image digest nếu dùng CNB/container build.
- Dùng archive timestamps/order reproducible settings khi plugin hỗ trợ.
- Exclude build timestamp khỏi embedded build-info nếu policy ưu tiên deterministic output.
- Ghi rõ compiler flags, profile và non-secret build parameters.
- Không dùng dynamic dependency versions cho release nếu cần reproducibility.

Không tuyên bố reproducible chỉ vì hai file có cùng version; phải build lại từ cùng source/inputs trong môi trường kiểm soát và so digest.

### 17.2. Retention và access control

Evidence thường tiết lộ dependency inventory, internal component names, source refs, build URLs và image references. Vì vậy:

- Đặt access control cho CI artifacts và release storage.
- Chọn retention theo audit/compliance/release lifecycle.
- Không để evidence chứa credential hoặc private key.
- Lưu signature/provenance lâu ít nhất tương ứng với artifact mà chúng xác minh.
- Giữ mapping giữa artifact version, digest, SBOM serial number, build run và deployment.
- Khi xóa artifact do retention, tuân thủ policy; không xóa evidence đang cần cho incident/audit.

### 17.3. SBOM không thay vulnerability scan

SBOM có thể giúp scanner biết thành phần nào cần kiểm tra. Nhưng tình trạng CVE thay đổi theo thời gian; cùng một SBOM có thể có kết quả khác nhau khi vulnerability database được cập nhật. Lưu scan timestamp, scanner/database version và policy để người audit hiểu kết quả được tạo khi nào.

### 17.4. Không để metadata làm lộ secrets

Tránh toàn bộ env/system properties, mvn -X, gradle --debug, registry access token, Maven password, Git deploy token, cloud credentials, absolute workspace paths không cần thiết và raw image build logs có command args nhạy cảm.

Metadata nên dùng commit SHA, build run URL đã được access control, tool versions, artifact digests và builder identity. Không cần ghi mọi biến môi trường để tái lập build.

## 18. Bài thực hành và tiêu chí đạt

### Bài A — Maven application SBOM

1. Tạo Spring Boot Maven project Java 17, artifactId release-demo, version 1.0.0, executable JAR có target/release-demo.jar.
2. Thêm CycloneDX Maven Plugin 2.9.1 với makeBom, schema 1.6 và scope runtime phù hợp.
3. Chạy ./mvnw clean verify.
4. Xác nhận JAR, target/bom.json và target/bom.xml tồn tại.
5. Kiểm tra JSON parse/schema declaration và so dependencies với ./mvnw dependency:tree.
6. Nếu multi-module, tạo aggregate SBOM chỉ khi nó mô tả đúng sản phẩm phát hành.

### Bài B — Gradle application SBOM

1. Tạo cùng source app bằng Gradle Wrapper tương thích plugin CycloneDX 3.4.0 (Gradle 8.4+).
2. Cấu hình cyclonedxDirectBom cho runtimeClasspath và loại test configs.
3. Chạy ./gradlew clean test bootBuildInfo bootJar cyclonedxDirectBom.
4. Xác nhận build/libs/release-demo.jar và build/reports/cyclonedx-direct/bom.json.
5. Nếu multi-project, so Direct SBOM từng module và Aggregate SBOM của sản phẩm.

### Bài C — checksum và verify

1. Copy JAR và SBOM vào dist/release-evidence.
2. Tạo SHA256SUMS bằng SHA-256.
3. Chạy sha256sum --check.
4. Tạo một bản copy test, sửa một byte bằng công cụ kiểm thử; xác nhận verify fail. Chỉ làm trên bản copy, không sửa release artifact gốc.
5. Ký manifest bằng Cosign keyless nếu CI có OIDC và policy cho phép.
6. Verify signature với expected signer identity/issuer, rồi verify hashes.

### Bài D — metadata và image SBOM

1. Tạo build-metadata.json có commit, ref, build ID/URL, Java/Maven/Gradle versions, artifact path/digest và SBOM path/digest.
2. Nếu build container, push image và lấy manifest digest thật.
3. Chạy Syft trên image@sha256:... để tạo image-sbom.cdx.json.
4. Cập nhật metadata với immutable image reference và image SBOM digest.
5. Tạo lại SHA256SUMS sau mọi cập nhật cuối.
6. Xác minh metadata không có token/password và digest trỏ đúng deliverable.

### Bài E — CI upload và downstream verify

1. Tạo CI job chạy test/package/SBOM trước khi upload.
2. Kiểm tra mọi file bắt buộc tồn tại; thiếu file thì job fail.
3. Upload release-evidence/ bằng GitHub Actions artifact hoặc cơ chế tương đương, đặt retention/access phù hợp.
4. Download artifact trong job downstream, verify signature và sha256sum --check.
5. Kiểm tra metadata commit/run trùng source build; xác nhận SBOM đúng schema và artifact.
6. Nếu dùng provenance, verify attestation theo builder/signer identity allowlist.

### Checklist hoàn thành

- [ ] Hiểu checksum, SBOM, build metadata và provenance khác nhau.
- [ ] Có executable JAR/WAR đúng version và đúng filename.
- [ ] Có CycloneDX SBOM JSON/XML từ Maven hoặc Gradle dependency graph.
- [ ] Chọn đúng scope/configurations và phân biệt Direct với Aggregate SBOM.
- [ ] Có SBOM riêng cho OCI image nếu container image là deliverable.
- [ ] Có SHA-256 manifest bao phủ JAR, SBOM và metadata.
- [ ] Verify checksum sau khi tải/download artifact.
- [ ] Biết checksum không chứng minh authenticity nếu manifest không được ký.
- [ ] Có build-info.properties non-secret khi cần hiển thị build version trong app.
- [ ] Có build-metadata.json ghi source commit, run ID/URL, toolchain và artifact digests.
- [ ] Image được định danh bằng immutable manifest digest.
- [ ] Chữ ký Cosign/Sigstore được verify bằng expected signer identity và issuer.
- [ ] SLSA provenance đến từ build platform đáng tin, không phải JSON tự gắn nhãn.
- [ ] CI upload đúng allowlist files, if-no-files-found: error và retention policy.
- [ ] Không upload settings, .env, credentials, private key hoặc raw secret logs.
- [ ] Downstream pipeline verify signature, checksum, metadata và SBOM trước khi deploy.

**Tiêu chí đạt:** một CI run tạo ra executable JAR, application SBOM, build-metadata.json và SHA256SUMS; người khác có thể tải bộ evidence, xác minh chữ ký (nếu được bật), chạy checksum verification và đối chiếu commit/build ID. Nếu release là container image, phải có immutable image digest và image SBOM scan từ chính digest đó. Nếu chưa có registry/attestation platform, ghi rõ phần chưa kiểm chứng; không tuyên bố SLSA level hoặc image SBOM pass chỉ từ project dependency report.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Maven Plugin: Build Info](https://docs.spring.io/spring-boot/3.3/maven-plugin/build-info.html)
- [Spring Boot 3.3 — Gradle Plugin: Integrating with Actuator](https://docs.spring.io/spring-boot/3.3/gradle-plugin/integrating-with-actuator.html)
- [CycloneDX Maven Plugin — Usage and Goals](https://github.com/CycloneDX/cyclonedx-maven-plugin)
- [CycloneDX Gradle Plugin — Configuration and Output](https://github.com/CycloneDX/cyclonedx-gradle-plugin)
- [CycloneDX Specification](https://cyclonedx.org/specification/overview/)
- [SLSA v1.2 — Build Provenance](https://slsa.dev/spec/v1.2/build-provenance)
- [Sigstore — Cosign Quickstart](https://docs.sigstore.dev/quickstart/quickstart-cosign/)
- [Sigstore — Signing Other Types, including SBOMs](https://docs.sigstore.dev/cosign/signing/other_types/)
- [Sigstore — Signing and Verifying Blobs](https://docs.sigstore.dev/cosign/signing/signing_with_blobs/)
- [Syft — Output Formats](https://github.com/anchore/syft/wiki/output-formats)
- [GitHub Actions — upload-artifact](https://github.com/actions/upload-artifact)
- [GitHub Docs — Artifact and Log Retention](https://docs.github.com/en/actions/using-workflows/storing-workflow-data-as-artifacts)

**Ghi nhớ:** checksum xác minh bytes; SBOM mô tả thành phần; metadata truy vết build; provenance và chữ ký xác thực nguồn gốc theo trust policy. Hãy gắn tất cả với **đúng artifact digest**, tạo manifest sau bước build cuối cùng, upload cùng một release evidence bundle và yêu cầu downstream verify trước khi triển khai.