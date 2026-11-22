# Xác minh artifact Java: checksum, chữ ký và tính hợp lệ

## Mục tiêu

Sau bài này, bạn có thể giải thích xác minh artifact là gì; phân biệt identity, integrity, authenticity và provenance; kiểm tra tọa độ và nguồn tải; tính SHA-256/SHA-512 trên Linux và Windows; xác minh JAR signature bằng jarsigner và PGP detached signature bằng GPG; bật strict checksum trong Maven và dependency verification trong Gradle; kiểm tra cấu trúc, manifest, class, resource và module descriptor; xác minh dependency graph; chạy consumer test từ artifact đã publish; lưu bằng chứng trong CI; và xử lý lỗi checksum, signature, metadata, repository hoặc nội dung artifact.

## 1. Xác minh artifact là gì?

Artifact là file được tạo hoặc phân phối từ một build, chẳng hạn JAR, WAR, EAR, ZIP, POM, native binary, container image hoặc package khác.

**Xác minh artifact** là quá trình kiểm tra file nhận được có đúng artifact dự kiến, giữ nguyên nội dung, đến từ nhà phát hành được tin cậy và đáp ứng yêu cầu sử dụng hay không.

Một lệnh tải thành công hoặc HTTP 200 chỉ cho biết server đã trả dữ liệu. Nó không chứng minh file:

- Thuộc đúng group, artifact và version.
- Có bytes giống artifact đã phát hành.
- Được ký bởi nhà phát hành mong đợi.
- Có nội dung và metadata đúng.
- Có thể được consumer compile hoặc chạy.
- Được tạo từ source revision và workflow đã phê duyệt.

Xác minh cần ở cả hai phía:

1. **Producer:** kiểm tra artifact sau build, trước khi ký và publish.
2. **Consumer:** kiểm tra file tải từ repository trước khi sử dụng hoặc đưa vào release.

Một artifact đã được producer kiểm tra vẫn có thể bị thay đổi trên đường truyền hoặc trong repository. Consumer cần kiểm tra lại theo chính sách tin cậy của mình.

## 2. Các lớp xác minh artifact

Mỗi lớp trả lời một câu hỏi khác nhau.

| Lớp | Câu hỏi | Bằng chứng |
|---|---|---|
| Identity | Có đúng artifact/version không? | Coordinates, repository URL, POM |
| Integrity | Bytes có giống fingerprint dự kiến không? | SHA-256/SHA-512 |
| Authenticity | Ai đã ký artifact? | JAR signature, PGP signature |
| Provenance | Artifact được tạo từ source/workflow nào? | Build attestation |
| Structure | File có đúng nội dung không? | jar, unzip, manifest |
| Compatibility | Consumer có dùng được không? | javap, jdeps, compile/test |
| Security | Có lỗ hổng hoặc policy violation không? | SBOM, vulnerability scan |

Các lớp này bổ trợ cho nhau:

- Checksum đúng không tự chứng minh ai phát hành file.
- Signature hợp lệ không tự chứng minh phiên bản an toàn hoặc không có lỗ hổng.
- Provenance ghi nhận nguồn build không tự chứng minh output có thể tái tạo.
- JAR mở được không tự chứng minh API tương thích với consumer.

## 3. Xác nhận identity trước khi kiểm tra bytes

Với Maven, ghi lại groupId, artifactId, version, packaging/extension, classifier và repository.

Ví dụ:

~~~text
com.acme.platform:domain:1.0.0
com.acme.platform:domain:jar:sources:1.0.0
com.acme.platform:domain:jar:javadoc:1.0.0
~~~

Artifact chính, sources và Javadoc có thể cùng version nhưng là các file khác nhau. Không so checksum của sources.jar với checksum của main JAR.

Với Gradle, kiểm tra dependency declaration, selected component và variant. Một dependency có thể chọn variant theo usage, attributes, platform hoặc capability. Tên file trong cache không phải bằng chứng duy nhất về variant đã được chọn.

Ghi lại repository URL thực tế: Maven Central, repository manager nội bộ, Gradle repository được khai báo tập trung, mirror/proxy hoặc staging repository. Cùng tọa độ có thể tồn tại trong nhiều repository và trả bytes khác nhau.

Không đưa username, password hoặc token trong repository URL vào audit log. Redact credential trước khi lưu bằng chứng.

## 4. Checksum và hash

Hash function nhận dữ liệu có độ dài bất kỳ và tạo digest có độ dài cố định. SHA-256 tạo digest 256 bit; SHA-512 tạo digest 512 bit.

Quy trình đối chiếu:

1. Tính digest của file đang có.
2. Lấy digest mong đợi từ nguồn tin cậy.
3. So sánh hai giá trị.
4. Nếu khác, dừng sử dụng artifact và điều tra.

Ví dụ minh họa:

~~~text
artifact.jar
SHA-256: 9f86d081884c7d659a2feaa0c55ad015...
~~~

Chuỗi trên chỉ minh họa hình thức digest, không phải checksum của JAR cụ thể.

Ưu tiên SHA-256 hoặc SHA-512 cho kiểm tra integrity mới. Không dùng MD5 hoặc SHA-1 làm cơ chế chống giả mạo. Nếu repository cũ chỉ cung cấp SHA-1/MD5, hiểu rõ chúng chủ yếu phát hiện lỗi truyền tải; bổ sung checksum mạnh hoặc chữ ký được xác minh độc lập.

### Checksum không đồng nghĩa authenticity

Giả sử server cung cấp đồng thời:

~~~text
domain-1.0.0.jar
domain-1.0.0.jar.sha256
~~~

Nếu attacker có thể thay cả JAR và file .sha256, hai file vẫn khớp nhau. Checksum lấy từ cùng nguồn truyền tải chỉ chứng minh hai file nhất quán theo dữ liệu nguồn đó; nó không tự chứng minh nguồn phát hành đáng tin.

Để xác minh authenticity, cần checksum lấy từ kênh tin cậy độc lập hoặc chữ ký số gắn với public key đã xác minh.

## 5. Tính và kiểm tra SHA-256

Linux:

~~~bash
sha256sum domain-1.0.0.jar
~~~

macOS:

~~~bash
shasum -a 256 domain-1.0.0.jar
~~~

Nếu có file checksum tham chiếu ở định dạng chuẩn:

~~~bash
sha256sum --check domain-1.0.0.jar.sha256
~~~

File checksum mẫu:

~~~text
9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08  domain-1.0.0.jar
~~~

Digest trên chỉ minh họa định dạng. Release thực tế phải dùng giá trị được công bố cho đúng artifact.

Windows PowerShell:

~~~powershell
Get-FileHash .\domain-1.0.0.jar -Algorithm SHA256
~~~

So sánh với digest mong đợi:

~~~powershell
$expected = 'REPLACE_WITH_TRUSTED_SHA256'
$actual = (Get-FileHash .\domain-1.0.0.jar -Algorithm SHA256).Hash

if ($actual -ne $expected) {
    throw 'Artifact SHA-256 mismatch'
}

Write-Output 'SHA256_OK'
~~~

Giá trị REPLACE_WITH_TRUSTED_SHA256 phải được thay bằng digest lấy từ release metadata hoặc kênh độc lập đã được xác minh.

Stdout khi khớp:

~~~text
SHA256_OK
~~~

Khi không khớp, script dừng bằng lỗi để pipeline không tiếp tục sử dụng artifact. Đừng tạo file checksum từ chính file vừa tải rồi coi đó là xác minh; lệnh tạo digest chỉ ghi nhận nội dung hiện tại.

## 6. Xác minh chữ ký số

Chữ ký số kết hợp hash của nội dung với private key của signer. Consumer dùng public key để kiểm tra chữ ký.

Nếu chữ ký hợp lệ, nội dung được ký không bị thay đổi sau khi ký và chữ ký được tạo bằng private key tương ứng với public key đó.

Để tin signer, còn phải xác nhận public key/certificate thực sự thuộc nhà phát hành mong đợi. Một chữ ký hợp lệ từ một key không đáng tin không làm artifact trở nên đáng tin.

| Dạng chữ ký | Ví dụ | Cách kiểm tra |
|---|---|---|
| JAR signature | .SF, .RSA, .DSA hoặc .EC trong META-INF | jarsigner -verify |
| Detached OpenPGP | File .asc cạnh JAR/POM | gpg --verify |

Hai dạng chữ ký có format và quy trình trust khác nhau. Không dùng jarsigner để kiểm tra file .asc PGP hoặc dùng GPG để thay cho JAR entry signature verification.

## 7. Xác minh JAR signature bằng jarsigner

JDK cung cấp công cụ jarsigner để ký và xác minh Java Archive.

~~~bash
jarsigner -verify -strict -verbose -certs domain-1.0.0.jar
~~~

- -verify: xác minh chữ ký của JAR.
- -strict: coi cảnh báo nghiêm trọng là lỗi.
- -verbose: hiển thị trạng thái từng entry.
- -certs: hiển thị certificate của signer.

Khi chữ ký hợp lệ, output có thể chứa:

~~~text
jar verified.
~~~

Nếu JAR chưa được ký, công cụ có thể báo JAR unsigned. Nếu entry đã ký bị sửa sau khi ký, xác minh sẽ thất bại.

Output verbose có thể hiển thị:
- s: chữ ký của entry đã được xác minh.
- m: entry được liệt kê trong manifest.
- k: certificate signer được tìm thấy trong keystore được kiểm tra.

Hãy đọc cả warning và thông tin certificate, không chỉ nhìn dòng jar verified.

### Kiểm tra signer có được tin cậy không

Có thể dùng truststore chứa certificate signer đã được tổ chức xác minh:

~~~bash
jarsigner -verify -strict -verbose -certs \
  -keystore trusted-signers.p12 \
  domain-1.0.0.jar trustedSigner
~~~

trusted-signers.p12 và alias trustedSigner là ví dụ. Truststore phải được tạo từ certificate/public key đã xác minh qua quy trình tin cậy độc lập.

Phân biệt ba câu hỏi:

1. Chữ ký có khớp nội dung hay không?
2. Certificate có hợp lệ theo trust policy hay không?
3. Certificate có thuộc đúng publisher mà project mong đợi hay không?

Certificate có thời hạn. Chữ ký có timestamp từ TSA đáng tin có thể giúp xác định chữ ký được tạo khi certificate còn hiệu lực. Kiểm tra warning về certificate hết hạn/chưa có hiệu lực, chain không validate, signer self-signed, key usage không cho phép code signing, thuật toán yếu hoặc timestamp authority không hợp lệ.

JAR signature xác minh các entry được ký thông qua manifest và signature files. File được thêm sau khi ký có thể không nằm trong tập entry đã ký. Hãy đóng gói hoàn chỉnh trước khi ký. Sau khi ký, không sửa, thêm hoặc thay resource trong JAR; nếu cần thay đổi, tạo lại artifact và ký lại.

## 8. Xác minh chữ ký PGP detached

Một số repository, trong đó có Maven Central, phân phối chữ ký PGP detached:

~~~text
domain-1.0.0.jar
domain-1.0.0.jar.asc
domain-1.0.0.pom
domain-1.0.0.pom.asc
~~~

Xác minh:

~~~bash
gpg --verify domain-1.0.0.jar.asc domain-1.0.0.jar
~~~

Trước khi tin kết quả, lấy public key của publisher từ nguồn chính thức và xác minh fingerprint qua kênh độc lập:

~~~bash
gpg --show-keys --with-fingerprint publisher-public-key.asc
~~~

Đối chiếu toàn bộ fingerprint với thông tin do publisher hoặc tổ chức công bố. Sau đó import key đã xác minh vào keyring phù hợp và chạy lại xác minh.

Không chỉ dựa vào tên hiển thị, email hoặc key ID ngắn. Tên và email trong key có thể được tự khai báo; fingerprint đầy đủ là định danh cần đối chiếu.

Khi chữ ký hợp lệ, GPG có thể hiển thị:

~~~text
Good signature from "Example Publisher"
~~~

Good signature cho biết chữ ký khớp với key. Nó chưa tự chứng minh key thuộc đúng publisher. Kiểm tra fingerprint và trust policy.

JAR signature xác minh các entry trong Java Archive. PGP detached signature thường đi cùng artifact/POM trên Maven repository và có thể ký nhiều loại file. Một release có thể cung cấp cả checksum lẫn chữ ký. Không phải mọi JAR đều được ký bằng jarsigner; hãy tuân theo policy phát hành của repository/project.

## 9. Xác minh checksum dependency trong Maven

Maven Resolver có thể lấy checksum của artifact trong repository và so sánh với bytes tải về.

Maven CLI hỗ trợ strict checksum mode:

~~~bash
./mvnw -C --batch-mode verify
~~~

-C tương đương --strict-checksums: build thất bại nếu checksum nhận được không khớp artifact. Chế độ lax -c chỉ cảnh báo khi mismatch và không phù hợp với release gate yêu cầu fail-closed.

Checksum được tải cạnh artifact qua cùng repository/transport có thể phát hiện file hỏng hoặc thay đổi không nhất quán. Nó không tự chứng minh checksum đến từ publisher đáng tin cậy.

Maven Resolver phân biệt checksum transport với trusted checksum. Với yêu cầu cao hơn, có thể quản lý checksum tin cậy độc lập trong source control hoặc xác minh chữ ký PGP.

### Trusted checksum trong Maven Resolver

Maven Resolver hỗ trợ trusted checksum sources. Với Maven 3.9.x, có thể cấu hình summary checksum files và chế độ fail nếu thiếu trusted checksum theo hướng dẫn chính thức.

Quy trình tổng quát:

1. Xác minh artifact/checksum ban đầu từ nguồn tin cậy.
2. Ghi trusted SHA-512 vào summary file trong project.
3. Review file checksum và nguồn repository.
4. Commit trusted checksum cùng source.
5. Chạy build ở chế độ verify, không bật chế độ record.
6. Khi dependency thay đổi hợp lệ, review checksum mới trước khi cập nhật.

Không sinh trusted checksum rồi tự động tin ngay. Nếu artifact ban đầu đã bị thay đổi, thao tác record có thể đóng dấu nội dung sai là nội dung tin cậy.

## 10. Xác minh dependency trong Gradle

Gradle hỗ trợ dependency verification cho dependency và plugin đã resolve. Hai phương thức chính:

- **Checksum:** kiểm tra bytes của artifact.
- **Signature:** kiểm tra artifact được ký bởi key được khai báo tin cậy.

Có thể dùng cả hai.

Sinh verification metadata bằng task thực sự resolve dependency/plugin cần kiểm tra:

~~~bash
./gradlew --write-verification-metadata sha256,pgp build
~~~

Gradle tạo file:

~~~text
gradle/verification-metadata.xml
~~~

File có thể chứa checksum và trusted public key metadata cho artifact đã được quan sát.

Sau đó:

1. Mở và review file metadata.
2. Xác minh các key/fingerprint với publisher.
3. Kiểm tra dependency bắc cầu và plugin.
4. Commit metadata đã review.
5. Chạy build bình thường để Gradle thực hiện verification.

Nếu chỉ resolve compile dependency nhưng bỏ qua test, runtime, plugin hoặc configuration khác, metadata có thể thiếu artifact khi pipeline khác chạy. Hãy chạy task đại diện cho mọi configuration/variant cần được bảo vệ.

Lệnh tạo metadata ghi nhận artifact từ repository hiện tại. Nếu repository đã trả nhầm hoặc artifact bị compromise, checksum mới có thể khiến nội dung sai được tin cậy. Review từng thay đổi, xác minh key/checksum từ nguồn độc lập và không tự động chấp nhận metadata mới chỉ vì Gradle tạo ra file.

Dependency verification không thay thế vulnerability scan. Nó trả lời câu hỏi artifact có đúng bytes/key đã tin cậy hay không; nó không trả lời dependency có CVE, license không phù hợp hoặc code độc hại ngay từ bản phát hành ban đầu hay không.

## 11. Kiểm tra cấu trúc và nội dung JAR

Liệt kê entry:

~~~bash
jar --list --file domain-1.0.0.jar
~~~

Kiểm tra ZIP archive:

~~~bash
unzip -t domain-1.0.0.jar
~~~

Xem manifest:

~~~bash
unzip -p domain-1.0.0.jar META-INF/MANIFEST.MF
~~~

Kiểm tra package/class public dự kiến, resource configuration, service provider files trong META-INF/services, manifest attributes, version/build metadata và module-info.class nếu dùng JPMS.

Đảm bảo không có .env, credential, private key, source local hoặc file debug ngoài ý muốn; không có class trùng lặp hoặc file ngoài phạm vi publication.

Với JAR chứa manifest, có thể xem:

~~~text
Implementation-Title
Implementation-Version
Specification-Title
Specification-Version
Automatic-Module-Name
Main-Class
Class-Path
Multi-Release
~~~

Không phải artifact nào cũng có tất cả thuộc tính. Giá trị manifest phải khớp release metadata của project.

Kiểm tra module descriptor:

~~~bash
jar --describe-module --file domain-1.0.0.jar
~~~

Nếu dùng JPMS, xác nhận module name, requires, exports, opens, uses và provides đúng thiết kế. Nếu JAR không có module-info.class, nó vẫn có thể là library hợp lệ trên classpath hoặc automatic module. Không coi thiếu descriptor là lỗi nếu project không yêu cầu JPMS.

## 12. Kiểm tra Java bytecode và API compatibility

Một JAR có thể mở được nhưng vẫn không tương thích với runtime hoặc consumer.

Dùng javap:

~~~bash
javap -verbose -classpath domain-1.0.0.jar \
  com.acme.platform.domain.Customer
~~~

Trong output, tìm major version.

| Java release | Class file major version |
|---:|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Class file version cho biết mức bytecode. Nó không chứng minh artifact chỉ dùng API của release đó nếu compiler không được cấu hình đúng --release.

Dùng jdeps:

~~~bash
jdeps --summary domain-1.0.0.jar
~~~

Xem dependency chi tiết:

~~~bash
jdeps --recursive --verbose:class domain-1.0.0.jar
~~~

Với modular JAR:

~~~bash
jdeps --check com.acme.platform.domain --module-path libs
~~~

Đường dẫn và module name phải khớp project thật. Kết quả giúp phát hiện dependency không mong muốn, module thiếu hoặc package phụ thuộc vào API nội bộ.

Xem public signature:

~~~bash
javap -classpath domain-1.0.0.jar \
  -public com.acme.platform.domain.Customer
~~~

Với release library, có thể dùng japicmp hoặc Revapi để so sánh artifact mới với version trước. Công cụ cần được cấu hình đúng baseline, filter và policy để phân loại breaking changes.

Không nhầm API compatibility với file integrity: hai JAR có checksum khác nhau vẫn có thể tương thích API; hai JAR cùng tọa độ cũng có thể khác API ngoài dự kiến.

## 13. Kiểm tra dependency graph và metadata

Artifact library thường cần POM hoặc Gradle Module Metadata để consumer biết dependency bắc cầu và variant.

Maven: xem POM đã publish:

~~~bash
cat domain-1.0.0.pom
~~~

Kiểm tra GAV, packaging, dependency và scope, version, parent/BOM, repository metadata và classifier sources/Javadoc.

Với consumer project:

~~~bash
./mvnw dependency:tree -Dverbose
~~~

Gradle:

~~~bash
./gradlew dependencies
./gradlew dependencyInsight --dependency domain --configuration runtimeClasspath
~~~

dependencyInsight cho biết lý do một version được chọn và dependency path đưa artifact vào configuration. Nếu publication có Gradle Module Metadata, kiểm tra variant attributes và artifact file được consumer chọn; không chỉ xem POM nếu Gradle consumer dùng metadata phong phú hơn.

## 14. Consumer test từ artifact đã publish

Producer build pass chưa đủ. Cần xác nhận consumer độc lập có thể resolve và sử dụng artifact từ repository đích.

Quy trình:

1. Publish vào staging repository hoặc repository thử nghiệm.
2. Tạo consumer project nhỏ, không nằm trong workspace producer.
3. Cấu hình đúng repository URL.
4. Khai báo dependency bằng coordinates/version đã phát hành.
5. Compile, test và chạy smoke test.
6. Kiểm tra dependency tree và checksum của file được resolve.
7. Xác nhận consumer không lấy nhầm artifact từ local cache.

Maven dependency:

~~~xml
<dependency>
    <groupId>com.acme.platform</groupId>
    <artifactId>domain</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Chạy:

~~~bash
./mvnw --batch-mode clean verify
~~~

Để kiểm tra độc lập hơn, dùng local repository riêng:

~~~bash
./mvnw -Dmaven.repo.local=/tmp/verify-m2 \
  --batch-mode clean verify
~~~

Nếu consumer chỉ pass khi producer đã chạy install trên cùng máy, có thể test đang lấy artifact từ local repository thay vì remote repository.

Gradle dependency:

~~~groovy
repositories {
    maven {
        url = uri('https://repo.example.com/releases')
    }
}

dependencies {
    implementation 'com.acme.platform:domain:1.0.0'
}
~~~

Chạy:

~~~bash
./gradlew --refresh-dependencies clean test
~~~

Trong môi trường audit, dùng Gradle User Home/cache tách biệt hoặc workspace sạch để kiểm tra resolution từ repository đích.

Nếu consumer cần kiểm tra một class public cụ thể:

~~~bash
javac -cp domain-1.0.0.jar ConsumerCheck.java
java -cp .:domain-1.0.0.jar ConsumerCheck
~~~

Trên Windows, classpath separator là dấu chấm phẩy:

~~~powershell
javac -cp domain-1.0.0.jar ConsumerCheck.java
java -cp ".;domain-1.0.0.jar" ConsumerCheck
~~~

ConsumerCheck phải gọi API thực tế mà project cung cấp. Đây là mẫu; tên class và source cần thay bằng consumer fixture phù hợp.

## 15. Xác minh artifact trong CI pipeline

CI nên dừng ngay khi một kiểm tra bắt buộc thất bại.

Ví dụ script Linux:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

ARTIFACT="build/libs/domain-1.0.0.jar"
if [ -z "$EXPECTED_ARTIFACT_SHA256" ]; then
  echo "Set trusted EXPECTED_ARTIFACT_SHA256" >&2
  exit 1
fi

test -s "$ARTIFACT"

ACTUAL_SHA256="$(sha256sum "$ARTIFACT" | awk '{print $1}')"
if [ "$ACTUAL_SHA256" != "$EXPECTED_ARTIFACT_SHA256" ]; then
  echo "Artifact checksum mismatch" >&2
  exit 1
fi

echo "CHECKSUM_OK"

unzip -t "$ARTIFACT" >/dev/null
echo "ARCHIVE_OK"

jarsigner -verify -strict -verbose -certs "$ARTIFACT"
echo "JAR_SIGNATURE_OK"

jar --list --file "$ARTIFACT" >/dev/null
echo "JAR_CONTENTS_OK"
~~~

Script giả định artifact đã được ký JAR và CI có EXPECTED_ARTIFACT_SHA256 lấy từ nguồn tin cậy. Nếu project dùng PGP detached signature thay vì JAR signature, thay bước jarsigner bằng GPG verification và kiểm tra fingerprint publisher.

Không hardcode expected hash của một release khác. Mỗi version/build phải có digest tương ứng.

### GitHub Actions

~~~yaml
name: Verify artifact

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '21'

      - name: Build
        run: ./mvnw --batch-mode clean verify

      - name: Verify dependency checksums
        run: ./mvnw -C --batch-mode verify

      - name: Inspect artifact
        run: |
          test -s target/domain-1.0.0.jar
          unzip -t target/domain-1.0.0.jar
          jar --list --file target/domain-1.0.0.jar
~~~

Ví dụ minh họa kiểm tra dependency checksum và archive contents. Trong workflow thật, thay đường dẫn/version artifact theo project; thêm bước signature/checksum/provenance theo policy release. Cần chạy cùng verification gate trong workflow phát hành thật.

### Maven strict checksum

~~~bash
./mvnw -C --batch-mode clean verify
~~~

Nếu lệnh báo checksum mismatch, giữ log, xác định artifact/repository và điều tra nguồn trước khi cập nhật cache hoặc checksum metadata.

### Gradle dependency verification

Khi project đã commit gradle/verification-metadata.xml, build bình thường sẽ kiểm tra các artifact được metadata bao phủ. Nếu thiếu checksum/key hoặc nội dung khác metadata, build báo verification failure.

Không tắt verification trong release job để làm pipeline pass.

## 16. Provenance, SBOM và attestation

Software Bill of Materials (SBOM) liệt kê component và dependency có trong artifact/release. SBOM hữu ích để điều tra dependency bị phát hiện lỗ hổng, theo dõi license và hỗ trợ incident response.

SBOM không chứng minh artifact không bị thay đổi. Cần gắn SBOM với đúng artifact digest hoặc release identity.

Provenance ghi nhận artifact được tạo từ repository, commit, workflow, builder và thông tin liên quan. Attestation có thể liên kết artifact digest, source repository/commit, workflow/job và build identity.

Kiểm tra attestation theo policy nền tảng và xác nhận subject digest khớp file đang sử dụng.

Attestation hợp lệ không tự thay thế checksum/signature verification. Nó trả lời câu hỏi về nguồn và quá trình tạo artifact; checksum/signature kiểm tra nội dung và signer.

Một artifact có chữ ký hợp lệ vẫn có thể chứa dependency dễ bị tấn công. Một artifact không có CVE đã biết vẫn có thể là file bị thay đổi. Release gate thường cần cả integrity, authenticity, dependency/security scan và consumer tests.

## 17. Kiểm tra release từ repository

Khi xác minh artifact đã publish:

1. Xác nhận coordinates và release version.
2. Xác nhận repository URL/namespace.
3. Tải main artifact và metadata.
4. Tải checksum/signature tương ứng.
5. Xác minh chữ ký/fingerprint hoặc trusted checksum.
6. So sánh SHA-256/SHA-512.
7. Kiểm tra POM/Gradle metadata.
8. Kiểm tra archive contents và manifest.
9. Chạy consumer test từ repository đích.
10. Lưu bằng chứng cùng release record.

Maven Central yêu cầu artifact, POM và PGP signatures theo quy định phát hành của repository. Release đã publish không được ghi đè bằng nội dung khác. Với repository nội bộ, áp dụng policy immutable tương tự nếu muốn giữ tính ổn định cho consumer.

### Artifact staging

Nếu repository hỗ trợ staging:

- Publish vào staging.
- Tải lại artifact từ staging.
- Xác minh checksum/signature.
- Chạy consumer test.
- Kiểm tra POM và attached artifacts.
- Promote sang release sau khi tất cả gate pass.

Việc kiểm tra sau upload quan trọng vì file trong workspace producer chưa chắc là bytes thực tế mà consumer tải từ repository.

## 18. Lỗi thường gặp và cách xử lý

### SHA-256 không khớp

**Nguyên nhân:** tải nhầm file/version, artifact hỏng, mirror trả bytes khác, file bị thay đổi hoặc expected checksum không đúng.

**Cách xử lý:** dừng sử dụng file; xác nhận coordinates/URL; tính lại digest; lấy checksum từ nguồn độc lập; tải lại từ repository tin cậy; không sửa expected checksum chỉ để pipeline pass.

### Checksum sidecar khớp nhưng không biết publisher

**Nguyên nhân:** checksum được tải cùng artifact qua cùng repository, nên cả hai có thể bị thay đổi đồng thời.

**Cách xử lý:** xác minh PGP/JAR signature hoặc lấy trusted checksum qua kênh độc lập; đối chiếu fingerprint signer.

### JAR unsigned

**Nguyên nhân:** publisher không ký JAR bằng jarsigner, hoặc signature files không có trong archive.

**Cách xử lý:** kiểm tra policy của project/repository. Nếu yêu cầu JAR signature, từ chối artifact unsigned. Nếu project dùng PGP detached signature, xác minh file .asc thay vì kỳ vọng JAR có signature entries.

### jarsigner báo signature verification failed

**Nguyên nhân:** entry bị thay đổi sau khi ký, signature block hỏng, digest không khớp hoặc thuật toán bị vô hiệu hóa.

**Cách xử lý:** tải lại artifact chính thức; kiểm tra SHA-256; xác minh signature files và từng entry; không sửa JAR đã ký.

### jar verified nhưng signer không đáng tin

**Nguyên nhân:** chữ ký mật mã hợp lệ nhưng certificate self-signed, chain chưa validate hoặc key không thuộc publisher mong đợi.

**Cách xử lý:** kiểm tra -verbose -certs; đối chiếu fingerprint với nguồn độc lập; dùng truststore/keystore chứa certificate đã xác minh; bật -strict.

### Certificate hết hạn hoặc timestamp warning

**Nguyên nhân:** certificate hết hạn, TSA chain lỗi hoặc timestamp không hợp lệ.

**Cách xử lý:** xem chi tiết warning và certificate chain; kiểm tra timestamp token; xác nhận policy về thời điểm ký. Không tự động bỏ qua warning nghiêm trọng.

### PGP Good signature nhưng key không được tin

**Nguyên nhân:** chữ ký khớp key nhưng fingerprint chưa được xác minh hoặc key có thể bị giả mạo.

**Cách xử lý:** lấy public key từ nguồn chính thức; so sánh fingerprint đầy đủ qua kênh độc lập; sau đó mới tin signature.

### Maven báo checksum mismatch

**Nguyên nhân:** artifact tải về khác checksum repository công bố, mirror chưa đồng bộ, cache cũ hoặc artifact bị thay đổi.

**Cách xử lý:** giữ log và coordinates; kiểm tra repository origin/mirror; tải lại từ nguồn tin cậy; không dùng -c để che lỗi trong release gate.

### Gradle dependency verification failed

**Nguyên nhân:** checksum thiếu, artifact bytes khác metadata, PGP signature/key thay đổi hoặc dependency mới chưa được review.

**Cách xử lý:** đọc chính xác artifact/configuration/repository trong error; xác minh release upstream; review checksum/key mới; cập nhật metadata có kiểm soát. Không chạy lệnh tạo metadata rồi commit ngay mà không review.

### JAR mở được nhưng thiếu class/resource

**Nguyên nhân:** publish nhầm classifier, sai build variant, packaging task bỏ sót output hoặc artifact không phải version mong đợi.

**Cách xử lý:** liệt kê JAR; kiểm tra POM/Gradle metadata; so sánh với artifact build output; chạy consumer test.

### Consumer compile được nhưng runtime lỗi

**Nguyên nhân:** thiếu transitive dependency, dependency scope/variant sai, class version quá mới, service provider/resource không được đóng gói hoặc JPMS module không resolve.

**Cách xử lý:** xem dependency tree/runtime classpath; kiểm tra class major version; kiểm tra manifest/services/module descriptor; chạy test bằng đúng runtime mục tiêu.

### POM đúng nhưng JAR sai

**Nguyên nhân:** upload thủ công nhầm file, publication trỏ sai artifact, repository ghi đè hoặc cache đang giữ bản khác.

**Cách xử lý:** tải file từ repository bằng clean cache; tính SHA-256; so với build output và release manifest; kiểm tra publication task/artifact mapping.

### Chỉ một platform fail

**Nguyên nhân:** classifier/variant không đúng OS/architecture, native library thiếu hoặc bytecode/runtime khác.

**Cách xử lý:** kiểm tra variant selection, artifact classifier, architecture và native dependencies; test trên từng platform được hỗ trợ.

### Artifact hash thay đổi sau khi ký

**Nguyên nhân:** file bị chỉnh sửa, repack hoặc metadata bị thêm sau signing.

**Cách xử lý:** xác định bước nào đã thay đổi file; ký lại artifact cuối cùng; cập nhật checksum/signature/attestation; không dùng chữ ký cũ.

## 19. Mẫu báo cáo xác minh artifact

| Trường | Giá trị cần lưu |
|---|---|
| Artifact identity | groupId, artifactId, version, classifier, extension |
| Repository | URL/namespace đã redact credential |
| File | Tên, kích thước, path |
| SHA-256 | Digest tính từ file nhận được |
| Expected digest | Nguồn và giá trị tham chiếu |
| Checksum result | PASS/FAIL |
| Signature type | JAR, PGP hoặc không có |
| Signer | Certificate/key fingerprint |
| Signature result | PASS/FAIL và warning |
| Structure | JAR integrity, manifest, class/resource |
| Compatibility | Java version, API, module/dependency checks |
| Consumer test | Build/test result từ repository |
| Provenance | Attestation subject digest/source/workflow |
| Decision | ACCEPT/REJECT và lý do |

Không đánh dấu PASS nếu chỉ có checksum được tải từ cùng một nguồn mà không có trust decision theo policy. Ghi rõ mức xác minh thực sự đạt được.

## 20. Checklist trước khi chấp nhận artifact

### Identity và nguồn

- [ ] Coordinates, version, classifier và extension đúng.
- [ ] Repository URL đúng nguồn đã phê duyệt.
- [ ] Không lấy nhầm snapshot hoặc version cũ.
- [ ] POM/Gradle metadata khớp artifact.
- [ ] Credential/URL nhạy cảm đã được redact khỏi log.

### Integrity và authenticity

- [ ] SHA-256 hoặc SHA-512 được tính từ file thực tế.
- [ ] Expected digest đến từ nguồn tin cậy.
- [ ] JAR signature hoặc PGP signature được xác minh khi policy yêu cầu.
- [ ] Fingerprint signer được xác minh độc lập.
- [ ] Certificate/algorithm warnings được xử lý.
- [ ] Artifact không bị sửa sau signing.

### Nội dung và compatibility

- [ ] Archive mở và liệt kê được.
- [ ] Manifest và version metadata đúng.
- [ ] Class/resource dự kiến có mặt.
- [ ] Không có secret hoặc file ngoài ý muốn.
- [ ] Class file version phù hợp runtime.
- [ ] JPMS descriptor/dependency đúng nếu dùng.
- [ ] Consumer compile/test từ repository đích thành công.

### Release evidence

- [ ] Dependency verification metadata được review.
- [ ] SBOM/provenance được liên kết với đúng artifact digest.
- [ ] Staging artifact được tải lại và kiểm tra.
- [ ] Report lưu digest, signer, source và kết quả.
- [ ] Release repository áp dụng immutable version policy.
- [ ] Có quyết định ACCEPT/REJECT rõ ràng.

## 21. Quy trình xác minh artifact chuẩn

1. Xác định chính xác coordinates, file và repository.
2. Tải artifact và metadata vào workspace sạch.
3. Tính SHA-256/SHA-512.
4. So sánh với trusted checksum hoặc xác minh signature.
5. Xác nhận fingerprint signer.
6. Kiểm tra archive, manifest và nội dung.
7. Kiểm tra class version, API, module và dependencies.
8. Resolve artifact trong consumer project độc lập.
9. Chạy compile, test và smoke test trên runtime mục tiêu.
10. Kiểm tra SBOM/provenance nếu release policy yêu cầu.
11. Lưu verification report.
12. Chỉ chấp nhận artifact khi tất cả gate bắt buộc pass.

Khi một bước fail, giữ nguyên artifact và log để điều tra. Không tự thay expected checksum, tắt strict mode hoặc bỏ signature requirement chỉ để làm pipeline chạy tiếp.

## 22. Tài liệu tham khảo chính thức

- [The jarsigner Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jarsigner.html) — xác minh JAR signature, certificate, keystore, verbose output, strict mode và timestamp.
- [Jarsigner — Dev.java](https://dev.java/learn/jvm/tool/security/jarsigner/) — ví dụ ký và xác minh JAR, hiển thị certificate signer.
- [Gradle Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html) — checksum, PGP signature, transitive dependency và verification metadata.
- [Gradle Securing Repositories](https://docs.gradle.org/current/userguide/securing_repositories.html) — repository trust, centralized declarations và artifact verification.
- [Maven CLI Options Reference](https://maven.apache.org/ref/3.9.16/maven-embedder/cli.html) — -C/--strict-checksums và -c/--lax-checksums.
- [Maven Resolver: About Checksums](https://maven.apache.org/components/resolver-archives/resolver-2.0.24/about-checksums.html) — checksum transport, giới hạn trust và SHA-256/SHA-512.
- [Maven Resolver: Expected Checksums](https://maven.apache.org/resolver/expected-checksums.html) — trusted checksum sources và summary checksum files.
- [Guide to Uploading Artifacts to Maven Central](https://maven.apache.org/repository/guide-central-repository-upload.html) — release artifact, POM, PGP signatures và immutable release policy.
- [Download Apache Maven](https://maven.apache.org/download.cgi) — checksum SHA-512 và signature .asc của Maven distributions.
- [The javap Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javap.html) — đọc class file metadata và bytecode.
- [The jdeps Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html) — phân tích dependency của Java class và module.

Xác minh artifact cần kiểm tra đúng identity, bytes, signer, cấu trúc và khả năng sử dụng của file nhận được. Checksum phát hiện khác biệt nội dung; chữ ký xác minh key đã ký; provenance liên kết artifact với source/workflow; consumer test xác nhận file thực sự hoạt động trong môi trường mục tiêu. Hãy kết hợp các lớp theo release policy và lưu bằng chứng để người khác có thể kiểm tra lại quyết định chấp nhận artifact.
