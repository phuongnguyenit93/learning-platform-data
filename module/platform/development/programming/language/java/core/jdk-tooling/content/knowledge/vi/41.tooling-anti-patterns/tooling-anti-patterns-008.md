# Không kiểm tra artifact: xác minh JAR trước khi phát hành và triển khai

**Không kiểm tra artifact** là anti-pattern xảy ra khi nhóm xem build thành công như bằng chứng rằng file được tạo ra đã đúng và có thể phát hành. Build có thể biên dịch và chạy unit test thành công nhưng JAR cuối cùng vẫn thiếu class hoặc resource, sai manifest, dùng bytecode không tương thích, chứa dependency ngoài dự kiến, bị hỏng khi upload, hoặc khác với file đã được kiểm thử.

Artifact là đầu ra cụ thể của quá trình build: JAR, WAR, ZIP distribution, runtime image do jlink tạo, installer do jpackage tạo, native executable hoặc container image. Người dùng và môi trường production nhận artifact này, vì vậy cần kiểm tra chính file hoặc image sẽ được phát hành.

Nguyên tắc quan trọng là **kiểm thử và xác minh đúng artifact sẽ được deploy**. Ghi lại danh tính artifact, kiểm tra cấu trúc và metadata, xác nhận tính toàn vẹn, chạy smoke test trên gói đã đóng, rồi mới ký, upload hoặc phát hành.

## 1. Vì sao bỏ qua kiểm tra artifact nguy hiểm?

Unit test thường chạy trên class và resource trong thư mục build của project. Chúng chưa chắc đã chạy đúng JAR sau khi Maven/Gradle đóng gói. Plugin đóng gói, resource filtering, shading, manifest, classifier, module descriptor và bước copy/upload đều có thể làm thay đổi đầu ra.

Một số lỗi chỉ xuất hiện sau packaging:

- JAR thiếu Main-Class, khiến java -jar không khởi chạy được.
- Resource hoặc file cấu hình không được đưa vào archive.
- META-INF/services bị mất hoặc bị ghi đè khi tạo fat JAR.
- JAR mang phiên bản cũ do pipeline lấy nhầm file từ thư mục target/ hoặc build/.
- Artifact được build bằng JDK mới hơn mức runtime production hỗ trợ.
- Dependency bị thiếu, trùng class hoặc bị đóng gói sai.
- File bị cắt, hỏng hoặc thay đổi trong lúc lưu trữ, upload hay download.
- File đã được kiểm thử khác với file được ký hoặc deploy.
- Artifact có tên và version đúng nhưng được tạo từ commit không đúng.
- Dependency hoặc binary bị thay thế trong repository.

Một dòng BUILD SUCCESS chỉ xác nhận các task đã chạy trong build hoàn tất theo cấu hình hiện tại. Nó không tự chứng minh mọi yêu cầu về nội dung, tính tương thích, nguồn gốc và khả năng chạy của artifact đều được đáp ứng.

## 2. Phân biệt source, output trung gian và artifact phát hành

| Loại | Ví dụ | Ý nghĩa |
|---|---|---|
| Source | src/main/java/... | Mã nguồn được duy trì |
| Compiled output | target/classes, build/classes/java/main | Class và resource sau compile |
| Test output | target/test-classes, build/classes/java/test | Class phục vụ test |
| Artifact | target/app-1.2.3.jar, build/libs/app-1.2.3.jar | File được phân phối hoặc deploy |
| Release metadata | checksum, signature, SBOM, attestation | Bằng chứng mô tả artifact và quá trình tạo nó |

Unit test trên target/classes có thể PASS trong khi JAR phát hành thiếu application.yml. Tương tự, việc kiểm tra source hoặc class file riêng lẻ không chứng minh file ZIP/JAR đã upload vẫn nguyên vẹn.

Sau khi package, hãy kiểm tra artifact từ đúng đường dẫn đầu ra. Nếu cần test chức năng, chạy JAR/WAR hoặc distribution đã đóng gói trong môi trường gần production.

## 3. Nhận diện artifact trước khi kiểm tra

Một tên file đơn lẻ chưa đủ để xác định một bản build. Hãy ghi nhận các thuộc tính cần thiết:

- Tên artifact và loại file.
- Group, artifact, version và classifier nếu dùng Maven coordinates.
- Commit hoặc source revision.
- JDK/compiler version và target release.
- Build tool cùng phiên bản plugin đóng gói.
- Hệ điều hành, kiến trúc và profile build khi có ảnh hưởng.
- Kích thước file và SHA-256.
- Build run, workflow hoặc release ID.
- Manifest, module name hoặc package version.

Ví dụ:

~~~text
groupId:       com.example
artifactId:    artifact-lab
version:       1.2.3
classifier:    none
extension:     jar
sourceCommit:  4f82a1c
javaRelease:   17
file:          artifact-lab-1.2.3.jar
~~~

Nếu có nhiều file cùng tên ở các thư mục hoặc job khác nhau, ghi rõ đường dẫn và hash để tránh chọn nhầm. Đừng dựa vào tên latest.jar hoặc file còn sót từ lần build trước.

## 4. Kiểm tra sự tồn tại, kích thước và đường dẫn

Bước đầu tiên là xác nhận file mong đợi thật sự được tạo và không rỗng.

PowerShell:

~~~powershell
$artifact = 'target\artifact-lab-1.2.3.jar'
if (-not (Test-Path -LiteralPath $artifact -PathType Leaf)) {
    throw "Artifact not found: $artifact"
}

$file = Get-Item -LiteralPath $artifact
if ($file.Length -le 0) {
    throw "Artifact is empty: $artifact"
}

$file | Select-Object FullName, Length, LastWriteTimeUtc
~~~

Bash:

~~~bash
artifact="target/artifact-lab-1.2.3.jar"
test -s "$artifact" || {
  echo "Artifact missing or empty: $artifact" >&2
  exit 1
}
stat "$artifact"
~~~

Kích thước bằng 0 là lỗi rõ ràng; kích thước khác 0 vẫn chưa đủ. Một file có thể tồn tại nhưng chứa archive hỏng, JAR sai project hoặc bản build cũ. Có thể đặt ngưỡng kích thước hợp lý cho sản phẩm, nhưng ngưỡng đó cần dựa trên artifact thực tế và phải được cập nhật có kiểm soát.

## 5. Kiểm tra cấu trúc JAR và ZIP

JAR dựa trên định dạng ZIP. Nó chứa các entry như class, resource và thư mục META-INF. Lệnh jar --list giúp xem danh sách entry:

~~~bash
jar --list --file target/artifact-lab-1.2.3.jar
~~~

Kiểm tra những thành phần bắt buộc, ví dụ:

~~~text
META-INF/MANIFEST.MF
com/example/HelloApp.class
application.yml
META-INF/services/com.example.Plugin
~~~

Tên entry dùng dấu / kể cả khi chạy trên Windows. Nếu ứng dụng cần service provider, native library, template hoặc file cấu hình, hãy xác nhận chúng thực sự có trong archive.

jar --list cho biết entry nào được khai báo trong archive. Để kiểm tra việc giải nén và CRC của dữ liệu, có thể dùng:

~~~bash
unzip -t target/artifact-lab-1.2.3.jar
~~~

Trên Java, có thể mở từng entry và đọc hết stream để buộc thư viện ZIP giải nén và kiểm tra CRC. Với JAR có chữ ký, việc đọc các entry bằng JarFile được tạo ở chế độ verify=true còn kích hoạt kiểm tra digest của các entry đã ký.

Không nhầm kiểm tra danh sách entry với kiểm tra mọi byte payload. Một archive có thể liệt kê được nhưng lỗi khi đọc một entry cụ thể.

## 6. Kiểm tra manifest

JAR manifest nằm tại META-INF/MANIFEST.MF. Nó chứa metadata và một số cấu hình mà Java launcher hoặc runtime sử dụng.

Ví dụ:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.HelloApp
Implementation-Title: artifact-lab
Implementation-Version: 1.2.3
Build-Commit: 4f82a1c
~~~

Các thuộc tính có ý nghĩa khác nhau:

- Manifest-Version: phiên bản định dạng manifest.
- Main-Class: class có phương thức public static void main(String[] args) để chạy bằng java -jar.
- Implementation-Title và Implementation-Version: metadata triển khai do nhà phát hành cung cấp.
- Specification-Version: phiên bản specification/package khi dự án có quy ước sử dụng.
- Automatic-Module-Name: tên module tự động khi JAR được dùng trên module path.
- Class-Path: danh sách thư viện bổ sung theo cú pháp manifest.
- Multi-Release: true: đánh dấu multi-release JAR có class/resource theo từng phiên bản Java.

Implementation-Version không tự động chứng minh nội dung JAR đúng với version đó. Đây là metadata do build ghi vào; phải so với version/commit mong đợi từ release pipeline.

Xem manifest bằng:

~~~bash
jar --extract --file target/artifact-lab-1.2.3.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
~~~

Trên PowerShell, thay cat bằng Get-Content. Nếu không muốn giải nén vào workspace, có thể đọc manifest qua java.util.jar.JarFile.

## 7. Phân biệt Main-Class, module name và phiên bản artifact

Ba loại metadata thường bị nhầm:

- Main-Class xác định entry point cho java -jar.
- Automatic-Module-Name hoặc module-info.class xác định danh tính module khi dùng module path.
- Implementation-Version là metadata version do dự án ghi vào manifest.

Một JAR thư viện có thể không có Main-Class vì nó không phải ứng dụng độc lập. Một modular JAR có module-info.class nhưng vẫn có thể không khai báo main class. Không đánh dấu QA FAIL chỉ vì một library JAR không chạy được bằng java -jar; hãy kiểm tra đúng hợp đồng của artifact.

Với modular JAR, xem module descriptor:

~~~bash
jar --describe-module --file target/library-1.2.3.jar
~~~

Kiểm tra cả exports, requires, uses và provides nếu API module hoặc service loading là một phần hợp đồng phát hành.

## 8. Kiểm tra class file version và Java compatibility

Bytecode có class-file major version. Runtime không hỗ trợ major version đó sẽ báo UnsupportedClassVersionError.

Một số mốc thường dùng:

| Java release | Class-file major version |
|---:|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Dùng javap -verbose để xem class version:

~~~bash
javap -verbose -classpath target/artifact-lab-1.2.3.jar com.example.HelloApp
~~~

Tìm dòng major version. Với Java 17, giá trị cần là 61.

Biên dịch bằng JDK mới không đồng nghĩa artifact tương thích với runtime cũ. Dùng javac --release 17 hoặc cấu hình compiler plugin/toolchain tương ứng để kiểm tra cả cú pháp, bytecode và API Java SE theo release mục tiêu.

Ví dụ:

~~~bash
javac --release 17 -d classes src/com/example/HelloApp.java
~~~

Kiểm tra ít nhất một class đại diện; với sản phẩm phức tạp, cần kiểm tra toàn bộ artifact hoặc dùng build tooling để bảo đảm mọi module đều target cùng release. Multi-release JAR cần được đánh giá theo từng nhánh class trong META-INF/versions/.

## 9. Kiểm tra dependency và classpath

Một JAR có thể chứa class ứng dụng nhưng thiếu thư viện runtime. jdeps phân tích dependency tĩnh của class và JAR:

~~~bash
jdeps -s target/artifact-lab-1.2.3.jar
~~~

Có thể dùng thêm:

~~~bash
jdeps --jdk-internals target/artifact-lab-1.2.3.jar
~~~

jdeps giúp phát hiện phụ thuộc package/module và việc dùng internal JDK API. Đây là phân tích tĩnh; reflection, service loading, JNI, class name được tạo động hoặc plugin runtime có thể không xuất hiện đầy đủ.

Cần biết loại gói đang phát hành:

- **Thin JAR:** chứa class/resource của ứng dụng; dependency được cung cấp qua classpath hoặc runtime launcher.
- **Fat/uber JAR:** gộp class/resource từ nhiều dependency.
- **Distribution ZIP:** chứa JAR, thư viện, script và cấu hình.
- **Modular application:** dùng module path và module descriptor.
- **Runtime image:** chứa runtime được tùy biến bằng jlink.

Nếu cần fat JAR, kiểm tra dependency thực sự nằm trong archive. Nếu dùng thin JAR, kiểm tra distribution hoặc classpath đi kèm có đủ thư viện. Kiểm tra META-INF/services sau shading vì việc merge sai file service có thể làm mất provider.

## 10. Kiểm tra tài nguyên và nội dung ứng dụng

Một số lỗi chỉ xuất hiện ở runtime vì resource không được đóng gói:

- application.properties, YAML hoặc XML.
- File template, schema và migration.
- Certificate hoặc truststore được đóng gói theo thiết kế.
- Native library cho từng OS/architecture.
- Service provider configuration.
- License và notice của dependency.
- File dữ liệu mặc định.

Đối chiếu danh sách resource bắt buộc với jar --list. Với resource quan trọng, viết smoke test mở resource qua classloader:

~~~java
try (var input = HelloApp.class.getResourceAsStream("/application.properties")) {
    if (input == null) {
        throw new IllegalStateException("application.properties is missing");
    }
}
~~~

Test bằng filesystem source không bảo đảm classloader có thể đọc resource từ JAR. Hãy chạy test trên artifact đã đóng gói.

## 11. Kiểm tra hành vi bằng smoke test trên JAR

Sau khi kiểm tra cấu trúc, chạy chính artifact:

~~~bash
java -jar target/artifact-lab-1.2.3.jar
~~~

Với ứng dụng có tham số, cấu hình và dependency, hãy dùng một bộ input nhỏ đại diện cho đường chạy quan trọng. Xác nhận exit code, stdout/stderr cần thiết và side effect mong đợi.

Ví dụ PowerShell:

~~~powershell
$output = & java -jar $artifact --self-check 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Packaged application failed: $output"
}
$output
~~~

Với thư viện không có main class, tạo test harness hoặc integration test sử dụng JAR như dependency. Mục tiêu là kiểm tra public API và resource từ đúng file đã package.

Smoke test không thay thế unit/integration test. Nó bổ sung bằng chứng rằng gói phân phối thực sự khởi chạy hoặc được tiêu thụ đúng cách.

## 12. Hash và checksum: kiểm tra tính toàn vẹn

SHA-256 tạo fingerprint của toàn bộ bytes trong file. Nếu một byte thay đổi, hash gần như chắc chắn sẽ khác.

PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath $artifact
~~~

Linux:

~~~bash
sha256sum "$artifact"
~~~

macOS:

~~~bash
shasum -a 256 "$artifact"
~~~

So sánh hash sau khi upload/download:

~~~bash
sha256sum artifact-before-upload.jar
sha256sum artifact-after-download.jar
~~~

Hai hash phải khớp nếu hai file có cùng bytes. Tính cả hash sau bước ký nếu chữ ký được thêm vào sau khi build, vì ký JAR làm thay đổi archive.

**Checksum chỉ xác nhận tính toàn vẹn khi giá trị mong đợi đến từ một nguồn đáng tin cậy độc lập.** Nếu artifact và file checksum bị thay cùng lúc trong một nơi lưu trữ không đáng tin, kẻ tấn công có thể thay cả hai.

## 13. Chữ ký số JAR: kiểm tra người phát hành

JAR signing dùng jarsigner để ký các entry trong archive. Khi xác minh, công cụ kiểm tra chữ ký và digest của entry đã ký.

Ký bằng keystore PKCS12:

~~~bash
jarsigner -keystore release-signing.p12 -storetype PKCS12 app.jar release-key
~~~

Xác minh chữ ký và trust chain bằng truststore chứa public certificate đã được xác nhận:

~~~bash
jarsigner -verify -strict -keystore trusted-publishers.p12 -storetype PKCS12 app.jar
~~~

Một thông báo jar verified cho biết chữ ký đã được kiểm tra. Trong môi trường phát hành, còn phải xác minh certificate hoặc public key thuộc đúng publisher theo quy trình trust của tổ chức.

JAR ký bằng self-signed certificate có thể có chữ ký toán học hợp lệ nhưng chưa chứng minh danh tính nhà phát hành. Chỉ tin certificate sau khi xác nhận fingerprint qua kênh độc lập và thêm nó vào truststore được quản lý.

Không lưu private signing key trong repository hoặc log CI. Dùng secret store, HSM hoặc signing service được tổ chức quản lý. Nếu thay đổi bất kỳ entry đã ký, chữ ký có thể không còn hợp lệ; ký sau cùng sau khi hoàn tất packaging và chỉnh sửa archive.

## 14. Phân biệt checksum, signature, SBOM và provenance

| Bằng chứng | Trả lời câu hỏi | Không tự chứng minh |
|---|---|---|
| SHA-256 | File có đúng bytes mong đợi không? | Ai đã tạo file |
| Digital signature | File có được ký bởi key/certificate đã tin cậy không? | Code an toàn hoặc không có lỗ hổng |
| SBOM | Artifact khai báo chứa thành phần/phụ thuộc nào? | Artifact có đúng nguồn gốc hoặc không bị sửa |
| Build provenance/attestation | Artifact được tạo từ source, workflow và môi trường nào? | Mọi code trong artifact đều an toàn |
| Vulnerability scan | Có thành phần khớp lỗ hổng đã biết không? | Artifact đúng version hoặc chạy đúng |

Các lớp kiểm tra này bổ sung cho nhau. Một file có hash đúng vẫn có thể chứa code độc hại nếu hash được lấy từ nguồn không đáng tin. Một chữ ký hợp lệ vẫn có thể thuộc publisher không phù hợp. SBOM tốt giúp kiểm kê dependency nhưng không thay thế kiểm tra nội dung và runtime.

## 15. Kiểm tra provenance và artifact attestation

Provenance mô tả artifact được tạo từ đâu và bằng quy trình nào. Thông tin hữu ích gồm repository, commit, workflow, builder identity, build parameters và digest của artifact.

GitHub Actions có thể tạo artifact attestation sau khi build:

~~~yaml
permissions:
  contents: read
  id-token: write
  attestations: write

steps:
  - name: Build
    run: ./mvnw --batch-mode clean verify

  - name: Attest release artifact
    uses: actions/attest@v4
    with:
      subject-path: target/artifact-lab-1.2.3.jar
~~~

Xác minh artifact bằng GitHub CLI trong GitHub Actions:

~~~bash
gh attestation verify target/artifact-lab-1.2.3.jar -R "$GITHUB_REPOSITORY"
~~~

GitHub Actions cung cấp biến GITHUB_REPOSITORY theo dạng owner/repository. Khi verify, kiểm tra repository, workflow identity, commit và subject digest có khớp release mong đợi không.

Attestation cung cấp bằng chứng nguồn gốc có chữ ký. Hãy giữ policy xác minh rõ ràng và chỉ chấp nhận builder/workflow/repository đã được tin cậy. Attestation không thay thế kiểm tra runtime, signature của artifact hoặc vulnerability scanning.

## 16. SBOM và kiểm tra dependency trong artifact

Software Bill of Materials (SBOM) liệt kê thành phần phần mềm trong artifact, thường dùng SPDX hoặc CycloneDX. SBOM giúp nhóm biết ứng dụng đang chứa thư viện nào và đối chiếu khi có CVE mới.

Một quy trình phát hành nên:

1. Sinh SBOM từ đúng artifact hoặc build graph.
2. Lưu SBOM cùng release và liên kết bằng digest.
3. Quét dependency và package theo chính sách bảo mật.
4. Kiểm tra license và thành phần bị cấm.
5. Tạo attestation cho SBOM nếu pipeline hỗ trợ.
6. Cập nhật SBOM khi artifact thay đổi.

Đừng tạo SBOM cho source tree rồi mặc định nó mô tả chính xác fat JAR cuối cùng. Shading, plugin đóng gói và dependency bundling có thể làm nội dung artifact khác với danh sách dependency ban đầu.

## 17. Bảo vệ dependency được tải về

Không kiểm tra artifact đầu ra là một vấn đề; tin mọi dependency tải về cũng là một rủi ro.

Gradle hỗ trợ dependency verification bằng checksum và chữ ký trong gradle/verification-metadata.xml. Có thể tạo metadata ban đầu:

~~~bash
./gradlew --write-verification-metadata sha256
~~~

Hoặc tạo cả checksum và PGP signature metadata khi nguồn cung cấp chữ ký:

~~~bash
./gradlew --write-verification-metadata sha256,pgp
~~~

Phải review metadata được sinh ra và xác minh checksum từ nguồn tin cậy trước khi commit. Quá trình bootstrap có thể ghi lại fingerprint của dependency đã bị xâm nhập nếu repository hiện tại đã bị compromise.

Gradle dependency verification bảo vệ dependency và plugin được tải qua dependency resolution. Nó không tự xác minh artifact do chính build tạo ra. Các dependency thay đổi như SNAPSHOT cũng có quy tắc riêng và không được xác minh như release dependency bất biến. Vì vậy, vẫn cần bước kiểm tra artifact đầu ra.

## 18. Maven: verify, package và deploy đúng thứ tự

Maven default lifecycle có các phase chính:

- compile: biên dịch source.
- test: chạy unit test.
- package: đóng gói JAR/WAR.
- verify: chạy các kiểm tra bổ sung để xác nhận package đáp ứng tiêu chí chất lượng.
- install: đưa artifact vào local repository.
- deploy: publish artifact lên remote repository.

Với build thông thường, dùng:

~~~bash
./mvnw --batch-mode clean verify
~~~

verify chạy các phase trước nó theo thứ tự, gồm compile, test và package. Tuy nhiên, test trên artifact cuối cùng chỉ diễn ra nếu dự án cấu hình kiểm tra phù hợp, chẳng hạn integration test hoặc smoke test chạy trên JAR/WAR đã đóng gói.

Trước deploy, xác nhận đúng file được tạo:

~~~bash
test -s target/artifact-lab-1.2.3.jar
jar --list --file target/artifact-lab-1.2.3.jar
java -jar target/artifact-lab-1.2.3.jar
~~~

Không suy ra rằng mvn verify đã chạy smoke test trên JAR chỉ từ tên phase. Kiểm tra plugin/task thực tế và đường dẫn artifact mà test sử dụng.

## 19. Gradle: assemble, check và build

Gradle Java plugin cung cấp các task phổ biến:

- compileJava: biên dịch main source.
- test: chạy test.
- jar: tạo JAR.
- assemble: tạo artifact của project.
- check: chạy các kiểm tra.
- build: kết hợp assemble và check theo convention của plugin.

Chạy:

~~~bash
./gradlew clean build
~~~

Sau đó xác nhận file đầu ra:

~~~bash
test -s build/libs/artifact-lab-1.2.3.jar
jar --list --file build/libs/artifact-lab-1.2.3.jar
~~~

Nếu cần test artifact đã đóng gói, thêm task smoke/integration test phụ thuộc vào task jar, rồi chạy task đó trong pipeline. Đảm bảo task dùng đúng file được tạo từ build hiện tại.

Có thể kiểm tra toolchain được Gradle phát hiện:

~~~bash
./gradlew javaToolchains
~~~

Build thành công và dependency verification thành công vẫn chưa tự xác nhận JAR local đã đóng gói đúng; cần kiểm tra output riêng.

## 20. Kiểm tra artifact sau upload và download

Một lỗi thường gặp là kiểm thử file trong workspace nhưng upload nhầm file khác, hoặc file tải xuống khác bytes so với file gốc.

Một pipeline nên:

- Upload đúng đường dẫn artifact, dùng if-no-files-found: error.
- Lưu SHA-256 cùng build metadata.
- Download artifact vào job/release stage.
- Tính lại SHA-256 sau download.
- So sánh với hash được tạo từ bước build đáng tin cậy.
- Chạy smoke test hoặc kiểm tra chữ ký trên file đã download nếu release stage có môi trường phù hợp.
- Deploy chính file đã xác minh.

Ví dụ GitHub Actions:

~~~yaml
- name: Verify artifact exists
  shell: bash
  run: |
    test -s target/artifact-lab-1.2.3.jar
    jar --list --file target/artifact-lab-1.2.3.jar

- name: Create checksum
  shell: bash
  run: |
    sha256sum target/artifact-lab-1.2.3.jar > target/artifact-lab-1.2.3.jar.sha256

- name: Upload verified artifact
  uses: actions/upload-artifact@v7
  with:
    name: artifact-lab-1.2.3
    path: |
      target/artifact-lab-1.2.3.jar
      target/artifact-lab-1.2.3.jar.sha256
    if-no-files-found: error
~~~

Ở job tải xuống, xác minh checksum trước khi sử dụng:

~~~bash
sha256sum --check target/artifact-lab-1.2.3.jar.sha256
~~~

Checksum file phải đến từ cùng build đã tạo artifact và được bảo vệ bằng provenance/signature phù hợp. Nếu người dùng có thể thay cả JAR lẫn checksum, bước so sánh đó không cung cấp xác thực nguồn gốc.

## 21. Kiểm tra artifact container và runtime image

Với Docker/OCI image, kiểm tra JAR riêng chưa đủ. Artifact triển khai là image digest, gồm base image, runtime, file hệ thống và entrypoint.

Các bước nên có:

- Pin base image bằng version hoặc digest.
- Xác nhận architecture và OS phù hợp.
- Scan image và dependency.
- Xem entrypoint, command, environment và exposed ports.
- Chạy container bằng cấu hình gần production.
- Xác minh image digest sau push/pull.
- Ký image hoặc tạo attestation nếu pipeline hỗ trợ.

Với runtime image do jlink tạo, kiểm tra các module được đưa vào:

~~~bash
runtime-image/bin/java --list-modules
~~~

Với installer do jpackage tạo, kiểm tra version, kiến trúc, file được cài và launcher thực tế. Artifact native cần test trên OS/architecture mục tiêu; JAR chạy được trên máy build không chứng minh installer Windows hoặc macOS hoạt động đúng.

## 22. Phát hiện artifact cũ và build không tái lập

Artifact cũ có thể còn trong target/, build/, cache hoặc workspace của self-hosted runner. Pipeline có thể upload file cũ dù compile step hiện tại thành công.

Giảm rủi ro bằng cách:

- Chạy clean trước release build.
- Ghi chính xác output path.
- Dùng version/classifier rõ ràng.
- Không dùng wildcard quá rộng khi upload.
- Ghi commit SHA và build run ID vào metadata.
- So hash của file đã test với file đã upload/deploy.
- Dùng workspace sạch hoặc ephemeral runner cho release.
- Không rebuild lại một artifact khác sau khi đã QA nếu có thể deploy cùng file đã xác minh.

Reproducible build giúp hai lần build từ cùng source và môi trường được kiểm soát tạo ra artifact có bytes giống nhau. Timestamp, thứ tự entry, locale, timezone, plugin version và dependency có thể ảnh hưởng kết quả. Hãy cấu hình reproducible archive khi công cụ hỗ trợ và so sánh SHA-256 qua các lần build độc lập.

Hash khác nhau không tự động chứng minh bị tấn công; có thể do metadata thời gian hoặc môi trường khác. Điều cần làm là tìm nguyên nhân và xác định artifact nào được release.

## 23. Kiểm tra version, classifier và release identity

Maven artifact thường được nhận diện bởi GAV: groupId, artifactId, version; classifier và extension phân biệt thêm các biến thể. Gradle publication cũng có coordinates và variant attributes.

Ví dụ cùng một version có thể có:

~~~text
artifact-lab-1.2.3.jar
artifact-lab-1.2.3-tests.jar
artifact-lab-1.2.3-sources.jar
artifact-lab-1.2.3-javadoc.jar
~~~

Không deploy tests.jar hoặc sources.jar thay cho binary runtime. Kiểm tra artifact classifier, extension và metadata repository.

Release version nên bất biến. Không ghi đè một release đã phát hành bằng file khác nhưng giữ nguyên version. Nếu nội dung thay đổi, phát hành version mới hoặc build identity mới theo chính sách nhóm. SNAPSHOT phù hợp cho phát triển thay đổi liên tục; không coi SNAPSHOT là artifact release ổn định.

## 24. Ví dụ thực hành: build và xác minh JAR bằng Java 17+

Ví dụ này tạo một ứng dụng nhỏ, đóng gói thành JAR, sau đó kiểm tra hash, manifest, class entry và khả năng đọc toàn bộ entry. Bộ kiểm tra dùng JarFile ở chế độ verify để kích hoạt kiểm tra digest của entry đã ký nếu archive có chữ ký.

Cấu trúc thư mục:

~~~text
artifact-lab/
├── src/
│   └── com/example/HelloApp.java
├── tools/
│   └── ArtifactVerifier.java
├── MANIFEST.MF
├── classes/
└── artifact-lab-1.2.3.jar
~~~

File src/com/example/HelloApp.java:

~~~java
package com.example;

public final class HelloApp {
    public static void main(String[] args) {
        System.out.println("ARTIFACT_LAB version=1.2.3");
    }
}
~~~

File MANIFEST.MF:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.HelloApp
Implementation-Title: artifact-lab
Implementation-Version: 1.2.3
Build-Commit: demo-commit

~~~

Biên dịch và đóng gói trên Bash, Linux hoặc macOS:

~~~bash
mkdir -p classes tools
javac --release 17 -d classes src/com/example/HelloApp.java

jar --create \
  --file artifact-lab-1.2.3.jar \
  --manifest MANIFEST.MF \
  -C classes .
~~~

Trên PowerShell:

~~~powershell
New-Item -ItemType Directory -Force classes, tools | Out-Null
javac --release 17 -d classes src\com\example\HelloApp.java
jar --create --file artifact-lab-1.2.3.jar --manifest MANIFEST.MF -C classes .
~~~

File tools/ArtifactVerifier.java:

~~~java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Enumeration;
import java.util.HexFormat;
import java.util.Locale;
import java.util.jar.Attributes;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public final class ArtifactVerifier {
    public static void main(String[] args) throws Exception {
        if (args.length != 5) {
            throw new IllegalArgumentException(
                    "Usage: ArtifactVerifier <jar> <sha256> <main-class> <version> <required-entry>");
        }

        Path artifact = Path.of(args[0]).toAbsolutePath().normalize();
        String expectedHash = args[1].toLowerCase(Locale.ROOT);
        String expectedMain = args[2];
        String expectedVersion = args[3];
        String requiredEntry = args[4];

        if (!Files.isRegularFile(artifact) || !Files.isReadable(artifact)) {
            throw new IllegalStateException(
                    "Artifact is missing or unreadable: " + artifact);
        }
        if (Files.size(artifact) == 0) {
            throw new IllegalStateException("Artifact is empty: " + artifact);
        }

        String actualHash = sha256(artifact);
        if (!MessageDigest.isEqual(
                expectedHash.getBytes(StandardCharsets.US_ASCII),
                actualHash.getBytes(StandardCharsets.US_ASCII))) {
            throw new SecurityException("SHA-256 mismatch: expected "
                    + expectedHash + " but got " + actualHash);
        }

        int entriesRead = 0;
        try (JarFile jar = new JarFile(artifact.toFile(), true)) {
            Manifest manifest = jar.getManifest();
            if (manifest == null) {
                throw new IllegalStateException("JAR manifest is missing");
            }

            Attributes attributes = manifest.getMainAttributes();
            String actualMain = attributes.getValue(Attributes.Name.MAIN_CLASS);
            String actualVersion =
                    attributes.getValue(Attributes.Name.IMPLEMENTATION_VERSION);

            if (!expectedMain.equals(actualMain)) {
                throw new IllegalStateException("Main-Class mismatch: " + actualMain);
            }
            if (!expectedVersion.equals(actualVersion)) {
                throw new IllegalStateException(
                        "Implementation-Version mismatch: " + actualVersion);
            }
            if (jar.getJarEntry(requiredEntry) == null) {
                throw new IllegalStateException(
                        "Required entry is missing: " + requiredEntry);
            }

            Enumeration<JarEntry> entries = jar.entries();
            byte[] buffer = new byte[8192];
            while (entries.hasMoreElements()) {
                JarEntry entry = entries.nextElement();
                if (entry.isDirectory()) {
                    continue;
                }

                try (InputStream input = jar.getInputStream(entry)) {
                    while (input.read(buffer) != -1) {
                        // Read every entry to check decompression, CRC and signed digests.
                    }
                }
                entriesRead++;
            }
        }

        System.out.println("ARTIFACT=" + artifact.getFileName());
        System.out.println("SHA256=" + actualHash);
        System.out.println("MAIN_CLASS=" + expectedMain);
        System.out.println("IMPLEMENTATION_VERSION=" + expectedVersion);
        System.out.println("REQUIRED_ENTRY=" + requiredEntry);
        System.out.println("ENTRIES_READ=" + entriesRead);
        System.out.println("ARTIFACT_VERIFY=PASS");
    }

    private static String sha256(Path path) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream input = Files.newInputStream(path)) {
            byte[] buffer = new byte[8192];
            int read;
            while ((read = input.read(buffer)) != -1) {
                digest.update(buffer, 0, read);
            }
        }
        return HexFormat.of().formatHex(digest.digest());
    }
}
~~~

Biên dịch bộ kiểm tra:

~~~bash
javac --release 17 -d tools tools/ArtifactVerifier.java
~~~

Xem cấu trúc và bytecode:

~~~bash
jar --list --file artifact-lab-1.2.3.jar
javap -verbose -classpath artifact-lab-1.2.3.jar com.example.HelloApp
jdeps -s artifact-lab-1.2.3.jar
~~~

Tạo hash và chạy verifier trên Bash:

~~~bash
HASH=$(sha256sum artifact-lab-1.2.3.jar | awk '{print $1}')

java -cp tools ArtifactVerifier \
  artifact-lab-1.2.3.jar "$HASH" \
  com.example.HelloApp 1.2.3 com/example/HelloApp.class
~~~

Trên PowerShell:

~~~powershell
$artifact = 'artifact-lab-1.2.3.jar'
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $artifact).Hash.ToLowerInvariant()
java -cp tools ArtifactVerifier $artifact $hash com.example.HelloApp 1.2.3 'com/example/HelloApp.class'
~~~

Chạy chính JAR đã package:

~~~bash
java -jar artifact-lab-1.2.3.jar
~~~

Output của ứng dụng:

~~~text
ARTIFACT_LAB version=1.2.3
~~~

Với bản build thử nghiệm trên Azul OpenJDK 24.0.2, verifier trả về:

~~~text
ARTIFACT=artifact-lab-1.2.3.jar
SHA256=f2fe60fa31c1d377897b5ffdcafbc93c1898fb9707011aec04b380ca0a2a0689
MAIN_CLASS=com.example.HelloApp
IMPLEMENTATION_VERSION=1.2.3
REQUIRED_ENTRY=com/example/HelloApp.class
ENTRIES_READ=2
ARTIFACT_VERIFY=PASS
~~~

Hash có thể thay đổi khi build lại vì archive có thể chứa timestamp hoặc metadata khác. Khi chạy lại, tính hash từ đúng artifact của lần build đó và so với giá trị được lưu trong metadata đáng tin cậy.

## 25. Kiểm tra bộ xác minh phát hiện artifact bị sửa

Sau khi tạo checksum, copy artifact và thay đổi một byte hoặc thêm dữ liệu vào bản sao. Chạy verifier với hash mong đợi ban đầu:

~~~powershell
Copy-Item artifact-lab-1.2.3.jar tampered.jar
[System.IO.File]::AppendAllText('tampered.jar', 'tampered')
java -cp tools ArtifactVerifier tampered.jar $hash com.example.HelloApp 1.2.3 'com/example/HelloApp.class'
~~~

Verifier phải kết thúc với lỗi:

~~~text
java.lang.SecurityException: SHA-256 mismatch
~~~

Trong CI, một test âm như vậy giúp xác nhận bước kiểm tra thực sự fail khi bytes thay đổi. Không dùng file đã bị sửa để deploy.

## 26. Kiểm tra JAR signature trong thực tế

Để thử luồng chữ ký trong môi trường phát triển, có thể tạo keystore tạm:

~~~bash
keytool -genkeypair -alias artifact-demo -keyalg RSA -keysize 3072 -validity 365 -storetype PKCS12 -keystore signer.p12 -storepass changeit -keypass changeit -dname "CN=Artifact Lab"
~~~

Ký JAR:

~~~bash
jarsigner -keystore signer.p12 -storetype PKCS12 -storepass changeit -keypass changeit artifact-lab-1.2.3.jar artifact-demo
~~~

Để kiểm thử trust trong lab, export certificate rồi import vào truststore riêng:

~~~bash
keytool -exportcert -alias artifact-demo -keystore signer.p12 -storetype PKCS12 -storepass changeit -rfc -file signer.cer
keytool -importcert -alias artifact-demo -file signer.cer -keystore truststore.p12 -storetype PKCS12 -storepass changeit -noprompt
~~~

Xác minh:

~~~bash
jarsigner -verify -strict -keystore truststore.p12 -storetype PKCS12 -storepass changeit -verbose -certs artifact-lab-1.2.3.jar
~~~

Trong lab, certificate tự ký được tin cậy vì public certificate đã được import vào truststore riêng. Đây là minh họa cơ chế xác minh. Trong production, chỉ import certificate/key sau khi xác minh publisher fingerprint qua kênh độc lập; không dùng password ví dụ hoặc self-signed test key làm release identity.

Sau khi ký, tính lại SHA-256. JAR đã ký có bytes khác với JAR trước ký vì archive được thêm signature metadata.

## 27. Kiểm thử trên đúng runtime và môi trường đích

Artifact có thể chạy trên JDK của developer nhưng lỗi trên production vì runtime version, module, OS, architecture, environment variable hoặc dependency khác nhau.

Tối thiểu cần xác nhận:

- Runtime Java tối thiểu mà ứng dụng hỗ trợ.
- OS/architecture của binary hoặc native library.
- Module cần thiết nếu dùng module path hoặc jlink.
- Environment variables, file permission và working directory.
- Dependency ngoài JDK và native dependency.
- Cấu hình TLS, truststore và certificate nếu ứng dụng kết nối mạng.
- Entrypoint và command của container hoặc installer.

Nếu release hỗ trợ Java 17 và 21, chạy smoke test trên cả hai runtime. Nếu phát hành installer Windows, test launcher trên Windows; nếu phát hành macOS ARM64, test trên kiến trúc đó. Cross-platform compile không thay thế runtime test trên từng nền tảng.

## 28. Những anti-pattern cần tránh

| Anti-pattern | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ nhìn BUILD SUCCESS | Không biết JAR cuối cùng có đúng không | Inspect và smoke test artifact |
| Chỉ test class trong target/classes | Không phát hiện resource/manifest bị thiếu | Test JAR sau package |
| Upload wildcard toàn bộ target/** | Có thể upload file cũ hoặc phụ | Chọn đường dẫn artifact cụ thể |
| Dùng tên latest.jar | Khó xác định build identity | Dùng version, commit và digest |
| Chỉ lưu checksum cạnh artifact ở cùng nơi không tin cậy | Có thể thay cả hai file | Ký metadata hoặc dùng attestation |
| Coi self-signed certificate là publisher đã xác thực | Có thể tin nhầm key | Xác minh fingerprint và trust anchor |
| Chỉ chạy jdeps | Bỏ sót dependency động/reflection | Kết hợp smoke/integration test |
| Chỉ scan vulnerability | Không biết file có đúng release không | Kết hợp hash, signature, provenance |
| Rebuild sau khi QA rồi deploy bản mới | Deploy bytes chưa được kiểm thử | Deploy chính artifact đã xác minh |
| Ghi đè release version | Cùng tọa độ nhưng nội dung khác | Dùng release bất biến và version mới |
| Tin checksum được tạo từ artifact không rõ nguồn | Fingerprint có thể đã sai ngay từ đầu | Lấy expected digest từ build/release tin cậy |
| Dùng runtime image để build | Thiếu compiler/tooling | Dùng JDK ở build stage |

## 29. Quy trình kiểm tra artifact trước khi release

Một pipeline có thể triển khai các bước theo thứ tự:

1. **Build sạch:** xóa output cũ và build từ commit đã xác định.
2. **Test source:** chạy unit test và static analysis.
3. **Package:** tạo JAR/WAR/distribution hoặc image.
4. **Kiểm tra file:** xác nhận path, kích thước, loại file và version.
5. **Kiểm tra cấu trúc:** liệt kê archive, đọc entry, xác nhận resource/manifest.
6. **Kiểm tra tương thích:** kiểm tra bytecode, dependency, module và runtime.
7. **Smoke test:** chạy chính artifact hoặc test harness sử dụng nó.
8. **Integrity:** tạo và lưu SHA-256 từ file đã kiểm tra.
9. **Security:** kiểm tra chữ ký, SBOM, dependency và vulnerability.
10. **Provenance:** tạo/verify attestation theo release policy.
11. **Publish:** upload chính file đã kiểm tra, không rebuild.
12. **Post-download check:** tính lại hash và xác minh trước deploy.

Không phải mọi dự án cần tất cả bước ở cùng mức độ. Artifact nội bộ nhỏ có thể dùng kiểm tra cấu trúc, hash và smoke test; release public hoặc production cần thêm signing, provenance, SBOM và kiểm soát dependency theo chính sách tổ chức.

## 30. Checklist review artifact cho Java project

- [ ] Đường dẫn và tên artifact đúng project, version, classifier và extension.
- [ ] Artifact được tạo từ commit/build run mong đợi.
- [ ] File tồn tại, đọc được và có kích thước hợp lý.
- [ ] JAR/ZIP có thể liệt kê và đọc hết entry.
- [ ] Manifest có metadata đúng; Main-Class đúng nếu là executable JAR.
- [ ] Các class/resource/service provider bắt buộc có trong archive.
- [ ] Bytecode target tương thích với Java runtime được hỗ trợ.
- [ ] Dependency, module và native library được cung cấp đầy đủ.
- [ ] jdeps và các kiểm tra static phù hợp đã chạy.
- [ ] Smoke test chạy trên chính artifact đã đóng gói.
- [ ] SHA-256 được lưu và kiểm tra sau upload/download.
- [ ] Chữ ký được xác minh bằng truststore chứa publisher key đã tin cậy.
- [ ] SBOM và vulnerability scan phù hợp với release policy.
- [ ] Provenance/attestation xác nhận đúng source và workflow.
- [ ] Artifact deploy có cùng digest với file đã QA.
- [ ] Release version không bị ghi đè bằng bytes khác.

Kiểm tra artifact là một phần của build/release contract. Khi nhóm xác minh nội dung, metadata, tương thích, hash, chữ ký và hành vi của đúng file sẽ phát hành, lỗi packaging và lỗi thay đổi artifact có thể được phát hiện trước khi đến người dùng.

## Tài liệu tham khảo

- Oracle JDK 27 — [The jar Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jar.html).
- Oracle JDK 26 — [JAR File Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html).
- Oracle JDK 26 — [The jarsigner Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jarsigner.html).
- Oracle JDK 26 — [The javap Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javap.html).
- Oracle JDK 26 — [The jdeps Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html).
- Oracle JDK 26 — [The java Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html).
- Apache Maven — [Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html).
- Gradle 9 — [Securing Dependencies](https://docs.gradle.org/current/userguide/dependency_verification.html).
- GitHub Docs — [Using Artifact Attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations).
- GitHub Docs — [Establishing Build Provenance](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations).
