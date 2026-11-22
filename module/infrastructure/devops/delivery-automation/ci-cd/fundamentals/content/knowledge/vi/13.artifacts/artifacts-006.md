# Lưu thông tin commit, lần build và phụ thuộc liên quan

Khi một file JAR được triển khai lên production, chỉ nhìn tên file và số phiên bản thường chưa đủ để trả lời những câu hỏi quan trọng: Artifact này được tạo từ commit nào? Pipeline nào đã build nó? Lần build chạy bằng JDK và build tool nào? Dependency nào đã được đưa vào? Có phải đúng artifact đã được kiểm thử trên staging đang chạy ở production không?

Thông tin trả lời các câu hỏi đó tạo nên **khả năng truy vết artifact** (artifact traceability). Mỗi artifact cần được liên kết với mã nguồn, lần build, công cụ và dependency đã tạo ra nó. Khi có sự cố bảo mật hoặc lỗi sau phát hành, nhóm có thể đi từ artifact đang chạy về commit và build run tương ứng, sau đó xác định những thành phần nào cần điều tra.

Một tên file như **service-2.4.0.jar** chỉ là nhãn. Nó không chứng minh nội dung bên trong được tạo từ tag **v2.4.0**, không xác nhận build đã thành công và cũng không cho biết dependency thực tế. Muốn có bằng chứng đáng tin cậy, cần lưu metadata có cấu trúc, checksum của artifact, danh sách dependency và thông tin provenance gắn với đúng đầu ra.

## 1. Phân biệt phiên bản, commit, build run và artifact

Các định danh này liên quan với nhau nhưng không thay thế được cho nhau:

| Định danh | Mô tả | Ví dụ |
|---|---|---|
| Product version | Phiên bản sản phẩm mà nhóm công bố | 2.4.0 |
| Git commit | Trạng thái mã nguồn được checkout | a1b2c3d4... |
| Git ref | Nhánh hoặc tag kích hoạt build | refs/tags/v2.4.0 |
| Build run ID | Một lần thực thi pipeline cụ thể | run-18452 |
| Build attempt | Lần thử trong cùng run nếu có retry | attempt-2 |
| Artifact name | Tên đầu ra được lưu trữ | service-2.4.0.jar |
| Artifact digest | Dấu vân tay nội dung của file | sha256:... |
| SBOM | Danh sách thành phần phần mềm trong artifact | service-2.4.0.cdx.json |

Một commit có thể được build nhiều lần. Ví dụ, lần đầu build thất bại do runner mất kết nối; lần thứ hai chạy lại thành công. Cả hai run có cùng commit nhưng khác build ID, thời điểm, môi trường và có thể khác artifact digest nếu build không tái lập.

Ngược lại, một build run có thể tạo nhiều artifact: JAR, file kiểm thử, image container, SBOM, báo cáo và gói triển khai. Mỗi artifact cần có định danh và digest riêng. Không nên giả định một build ID duy nhất cũng là checksum của mọi đầu ra.

### Một chuỗi truy vết hoàn chỉnh

~~~text
Git repository
    |
    v
Commit SHA + Git ref
    |
    v
CI workflow + build run ID
    |
    +---- Build tool / JDK / runner image
    |
    +---- Lockfiles / resolved dependencies
    |
    v
Artifact + SHA-256 digest
    |
    +---- SBOM
    |
    +---- Build provenance / attestation
    |
    v
Artifact repository
    |
    v
Staging ---- verify digest ----> Production
~~~

Khi một phiên bản gặp sự cố, nhóm có thể truy ngược từ digest của artifact đang triển khai đến provenance, build run, commit và dependency graph đã sử dụng.

## 2. Thông tin nguồn mã cần lưu

Mỗi lần build nên ghi lại thông tin đủ để xác định chính xác trạng thái mã nguồn:

- Repository hoặc project định danh duy nhất.
- Commit SHA đầy đủ, không chỉ vài ký tự đầu.
- Git ref: branch, tag hoặc ref của pull request.
- Commit của nhánh đích hoặc merge result nếu build kiểm tra pull request.
- Trạng thái working tree tại thời điểm build.
- Submodule revision nếu repository sử dụng Git submodules.
- Revision của file pipeline hoặc build configuration khi có thể xác định.

Commit SHA là định danh cốt lõi, nhưng chưa đủ nếu build lấy thêm nội dung bên ngoài repository. Ví dụ, pipeline có thể tải script từ một URL không pin phiên bản, đọc file cấu hình trên runner hoặc dùng generated source được tạo từ dịch vụ bên ngoài. Những đầu vào đó cũng cần được ghi nhận hoặc kiểm soát.

### Build từ trạng thái sạch

Pipeline phát hành nên checkout đúng commit và xác minh working tree không có thay đổi ngoài dự kiến. Nếu build từ workspace đã tồn tại, file cũ hoặc generated source chưa được dọn có thể ảnh hưởng artifact mà commit SHA không phản ánh.

Với Git, có thể ghi nhận commit và trạng thái working tree:

~~~bash
git rev-parse HEAD
git status --porcelain
git submodule status --recursive
~~~

Nếu git status --porcelain có đầu ra trong một build được kỳ vọng là sạch, cần điều tra file thay đổi. Một số pipeline cố ý tạo file version hoặc generated source trước khi đóng gói; khi đó cần xác định rõ file nào là đầu vào được tạo trong build và lưu cách tạo ra chúng.

### Phân biệt head commit và merge result

Với pull request, CI có thể kiểm tra commit cuối của nhánh nguồn hoặc một commit merge tạm thời giữa nhánh nguồn và nhánh đích. Hai trạng thái này không nhất thiết giống nhau. Nếu artifact được tạo từ merge result, metadata phải lưu đúng SHA đó và thông tin head/base liên quan. Nếu chỉ lưu head SHA trong khi build thực tế dùng merge result, việc truy vết sẽ không mô tả chính xác đầu vào.

### Không nhầm commit time với build time

Commit timestamp do Git ghi nhận thời điểm commit được tạo. Build timestamp là thời điểm pipeline thực hiện build. Hai mốc có thể cách nhau nhiều giờ hoặc nhiều ngày. Hãy lưu riêng thời điểm bắt đầu và kết thúc build theo UTC, dùng định dạng có múi giờ rõ ràng.

## 3. Thông tin lần build cần lưu

Build run là cầu nối giữa source code và artifact. Một bản ghi build nên có:

| Nhóm | Trường dữ liệu gợi ý | Mục đích |
|---|---|---|
| Nhận diện | Build ID, run attempt, workflow name | Phân biệt các lần chạy |
| Nguồn | Repository, commit SHA, ref, merge SHA | Xác định mã nguồn đầu vào |
| Thời gian | Started at, completed at, timezone | Điều tra thứ tự và thời lượng |
| CI | Provider, workflow URL, job IDs | Mở đúng log và bằng chứng |
| Toolchain | JDK, Gradle/Maven, compiler và plugin | Tái tạo môi trường build |
| Runner | OS, architecture, container image digest | Xác định môi trường thực thi |
| Cấu hình | Build parameters, profile, feature options | Hiểu cách artifact được tạo |
| Kết quả | Status, artifact names và digests | Liên kết đầu ra với lần build |
| Bảo mật | Builder identity, provenance signature | Xác minh nguồn tạo |

Không cần nhúng mọi trường vào manifest bên trong JAR. Có thể lưu một phần metadata trong artifact, phần chi tiết trong file build-info hoặc provenance riêng và phần log trong hệ thống CI. Điều quan trọng là các bản ghi có định danh liên kết được với nhau và được giữ đủ lâu để hỗ trợ vòng đời phát hành.

### Build ID khác product version

Product version thường mang ý nghĩa đối với người dùng hoặc quy trình phát hành, ví dụ 2.4.0. Build ID nhận diện một lần thực thi, ví dụ 18452. Nếu build lại cùng phiên bản sau khi sửa pipeline, hai run vẫn cần hai build ID khác nhau.

Không nên ghi đè artifact của một phiên bản đã phát hành bằng nội dung khác mà vẫn giữ nguyên định danh và đường dẫn. Nếu cần build lại, tạo một build record mới, lưu digest mới và xử lý theo chính sách phát hành. Điều này tránh việc một tag hoặc tên file trỏ đến các nội dung khác nhau theo thời gian.

## 4. Gắn metadata cơ bản vào artifact Java

Với JAR, một số thông tin có thể được đưa vào META-INF/MANIFEST.MF, chẳng hạn version, commit revision và build ID. Điều này hữu ích khi kỹ sư chỉ có file JAR và cần xác định nguồn tạo ban đầu.

### Ví dụ với Gradle Kotlin DSL

Trong build.gradle.kts:

~~~kotlin
tasks.jar {
    manifest {
        attributes(
            mapOf(
                "Implementation-Title" to project.name,
                "Implementation-Version" to project.version.toString(),
                "SCM-Revision" to providers.environmentVariable("GITHUB_SHA")
                    .orElse("unknown").get(),
                "Build-Run-Id" to providers.environmentVariable("GITHUB_RUN_ID")
                    .orElse("local").get()
            )
        )
    }
}
~~~

Ví dụ dùng biến môi trường của GitHub Actions. Với nền tảng CI khác, ánh xạ biến tương ứng của hệ thống đó. Build local không có biến CI sẽ nhận giá trị dự phòng; không nên dùng giá trị unknown cho artifact phát hành nếu chính sách yêu cầu truy vết đầy đủ.

### Ví dụ với Maven

Có thể cấu hình Maven JAR Plugin để thêm manifest entry trong pom.xml:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-jar-plugin</artifactId>
      <version>3.4.2</version>
      <configuration>
        <archive>
          <manifestEntries>
            <Implementation-Title>order-service</Implementation-Title>
            <Implementation-Version>2.4.0</Implementation-Version>
            <SCM-Revision>a1b2c3d4e5f6789012345678901234567890abcd</SCM-Revision>
            <Build-Run-Id>18452</Build-Run-Id>
          </manifestEntries>
        </archive>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Các giá trị trong ví dụ là minh họa. Trong CI, nên truyền commit và build ID từ biến môi trường hoặc tham số build được kiểm soát. Tránh sửa pom.xml mỗi lần build chỉ để ghi một giá trị mới.

### Metadata trong manifest có giới hạn

Manifest là nơi phù hợp cho một số thông tin ngắn, dễ đọc. Nó không phải kho provenance đầy đủ và không chứng minh metadata không bị sửa. Nếu cần xác minh tính toàn vẹn, phải tính digest của artifact và lưu metadata/provenance có chữ ký hoặc cơ chế xác thực riêng.

Việc nhúng build timestamp hoặc build ID vào JAR có thể làm hai build từ cùng commit tạo ra byte khác nhau. Nếu mục tiêu là reproducible build, cần cân nhắc đưa thông tin thay đổi theo từng lần chạy ra file metadata bên ngoài artifact, hoặc chuẩn hóa các trường thời gian và đầu vào theo chính sách.

## 5. Lưu build-info riêng có cấu trúc

Một file JSON hoặc properties đi kèm artifact có thể lưu các trường chi tiết hơn manifest. Ví dụ build-info.json:

~~~json
{
  "schemaVersion": 1,
  "artifact": {
    "name": "order-service-2.4.0.jar",
    "version": "2.4.0",
    "sha256": "REPLACE_WITH_COMPUTED_DIGEST"
  },
  "source": {
    "repository": "https://example.org/platform/order-service",
    "commit": "a1b2c3d4e5f6789012345678901234567890abcd",
    "ref": "refs/tags/v2.4.0",
    "dirty": false
  },
  "build": {
    "id": "18452",
    "attempt": 1,
    "provider": "github-actions",
    "startedAt": "2026-11-18T08:00:00Z",
    "completedAt": "2026-11-18T08:04:32Z",
    "jdk": "17",
    "buildTool": "Gradle 8.10.2",
    "runner": "linux-x64"
  },
  "dependencies": {
    "lockfile": "gradle.lockfile",
    "lockfileSha256": "REPLACE_WITH_LOCKFILE_DIGEST",
    "sbom": "order-service-2.4.0.cdx.json"
  }
}
~~~

Đây là ví dụ về cấu trúc thông tin. Các giá trị digest phải được tính từ file thực tế; không để placeholder trong metadata phát hành. Repository URL, build URL và các trường khác cần phản ánh đúng nguồn thật của dự án.

Nếu build-info.json được đặt bên trong JAR, trường artifact.sha256 không thể chứa digest cuối cùng của chính JAR mà không tạo vòng lặp: thay đổi file để thêm digest sẽ làm digest thay đổi. Cách phổ biến là:

- Đưa source/build metadata vào trong JAR.
- Tính digest sau khi JAR đã hoàn tất.
- Lưu digest trong manifest phát hành, registry metadata hoặc attestation bên ngoài.
- Liên kết bản ghi bên ngoài với đúng artifact bằng tên và digest.

### Dùng định dạng có schema

Khi metadata được nhiều hệ thống đọc, cần định nghĩa schema và phiên bản schema. Điều này giúp công cụ phát hành, dashboard và hệ thống kiểm kê hiểu trường nào bắt buộc, trường nào tùy chọn và cách thay đổi cấu trúc mà không làm hỏng consumer cũ.

Các trường quan trọng nên có kiểu dữ liệu rõ ràng. Timestamp nên dùng ISO 8601/RFC 3339 với UTC hoặc offset. Digest nên nêu thuật toán, ví dụ sha256:<hex>. Danh sách dependency nên có định danh package và phiên bản, không chỉ tên hiển thị.

## 6. Ghi nhận dependency thực tế

Chỉ lưu pom.xml hoặc build.gradle là chưa đủ để biết chính xác dependency nào đã đi vào artifact. Build file mô tả quy tắc khai báo; dependency resolution còn phụ thuộc version constraint, BOM, lockfile, repository metadata, profile và dependency bắc cầu.

Một bản ghi dependency hữu ích nên thể hiện:

- Package name và version đã phân giải.
- Package ecosystem, ví dụ Maven hoặc npm.
- Group ID và artifact ID đối với Maven.
- Scope hoặc configuration, ví dụ compile, runtime, test.
- Direct hay transitive dependency.
- Repository hoặc nguồn phân phối.
- Checksum hoặc digest của package khi có.
- License và thông tin tham chiếu bảo mật nếu được thu thập.

### Lockfile và dependency graph

Lockfile ghi lại phiên bản được phân giải theo quy tắc của công cụ. Với Gradle, có thể bật dependency locking cho các configuration cần kiểm soát và commit lock state. Với Maven, có thể quản lý phiên bản qua dependency management/BOM và repository nội bộ; các dự án cần khóa đồ thị phân giải có thể bổ sung cơ chế kiểm soát phù hợp.

Lockfile giúp build dùng lại cùng phiên bản dependency, nhưng vẫn cần kiểm soát nội dung artifact tải về. Nếu repository thay nội dung của một tọa độ đã có, checksum verification hoặc repository immutability giúp phát hiện vấn đề.

### Ghi nhận dependency bắc cầu

Một thư viện trực tiếp có thể kéo theo nhiều thư viện khác. Khi có CVE, nhóm cần biết artifact nào có chứa package bị ảnh hưởng, kể cả package đó không được khai báo trực tiếp trong build file.

Vì vậy, nên lưu dependency graph đã phân giải hoặc SBOM được tạo từ đúng artifact/build. Danh sách dependency trực tiếp không đủ để trả lời đầy đủ câu hỏi thành phần nào đang có trong sản phẩm.

## 7. SBOM bổ sung góc nhìn thành phần phần mềm

**Software Bill of Materials (SBOM)** là danh mục các thành phần phần mềm trong một sản phẩm hoặc artifact. SBOM thường mô tả package, phiên bản, định danh, quan hệ phụ thuộc và một số thông tin license hoặc nguồn gốc.

Hai định dạng phổ biến:

- **CycloneDX:** định dạng tập trung vào BOM và các trường phục vụ phân tích thành phần, bảo mật và chuỗi cung ứng.
- **SPDX:** định dạng chuẩn để mô tả package, file, license và thông tin liên quan đến thành phần phần mềm.

SBOM nên được tạo từ đúng dependency graph hoặc artifact cần phát hành. Nếu build tạo nhiều module hoặc image, cần xác định SBOM mô tả toàn bộ sản phẩm hay một thành phần riêng. Gắn SBOM với artifact bằng digest hoặc định danh rõ ràng.

### Ví dụ quy trình SBOM

~~~text
Resolve dependencies
        |
        v
Build application artifact
        |
        v
Collect resolved components
        |
        v
Generate CycloneDX or SPDX SBOM
        |
        v
Store SBOM + artifact digest
        |
        v
Scan dependencies and retain report
~~~

Không nên tạo SBOM từ một lần resolve độc lập sau khi build nếu dependency graph có thể thay đổi giữa hai lần. Cần dùng dữ liệu resolution của chính lần build hoặc xác minh SBOM tương ứng với artifact được phát hành.

SBOM không phải chứng nhận rằng sản phẩm an toàn. Nó cho biết những thành phần được khai báo trong phạm vi SBOM; nhóm vẫn cần scan, đánh giá khả năng khai thác, kiểm tra license và theo dõi lỗ hổng.

## 8. Tạo digest và liên kết với artifact

Sau khi build hoàn tất, tính checksum để nhận diện chính xác nội dung artifact. SHA-256 là lựa chọn thường dùng:

~~~bash
# Linux
sha256sum build/libs/order-service-2.4.0.jar

# PowerShell
Get-FileHash .\build\libs\order-service-2.4.0.jar -Algorithm SHA256
~~~

Digest cần được lưu cùng:

- Artifact name và version.
- Build run ID.
- Commit SHA.
- Repository hoặc registry location.
- Thời điểm tạo và người/identity tạo.
- SBOM và provenance tương ứng.

Tên file có thể được giữ ổn định cho người dùng, nhưng digest mới là định danh nội dung. Hai file có cùng tên có thể có byte khác nhau. Hai bản sao có cùng SHA-256 digest có độ tin cậy rất cao là cùng nội dung; khi cần xác minh, tính digest lại từ file đã tải về.

### Lưu checksum cạnh artifact

Có thể phát hành file checksum cạnh artifact:

~~~text
order-service-2.4.0.jar
order-service-2.4.0.jar.sha256
order-service-2.4.0.cdx.json
order-service-2.4.0.build-info.json
~~~

File checksum cạnh artifact giúp phát hiện lỗi tải hoặc lưu trữ. Tuy nhiên, nếu attacker có thể thay cả artifact và file checksum, checksum không chứng minh nguồn gốc đáng tin cậy. Với luồng phát hành quan trọng, cần chữ ký số hoặc attestation được xác minh bằng identity tin cậy.

## 9. Provenance: bằng chứng artifact được tạo như thế nào

**Build provenance** mô tả nguồn và quy trình đã tạo ra artifact. Nó thường liên kết:

- Subject: artifact và digest của artifact.
- Source: repository và commit.
- Builder: hệ thống hoặc identity thực hiện build.
- Build definition: workflow, script hoặc cấu hình được dùng.
- Invocation: tham số và ngữ cảnh kích hoạt.
- Materials: dependency và đầu vào liên quan.
- Metadata: thời gian, thông tin run và các thuộc tính cần thiết.

Các mô hình như SLSA provenance và in-toto attestation cung cấp cách biểu diễn bằng chứng có cấu trúc. Có thể lưu attestation cạnh artifact hoặc trong hệ thống hỗ trợ tra cứu theo digest.

Provenance khác build-info tự khai báo. Một file JSON do chính script build ghi ra có thể hữu ích cho truy vết, nhưng nếu không được bảo vệ thì người có quyền sửa artifact cũng có thể sửa metadata. Attestation có chữ ký và identity builder được xác minh giúp tăng độ tin cậy của nguồn thông tin.

### Ký và xác minh attestation

Trong hệ thống phát hành, builder có thể ký provenance bằng khóa được quản lý hoặc identity ngắn hạn của CI thông qua cơ chế xác thực phù hợp. Bên triển khai xác minh chữ ký, identity, repository, workflow và subject digest trước khi cho phép sử dụng artifact.

Không nên chỉ kiểm tra rằng có một chữ ký. Chính sách cần xác định:

- Identity nào được phép ký.
- Repository và workflow nào được phép tạo artifact.
- Nhánh hoặc tag nào được phép phát hành.
- Artifact digest có khớp với subject trong attestation không.
- Provenance có đáp ứng yêu cầu về builder và build definition không.

Không đưa private signing key, token hoặc secret vào build-info hay SBOM. Dùng secret manager hoặc cơ chế identity/OIDC phù hợp để cấp quyền ký; giới hạn quyền theo repository, workflow và môi trường.

## 10. Ví dụ thu thập metadata trong GitHub Actions

GitHub Actions cung cấp các biến môi trường giúp ghi nhận run và source:

- GITHUB_REPOSITORY: repository đang chạy workflow.
- GITHUB_SHA: commit được gắn với event.
- GITHUB_REF: branch hoặc tag ref.
- GITHUB_RUN_ID: định danh workflow run.
- GITHUB_RUN_ATTEMPT: số lần chạy thử của run.
- GITHUB_WORKFLOW: tên workflow.

Ví dụ ghi một file build-info đơn giản sau khi build:

~~~yaml
name: Build and describe artifact

on:
  push:
    tags:
      - "v*"

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"

      - name: Build
        run: ./gradlew --no-daemon clean build

      - name: Create build metadata
        shell: bash
        run: |
          mkdir -p build/release-metadata
          cat > build/release-metadata/build-info.txt <<EOF
          repository=$GITHUB_REPOSITORY
          commit=$GITHUB_SHA
          ref=$GITHUB_REF
          workflow=$GITHUB_WORKFLOW
          run_id=$GITHUB_RUN_ID
          run_attempt=$GITHUB_RUN_ATTEMPT
          java_version=$(java -version 2>&1 | head -n 1)
          gradle_version=$(./gradlew --version | grep '^Gradle ' | head -n 1)
          EOF

      - name: Calculate artifact digest
        shell: bash
        run: |
          sha256sum build/libs/*.jar > build/release-metadata/SHA256SUMS

      - name: Upload release evidence
        uses: actions/upload-artifact@v4
        with:
          name: release-evidence
          path: |
            build/libs/*.jar
            build/release-metadata/
~~~

Ví dụ minh họa cách thu thập một số trường. Cần điều chỉnh đường dẫn artifact, tên file, workflow và phiên bản action theo dự án. GITHUB_SHA phụ thuộc loại event; với pull request có thể đại diện merge commit do nền tảng tạo. Nếu cần cả head SHA và base SHA, hãy lấy từ event payload và ghi rõ ý nghĩa từng trường.

Ví dụ trên chỉ tạo build-info và checksum, chưa tạo SBOM, chưa ký provenance và chưa chứng minh build độc lập hoặc tái lập. Artifact upload của workflow là nơi lưu bằng chứng phục vụ run; artifact phát hành chính thức vẫn nên được đưa vào registry hoặc artifact repository có retention và quyền truy cập phù hợp.

### Tránh đưa dữ liệu không tin cậy vào metadata

Branch name, tag name, commit message và dữ liệu pull request có thể chứa ký tự đặc biệt hoặc nội dung do người dùng kiểm soát. Khi ghi vào JSON, properties hoặc shell script, phải escape theo định dạng và tránh ghép trực tiếp dữ liệu không tin cậy vào lệnh shell. Không đưa secret, token, nội dung file cấu hình nhạy cảm hoặc URL có credential vào metadata.

## 11. Lưu trữ artifact và thúc đẩy cùng một artifact qua môi trường

Sau khi artifact được tạo và xác minh, hãy lưu nó trong artifact repository hoặc container registry với:

- Đường dẫn hoặc tọa độ ổn định.
- Version và build ID.
- Digest.
- Metadata build và provenance.
- SBOM và báo cáo kiểm tra.
- Chính sách retention và quyền truy cập.
- Dấu vết tải lên, tải xuống và triển khai.

Một luồng tốt tạo artifact một lần, sau đó promote cùng digest qua dev, staging và production. Không nên build lại từ source ở mỗi môi trường rồi giả định kết quả giống nhau. Build lại có thể nhận dependency, plugin, base image hoặc môi trường khác.

Ví dụ:

~~~text
Build commit a1b2c3
       |
       v
order-service.jar
sha256:abc123...
       |
       v
Artifact repository
       |
       +---- Deploy staging (digest abc123...)
       |
       +---- Verify smoke test / quality gate
       |
       v
Promote same digest
       |
       v
Deploy production (digest abc123...)
~~~

Với container image, ưu tiên triển khai bằng digest thay vì chỉ dùng tag có thể thay đổi. Ví dụ registry.example.com/order-service@sha256:... nhận diện nội dung image cụ thể; tag 2.4.0 có thể bị di chuyển nếu registry cho phép ghi đè.

### Tách cấu hình môi trường khỏi artifact

Artifact nên chứa ứng dụng và các thành phần cần thiết để chạy. Cấu hình môi trường như endpoint, feature flag, secret và thông tin kết nối nên được cấp khi triển khai theo cơ chế cấu hình/secret management. Nếu build riêng một artifact cho mỗi môi trường, khả năng chứng minh staging đã kiểm tra đúng binary được triển khai production sẽ giảm.

Nếu một artifact cần khác biệt theo môi trường, hãy xác định rõ khác biệt đó có thực sự là cấu hình runtime hay là một đầu vào build. Ghi lại mọi đầu vào build làm thay đổi nội dung artifact.

## 12. Truy vết từ artifact về commit và dependency

Khi phát hiện lỗ hổng trong một thư viện, nhóm cần trả lời: artifact nào có chứa thư viện đó, được build từ commit nào và đang chạy ở môi trường nào?

Quy trình truy vết có thể thực hiện theo chiều ngược:

1. Lấy artifact digest từ registry hoặc môi trường đang chạy.
2. Tra cứu build record hoặc attestation theo digest.
3. Xác minh chữ ký và identity builder.
4. Đọc commit SHA, Git ref, build run ID và build definition.
5. Lấy SBOM hoặc dependency graph của chính artifact đó.
6. Tìm package, phiên bản và dependency path bị ảnh hưởng.
7. Xác định release và môi trường đang sử dụng digest đó.
8. Tạo kế hoạch cập nhật dependency, build artifact mới và triển khai theo chính sách.

Chiều truy vết từ commit đến artifact cũng cần được hỗ trợ. Khi một commit được merge, nhóm có thể tìm các build run đã tạo artifact từ commit đó, kiểm tra digest và biết artifact nào đã được promote.

### Lưu lịch sử triển khai

Một bản ghi triển khai nên liên kết:

- Artifact digest.
- Môi trường đích.
- Thời điểm bắt đầu và kết thúc.
- Phiên bản cấu hình hoặc config revision.
- Deployment run ID.
- Kết quả health check và smoke test.
- Người hoặc identity khởi chạy.
- Kết quả rollback nếu có.

Nhờ vậy, khi production có lỗi, nhóm có thể xác định binary thực tế, build đã tạo nó và các dependency liên quan, thay vì chỉ dựa trên nhãn release hoặc tên image.

## 13. Lưu giữ metadata và bằng chứng

Artifact có thể được giữ lâu hơn log CI thông thường. Nếu log bị xóa sau một thời gian ngắn nhưng artifact vẫn được triển khai, khả năng truy vết sẽ bị đứt đoạn. Hãy xác định retention cho từng loại dữ liệu:

| Dữ liệu | Chính sách lưu giữ cần xem xét |
|---|---|
| Artifact phát hành | Theo vòng đời hỗ trợ sản phẩm và yêu cầu rollback |
| Digest/checksum | Giữ cùng thời gian với artifact |
| Build-info | Giữ cùng thời gian với artifact hoặc lâu hơn |
| Provenance/attestation | Giữ đủ lâu để xác minh artifact đang được sử dụng |
| SBOM | Giữ theo phiên bản artifact và yêu cầu quản lý lỗ hổng |
| Build log | Theo yêu cầu điều tra và chính sách tổ chức |
| Deployment record | Theo vòng đời môi trường và yêu cầu kiểm toán |
| Test/security reports | Theo yêu cầu chất lượng, bảo mật và pháp lý |

Không cần giữ mọi log chi tiết vô thời hạn. Nhưng bản ghi tối thiểu để xác định nguồn, nội dung và lịch sử triển khai của artifact cần tồn tại trong suốt thời gian artifact còn được hỗ trợ hoặc sử dụng.

## 14. Những sai lầm thường gặp

### Chỉ lưu version và tên file

Version không cho biết commit hay build run. Hai artifact cùng tên có thể khác nội dung. Lưu commit SHA, build ID và digest để phân biệt.

### Chỉ lưu commit SHA

Commit không mô tả JDK, build tool, dependency đã phân giải, runner hay tham số build. Ghi nhận toolchain, lockfile, SBOM và provenance tương ứng.

### Chỉ lưu build log

Log có thể bị xóa, khó truy vấn và không bảo đảm gắn với artifact đang triển khai. Tạo metadata có cấu trúc và liên kết với digest.

### Tạo lại artifact ở mỗi môi trường

Build lại có thể tạo binary khác. Tạo artifact một lần, xác minh và promote cùng digest qua các môi trường.

### Dùng checksum như bằng chứng nguồn gốc

Checksum phát hiện thay đổi nội dung khi giá trị tham chiếu đáng tin cậy. Nếu cả file và checksum đều bị thay, nó không xác minh được ai đã tạo artifact. Dùng chữ ký và provenance để xác minh nguồn.

### Tạo SBOM từ dependency khai báo thay vì dependency thực tế

Dependency graph có thể gồm nhiều package bắc cầu hoặc phụ thuộc vào resolution. SBOM cần phản ánh đúng thành phần của artifact được phát hành.

### Nhúng build ID và timestamp mà không cân nhắc reproducibility

Metadata thay đổi theo từng run có thể làm artifact khác byte dù source giống nhau. Quyết định trường nào nằm trong artifact và trường nào nằm trong provenance bên ngoài dựa trên yêu cầu tái lập.

### Đưa secret vào build metadata

Build-info và SBOM thường được phân phối rộng hơn log nội bộ. Không ghi token, mật khẩu, private key hoặc URL chứa credential vào các file này.

## 15. Checklist trước khi phát hành artifact

- [ ] Artifact được tạo từ commit SHA và Git ref xác định.
- [ ] Build run ID và attempt được ghi nhận.
- [ ] Working tree sạch hoặc mọi thay đổi sinh thêm được mô tả.
- [ ] JDK, build tool, plugin và môi trường runner được ghi nhận.
- [ ] Dependency lockfile và digest của lockfile được lưu.
- [ ] SBOM phản ánh dependency thực tế của artifact.
- [ ] Artifact có SHA-256 digest được tính sau khi build hoàn tất.
- [ ] Build-info và provenance liên kết đúng artifact digest.
- [ ] Chữ ký/attestation được xác minh theo identity và chính sách tin cậy.
- [ ] Artifact được lưu ở repository có retention và quyền truy cập phù hợp.
- [ ] Staging và production sử dụng cùng artifact digest đã xác minh.
- [ ] Deployment record liên kết artifact với môi trường và kết quả xác minh.
- [ ] Metadata không chứa secret hoặc dữ liệu nhạy cảm.

Khả năng truy vết artifact giúp đội ngũ biết chính xác binary đang chạy được tạo từ đâu, bằng công cụ nào và chứa những thành phần nào. Khi commit, build run, dependency, SBOM, digest và provenance được liên kết, việc điều tra sự cố, đánh giá lỗ hổng, kiểm toán và triển khai lại trở nên có cơ sở. Quan trọng hơn, nhóm có thể promote đúng artifact đã kiểm thử qua các môi trường và xác minh nội dung bằng digest thay vì dựa vào tên file hoặc nhãn phiên bản.
