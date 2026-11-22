# Gắn checksum, chữ ký và thông tin truy vết cho sản phẩm

## 1. Mục tiêu: chứng minh đúng file, đúng người phát hành và đúng quy trình build

Khi phát hành một ứng dụng Spring Boot, người nhận cần trả lời ba câu hỏi khác nhau:

1. **Artifact có bị thay đổi không?** So sánh checksum mật mã (ví dụ SHA-256) của file nhận được với digest đã được công bố qua một kênh đáng tin cậy.
2. **Ai đã ký/phát hành artifact?** Xác minh chữ ký số bằng public key hoặc certificate chain, sau đó kiểm tra danh tính người/workflow ký có nằm trong trust policy không.
3. **Artifact được tạo ra như thế nào?** Đọc provenance để biết source repository/commit, build definition, builder identity, dependencies và output digest; đối chiếu với SBOM để biết những thành phần nào nằm trong sản phẩm.

Ba cơ chế bổ sung cho nhau:

- **Checksum** là dấu vân tay của bytes. Nó phát hiện file khác với digest tham chiếu, nhưng bản thân checksum không chứng minh ai đã tạo file.
- **Digital signature** xác thực chữ ký gắn với một key/identity được tin cậy và bảo vệ nội dung đã ký khỏi bị sửa mà không phát hiện.
- **Build provenance** mô tả inputs và quá trình tạo output. Provenance cần được phát hành bởi builder/CI đáng tin và được ký/attest để người nhận xác minh được nguồn gốc.

Ví dụ release Spring Boot:

~~~text
Git tag + commit
       │
       ▼
CI: clean test + bootJar / mvn package
       │
       ▼
Executable JAR ── SHA-256 checksum
       │           └─ signature / verification bundle
       ▼
Container image ── image digest
       │           ├─ Cosign image signature
       │           ├─ SLSA provenance attestation
       │           └─ SBOM attestation
       ▼
Publish immutable artifact/image
       │
       ▼
Consumer verifies digest + signer + provenance policy
       │
       ▼
Deploy đúng image digest đã xác minh
~~~

Sau bài học, bạn có thể tạo checksum SHA-256 cho Spring Boot JAR, ký JAR hoặc ký nguyên file bằng Sigstore Cosign, ký OCI image theo digest, đính kèm SLSA provenance/SBOM, xác minh chữ ký và áp dụng các bước đó trong Gradle/Maven CI pipeline.

**Phạm vi:** ví dụ dùng Java 17 và Spring Boot 3.3.13 để minh họa build artifact. Cosign, Sigstore, SLSA và build tool phải được pin/kiểm chứng theo version mà tổ chức sử dụng; các lệnh bên dưới mô tả workflow, không khẳng định một bản tool cụ thể là mới nhất.

## 2. Phân biệt checksum, chữ ký, provenance và SBOM

| Thành phần | Câu hỏi trả lời | Bảo vệ điều gì? | Không tự chứng minh |
| --- | --- | --- | --- |
| SHA-256 checksum | Bytes hiện tại có khớp digest tham chiếu? | Integrity / phát hiện thay đổi | Ai tạo file, file có an toàn không |
| Digital signature | Key/identity nào ký nội dung này? | Authenticity + integrity của payload đã ký | Mã nguồn tốt, build sạch, không có malware |
| Build provenance | Source, builder, parameters và dependencies nào tạo output? | Traceability / auditability | Artifact không có vulnerability |
| SBOM | Artifact chứa những component nào? | Inventory và phân tích dependency | Artifact được build bởi ai |
| Reproducible build | Có thể dựng lại cùng bytes từ inputs/build process tương đương? | Khả năng tái lập và đối chiếu | Người phát hành hoặc source có đáng tin |

### 2.1. Checksum chỉ có ý nghĩa khi digest tham chiếu đáng tin

Giả sử người phát hành gửi hai file:

~~~text
app.jar
app.jar.sha256
~~~

Nếu kẻ tấn công thay cả JAR và file checksum trên cùng một server không được bảo vệ, người nhận vẫn có thể tính ra một checksum khớp. Vì vậy cần lấy digest từ một nguồn tin cậy độc lập, hoặc ký checksum manifest bằng chữ ký số có trust chain rõ ràng.

Checksum rất hữu ích để phát hiện lỗi truyền tải, file hỏng, nhầm phiên bản hoặc thay đổi không mong muốn. Nhưng nó không thay thế chữ ký.

### 2.2. Chữ ký cần trust policy

Một file có chữ ký hợp lệ có nghĩa là chữ ký khớp với public key/certificate tương ứng. Người xác minh vẫn phải hỏi:

- Public key đó có thuộc tổ chức/workflow được phép phát hành không?
- Certificate có chain và identity hợp lệ không?
- OIDC issuer và identity có đúng repository/workflow/ref không?
- Signing key có bị lộ/thu hồi hoặc policy đã thay đổi không?
- Chữ ký có gắn với đúng digest của artifact/image đang nhận không?

Không chấp nhận một chữ ký chỉ vì lệnh verify trả success với một public key bất kỳ do chính nguồn artifact cung cấp.

### 2.3. Provenance khác build-info.properties

Spring Boot build-info hoặc manifest có thể chứa version, build time và Git commit. Những giá trị đó hữu ích khi vận hành, nhưng chúng thường do build script tự ghi vào artifact. Chúng không tự chứng minh builder thực sự chạy source commit đó.

Provenance theo SLSA/in-toto mô tả build definition và execution, builder identity và output subject digest. Khi được tạo bởi build platform đáng tin và ký/attest, consumer có thể xác minh claim nguồn gốc theo policy.

### 2.4. SBOM khác provenance

SBOM (Software Bill of Materials) liệt kê component/dependency, version, license hoặc package metadata. Provenance nói về **quá trình tạo** sản phẩm. Một image có SBOM đầy đủ vẫn có thể được build từ source không đáng tin; một provenance hợp lệ không tự liệt kê toàn bộ thư viện nếu builder không tạo SBOM.

Release tốt thường phát hành cả hai, gắn chúng với cùng image digest.

## 3. Tạo SHA-256 checksum cho Spring Boot artifact

Giả sử Gradle đã tạo executable Boot JAR:

~~~bash
./gradlew clean test bootJar
~~~

Nếu project cấu hình archive output tên `app.jar`, đường dẫn ví dụ là:

~~~text
build/libs/app.jar
~~~

Maven tương đương có thể là:

~~~bash
mvn clean verify
~~~

Với POM đặt `<finalName>app</finalName>`, artifact ví dụ ở:

~~~text
target/app.jar
~~~

Tên/path phụ thuộc cấu hình thực tế của project. Hãy ký **đúng executable Boot JAR cuối cùng**, không nhầm với `-plain.jar` hoặc file trung gian trước bước repackage.

### 3.1. Linux/macOS: sha256sum

Tạo sidecar:

~~~bash
sha256sum build/libs/app.jar > app.jar.sha256
~~~

Kiểm tra lại:

~~~bash
sha256sum --check app.jar.sha256
~~~

Nếu sidecar ghi đúng tên file và bytes không thay đổi, output có dạng:

~~~text
build/libs/app.jar: OK
~~~

Tên hiển thị trong output phụ thuộc path được ghi trong sidecar. Nếu chuyển artifact sang thư mục khác, bảo đảm sidecar tham chiếu đúng file hoặc tạo lại sidecar trong release directory.

Có thể tính SHA-512 tương tự:

~~~bash
sha512sum build/libs/app.jar > app.jar.sha512
sha512sum --check app.jar.sha512
~~~

SHA-256 và SHA-512 là các lựa chọn phù hợp cho digest integrity hiện đại. Không dùng MD5 hoặc SHA-1 làm cơ chế bảo vệ artifact mới vì các hàm này đã có vấn đề collision.

### 3.2. Windows PowerShell

~~~powershell
Get-FileHash .\build\libs\app.jar -Algorithm SHA256
~~~

PowerShell in các trường `Algorithm`, `Hash` và `Path`. Đối chiếu `Hash` với digest lấy từ release manifest/kênh tin cậy.

Nếu đã lưu sidecar theo định dạng gồm digest ở token đầu tiên và tên file ở phần còn lại:

~~~powershell
$actual = (Get-FileHash .\build\libs\app.jar -Algorithm SHA256).Hash.ToLowerInvariant()
$expected = (Get-Content .\app.jar.sha256 -Raw).Trim().Split()[0].ToLowerInvariant()

if ($actual -ne $expected) {
    throw "SHA-256 mismatch"
}

"SHA-256 OK"
~~~

Lệnh giả định sidecar chứa checksum theo định dạng văn bản mà token đầu tiên là digest. Nếu repository dùng JSON hoặc format khác, parse theo schema của format đó thay vì dùng `Split()[0]`.

### 3.3. Không tự điền checksum giả

SHA-256 phụ thuộc từng byte của artifact. Không thể đoán digest chỉ từ tên file, version hoặc source code. Tính digest sau khi artifact đã được đóng gói hoàn chỉnh, rồi lưu giá trị thật vào manifest/release metadata.

## 4. Java 17: chương trình tính SHA-256 cho file

Ví dụ độc lập này dùng Java SE, không cần Spring Boot, Gradle hay Maven. Nó đọc file theo buffer để không phải nạp toàn bộ JAR vào RAM.

Tạo `ArtifactSha256.java`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class ArtifactSha256 {

    private ArtifactSha256() {
    }

    public static void main(String[] args)
            throws IOException, NoSuchAlgorithmException {

        if (args.length != 1) {
            System.err.println("Usage: java ArtifactSha256 <file>");
            System.exit(2);
        }

        Path file = Path.of(args[0]);
        MessageDigest digest = MessageDigest.getInstance("SHA-256");

        try (InputStream input = Files.newInputStream(file)) {
            byte[] buffer = new byte[8192];
            int count;

            while ((count = input.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }

        String hex = HexFormat.of().formatHex(digest.digest());
        System.out.println("SHA-256=" + hex);
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac ArtifactSha256.java
java ArtifactSha256 build/libs/app.jar
~~~

Output có dạng:

~~~text
SHA-256=<64 ký tự hex phụ thuộc bytes thực tế của app.jar>
~~~

Đoạn `<64 ký tự hex...>` mô tả định dạng output, không phải checksum có thể copy. Kết quả thật thay đổi khi file thay đổi.

### 4.1. Vì sao dùng MessageDigest và HexFormat?

- `MessageDigest.getInstance("SHA-256")` lấy implementation của hàm băm SHA-256 từ Java security providers.
- `update(buffer, 0, count)` cập nhật digest từng khối, hỗ trợ file lớn.
- `digest()` hoàn tất và trả 32 bytes (256 bits).
- `HexFormat.of().formatHex(...)` biểu diễn 32 bytes thành 64 ký tự hexadecimal.
- `try-with-resources` đóng InputStream kể cả khi đọc file có lỗi.

Chương trình này chỉ **tính digest**. Nó không tự biết digest tham chiếu nào đáng tin; bước verify vẫn phải so sánh với digest đã được phát hành/được ký từ nguồn đáng tin.

## 5. Quy trình checksum cho release

Một thư mục release có thể có:

~~~text
release/
├── app.jar
├── app.jar.sha256
├── app.jar.sigstore.json
├── sbom.spdx.json
└── release-notes.txt
~~~

Ý nghĩa:

- `app.jar`: executable artifact.
- `app.jar.sha256`: digest sidecar để phát hiện thay đổi.
- `app.jar.sigstore.json`: Sigstore bundle chứa signature và verification metadata cho blob.
- `sbom.spdx.json`: inventory component của artifact, nếu pipeline đã tạo.
- Provenance có thể được lưu thành attestation trong OCI registry, release store hoặc một hệ thống artifact metadata có kiểm soát.

**Thứ tự quan trọng:** nếu dùng `jarsigner` để sửa JAR, hãy tính checksum và ký Cosign blob **sau khi JAR signing hoàn tất**. Nếu sửa/repackage JAR sau khi tạo checksum hoặc chữ ký, digest/signature cũ không còn khớp.

Cosign `sign-blob` tạo bundle tách rời và không sửa nội dung JAR; checksum của JAR không đổi khi bundle được tạo. Người nhận phải nhận cả JAR và bundle, đồng thời kiểm identity của signer.

## 6. Chữ ký số: private key, public key và trust

Digital signature sử dụng cặp khóa:

- **Private key** tạo chữ ký. Chỉ signer hoặc signing service được phép sử dụng khóa này.
- **Public key** xác minh chữ ký. Consumer có thể nhận public key qua trust channel độc lập.
- **Certificate** có thể ràng buộc public key với một danh tính/tổ chức qua CA.
- **Trust policy** quyết định certificate/key/identity nào được phép phát hành artifact.

Khi file đã ký bị thay một byte, phép verify phải thất bại (nếu byte đó thuộc payload được ký). Tuy nhiên, chữ ký hợp lệ không đồng nghĩa phần mềm không có lỗi hoặc không có malware.

### 6.1. Hai cách quản lý khóa

| Mô hình | Cách hoạt động | Ưu điểm | Rủi ro/điều kiện |
| --- | --- | --- | --- |
| Key-based | Dùng key pair lâu dài, thường trong KMS/HSM/secure key store | Kiểm soát trust key rõ, dùng được trong mạng riêng | Phải bảo vệ, backup, rotate và revoke key |
| Keyless (Sigstore) | Dùng OIDC identity, ephemeral key và certificate ngắn hạn | Giảm việc giữ private key dài hạn | Phải kiểm đúng OIDC issuer, identity và workflow policy |

Không lưu private signing key trong Git repository, Docker image, JAR, build logs hoặc artifact output. Không truyền password/secret dưới dạng command-line argument có thể bị ghi lại trong process list/logs. CI nên dùng workload identity, KMS/HSM hoặc secret manager được tổ chức phê duyệt.

## 7. Ký JAR bằng JDK jarsigner

JDK cung cấp `jarsigner` để ký và xác minh JAR. Công cụ này cập nhật manifest và thêm các file chữ ký vào `META-INF`, thường gồm `.SF` và signature block `.RSA`, `.DSA` hoặc `.EC`.

### 7.1. Chuẩn bị certificate/keystore

Trong lab có thể tạo keystore PKCS12 và certificate thử nghiệm:

~~~bash
keytool -genkeypair \
  -alias release-signing \
  -keyalg RSA \
  -keysize 3072 \
  -validity 365 \
  -storetype PKCS12 \
  -keystore release.p12
~~~

Lệnh sẽ hỏi mật khẩu và thông tin certificate. Certificate tự ký phù hợp để học cú pháp, **không tự tạo trust cho người nhận**. Production cần certificate chain/trust anchor được tổ chức chấp thuận hoặc key được quản lý trong HSM/KMS.

### 7.2. Ký JAR

~~~bash
jarsigner \
  -keystore release.p12 \
  -storetype PKCS12 \
  -signedjar app-signed.jar \
  build/libs/app.jar \
  release-signing
~~~

Nếu không truyền password trên command line, tool có thể yêu cầu nhập tương tác. Với CI, sử dụng phương thức secret/key provider an toàn được JDK và tổ chức hỗ trợ; không hardcode mật khẩu trong script.

### 7.3. Verify JAR đã ký

~~~bash
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

Đọc toàn bộ warnings. `-strict` khiến severe warnings trở thành lỗi theo quy tắc của jarsigner. Thành công về mặt cryptographic signature không có nghĩa certificate self-signed đã được người nhận tin cậy; cần kiểm chain, signer identity, validity, timestamp và policy.

### 7.4. JAR signing ký những gì?

JAR signing ghi digest cho các entries trong archive và ký signature file. Nó kiểm tra các entries đã ký không bị thay đổi và signature được tạo bởi private key tương ứng certificate. Đây là cơ chế hữu ích khi hệ thống phân phối/loader có hỗ trợ JAR signatures.

Nhưng JAR signing khác với ký toàn bộ file blob:

- `jarsigner` xác minh các entries và manifest theo JAR signing specification.
- Cosign `sign-blob` ký payload của toàn bộ file artifact dưới dạng blob và giữ bundle ngoài file.
- JAR signature không mô tả source commit, build runner hoặc dependency graph.
- JAR signature không ký OCI image manifest/layers.

Với Spring Boot executable JAR, hãy hoàn thành Gradle `bootJar` hoặc Maven `repackage` trước khi ký. Không sửa/repackage JAR sau khi ký; chạy smoke test trên **chính file đã ký** và xác minh bằng JDK/runtime mà hệ thống đích dùng. Nếu mục tiêu là xác minh nguyên vẹn toàn bộ bytes của release file, có thể dùng thêm SHA-256 và Cosign blob signature.

## 8. Sigstore Cosign: ký một file JAR như blob

Cosign có thể ký file thông thường, không chỉ container image. Với keyless signing, Cosign dùng OpenID Connect để xác thực identity; Sigstore Fulcio cấp certificate ngắn hạn gắn với ephemeral public key và Rekor ghi nhận sự kiện vào transparency log. Bundle giúp consumer giữ signature, certificate và proof cần để verify.

### 8.1. Ký blob keyless

Sau khi cài Cosign và đã xác thực OIDC:

~~~bash
cosign sign-blob --bundle app.jar.sigstore.json build/libs/app.jar
~~~

Trong môi trường tương tác, Cosign có thể yêu cầu đăng nhập OIDC. Trong CI, workload identity/OIDC provider phải được cấu hình đúng. `app.jar.sigstore.json` là verification bundle, không phải file JAR đã được sửa.

Sigstore transparency log có thể tạo bản ghi công khai về digest và identity ký. Trước khi ký artifact nội bộ/nhạy cảm, kiểm tra chính sách công khai metadata của tổ chức.

### 8.2. Verify blob bằng identity được cho phép

~~~bash
cosign verify-blob \
  --bundle app.jar.sigstore.json \
  --certificate-identity "$SIGNER_IDENTITY" \
  --certificate-oidc-issuer "$OIDC_ISSUER" \
  build/libs/app.jar
~~~

`SIGNER_IDENTITY` và `OIDC_ISSUER` phải được lấy từ policy release thực tế, ví dụ identity của CI workflow cụ thể và issuer tương ứng. Không đặt wildcard rộng như `.*` trong production policy nếu mục tiêu là chỉ chấp nhận một workflow phát hành được phê duyệt.

Nếu bundle thiếu, file thay đổi hoặc identity/issuer không khớp, verification phải fail. Không bỏ qua lỗi bằng cách tắt claim checking trong release gate.

### 8.3. Key-based blob signing

Khi dùng key pair quản lý riêng:

~~~bash
cosign generate-key-pair
cosign sign-blob \
  --key cosign.key \
  --bundle app.jar.sigstore.json \
  build/libs/app.jar
~~~

Consumer xác minh bằng public key được phân phối qua trust channel:

~~~bash
cosign verify-blob \
  --key cosign.pub \
  --bundle app.jar.sigstore.json \
  build/libs/app.jar
~~~

`cosign.key` phải được bảo vệ và không được publish. Với production, ưu tiên KMS/HSM hoặc secret manager thay cho private key file nằm lâu trên CI worker. Nếu dùng key-based signing, quản lý public key rotation và quy trình thu hồi key rõ ràng.

## 9. Ký OCI container image bằng digest

Khi ứng dụng được đóng gói thành OCI image, cần ký **image digest** thay vì chỉ ghi nhận tag mutable như `:latest` hoặc `:1.2.3`.

Tag có thể được registry trỏ sang image khác. Digest xác định manifest content cụ thể. Consumer nên pull/verify/deploy đúng reference:

~~~text
registry.example.com/team/jvm-compat-demo@sha256:<digest-thực>
~~~

Chuỗi trên mô tả định dạng; thay bằng digest thực được registry trả về. Không tự tạo digest.

### 9.1. Push image rồi resolve digest

Ví dụ tag release:

~~~bash
IMAGE_TAG=registry.example.com/team/jvm-compat-demo:1.0.0
~~~

Sau khi CI push image, dùng công cụ registry phù hợp (ví dụ `crane`) để resolve digest:

~~~bash
crane digest "$IMAGE_TAG"
~~~

Tạo image reference theo digest từ kết quả thật. Ví dụ shell:

~~~bash
IMAGE_DIGEST="$(crane digest "$IMAGE_TAG")"
IMAGE_REF="registry.example.com/team/jvm-compat-demo@$IMAGE_DIGEST"
~~~

Không ký tag trước khi biết artifact cuối cùng đã được push và digest cố định. Nếu registry hoặc tool trả digest khác, kiểm tra manifest/architecture/index và chọn đúng image reference cần phát hành.

### 9.2. Ký image keyless bằng Cosign

~~~bash
cosign sign "$IMAGE_REF"
~~~

Cosign dùng OIDC identity flow trong môi trường hỗ trợ và lưu signature liên kết với digest của image trong registry theo cơ chế OCI referrers/registry support phù hợp.

### 9.3. Verify image signature

~~~bash
cosign verify "$IMAGE_REF" \
  --certificate-identity "$SIGNER_IDENTITY" \
  --certificate-oidc-issuer "$OIDC_ISSUER"
~~~

Cosign kiểm signature, certificate identity/issuer và claim digest. Consumer vẫn cần policy để xác nhận đúng workflow, repository, tag/ref và tổ chức được phép phát hành. Một image được ký bởi một tài khoản không được phê duyệt không trở thành trusted image.

### 9.4. Key-based image signing

~~~bash
cosign sign --key cosign.key "$IMAGE_REF"
cosign verify --key cosign.pub "$IMAGE_REF"
~~~

Với registry, signature được lưu như artifact/referrer nếu registry hỗ trợ. Nếu registry cũ hoặc hạn chế OCI referrers, xem compatibility guidance của Cosign và registry; không mặc định mọi registry lưu chữ ký giống nhau.

**Không làm:** build image mới rồi ghi đè cùng tag nhưng tiếp tục dùng signature của digest cũ. Hãy resolve digest, sign digest mới, verify digest mới và deploy đúng digest đó.

## 10. Provenance theo SLSA/in-toto

SLSA provenance là attestation mô tả **artifact được tạo từ đâu và bằng quy trình nào**. Trong SLSA provenance v1, các phần quan trọng gồm:

- `subject` trong in-toto Statement: artifact đầu ra, được nhận diện bằng digest.
- `predicateType`: URI chuẩn `https://slsa.dev/provenance/v1`.
- `buildDefinition`: build type, external parameters và resolved dependencies.
- `runDetails`: builder identity, thông tin lần chạy và dữ liệu liên quan.
- `resolvedDependencies`: các artifact cần cho build, nếu builder thu thập được.

Provenance trả lời câu hỏi như: image này được build từ repository nào, commit nào, bằng builder/workflow nào, với parameters/dependencies nào và output digest nào?

### 10.1. Predicate minh họa

Đây là **mẫu cấu trúc để hiểu các trường**, không phải provenance thực và không chứng minh SLSA level. Giá trị phải do build platform đáng tin ghi nhận:

~~~json
{
  "buildDefinition": {
    "buildType": "https://ci.example.org/buildtypes/gradle-spring-boot/v1",
    "externalParameters": {
      "repository": "https://git.example.org/team/jvm-compat-demo",
      "gitRef": "refs/tags/v1.0.0",
      "gitCommit": "FULL_COMMIT_SHA_FROM_CI",
      "entryPoint": "./gradlew clean test bootJar"
    },
    "resolvedDependencies": []
  },
  "runDetails": {
    "builder": {
      "id": "https://ci.example.org/builders/release-v1"
    },
    "metadata": {
      "invocationId": "ci://jvm-compat-demo/release/12345",
      "startedOn": "2026-11-09T02:00:00Z",
      "finishedOn": "2026-11-09T02:04:00Z"
    }
  }
}
~~~

Trong release thật, `gitCommit` phải là commit SHA thực, `builder.id` phải nhận diện builder được phê duyệt, invocation ID phải trỏ về lần chạy có thể audit, thời gian phải lấy từ CI, và resolved dependencies phải đầy đủ theo mức bảo đảm mà builder cam kết. Không dùng các chuỗi minh họa ở trên làm claim release.

### 10.2. Attest SLSA provenance cho OCI image

Khi đã có predicate do build platform tạo, Cosign có thể đính kèm và ký attestation:

~~~bash
cosign attest \
  --type slsaprovenance1 \
  --predicate provenance.json \
  "$IMAGE_REF"
~~~

`slsaprovenance1` là type alias của Cosign cho SLSA provenance v1. Cosign tạo in-toto statement với subject gắn với image được chỉ định, ký attestation và lưu vào registry theo cơ chế hỗ trợ.

**Cảnh báo về trust:** lệnh Cosign ký dữ liệu được đưa vào; nó không tự xác minh rằng nội dung provenance là sự thật. Nếu developer tự viết JSON và ký bằng tài khoản cá nhân, ta chỉ chứng minh người đó ký claim ấy. Muốn provenance có giá trị supply-chain, hãy lấy dữ liệu từ CI/build platform được tin cậy, kiểm builder identity và không cho build script tùy ý giả mạo những trường do platform kiểm soát.

### 10.3. Verify attestation và signer identity

~~~bash
cosign verify-attestation \
  --type slsaprovenance1 \
  --certificate-identity "$SIGNER_IDENTITY" \
  --certificate-oidc-issuer "$OIDC_ISSUER" \
  "$IMAGE_REF"
~~~

Lệnh kiểm tra attestation signature/identity/type cho image. Sau đó consumer phải đọc payload và áp dụng policy đối với:

- Subject digest có đúng image đang định deploy không?
- Source repository và commit có được phép không?
- Git ref có phải release tag/branch được phê duyệt không?
- Builder ID có thuộc CI platform tin cậy không?
- Build type/parameters có đúng release workflow không?
- Invocation ID có tồn tại và tương ứng log/record CI không?
- Dependencies/builder inputs có nằm trong policy không?

Chỉ verify cryptographic signature mà không kiểm các claims quan trọng có thể chấp nhận một provenance được ký hợp lệ nhưng trỏ tới repository hoặc workflow sai.

## 11. SBOM: inventory đi cùng artifact

SBOM cho biết thành phần nào nằm trong artifact/image, ví dụ:

- Spring Boot libraries, embedded server và transitive dependencies.
- Java runtime, OS packages và native libraries trong OCI image.
- Version, package identifiers, license và dependency relationships theo format hỗ trợ.

Các định dạng phổ biến gồm SPDX và CycloneDX. Ví dụ tạo SPDX JSON cho image bằng Syft (nếu đã cài và version được pin):

~~~bash
syft "$IMAGE_REF" -o spdx-json > sbom.spdx.json
~~~

Gắn SBOM như một attestation:

~~~bash
cosign attest \
  --type spdxjson \
  --predicate sbom.spdx.json \
  "$IMAGE_REF"
~~~

Kiểm tra attestation theo type phù hợp:

~~~bash
cosign verify-attestation \
  --type spdxjson \
  --certificate-identity "$SIGNER_IDENTITY" \
  --certificate-oidc-issuer "$OIDC_ISSUER" \
  "$IMAGE_REF"
~~~

Đảm bảo SBOM được tạo từ **chính image digest đang ký**, không phải từ source tree trước khi đóng image. SBOM giúp scanner tra CVE/license; nó không khẳng định mọi component an toàn hoặc provenance đúng.

## 12. Gradle dependency verification: bảo vệ thư viện đầu vào

Gradle có dependency verification thông qua file:

~~~text
gradle/verification-metadata.xml
~~~

File này giúp Gradle xác minh checksums và/hoặc chữ ký PGP của dependencies/plugins được resolve. Đây là **kiểm tra artifact đầu vào của build**, không phải ký JAR ứng dụng vừa sinh ra.

Tạo baseline metadata (sau khi resolve từ repository đã được kiểm tra):

~~~bash
./gradlew --write-verification-metadata sha256
~~~

Khi các thư viện có PGP signatures và team muốn lưu cả checksum lẫn signature metadata:

~~~bash
./gradlew --write-verification-metadata sha256,pgp
~~~

Sau khi tạo:

1. Review toàn bộ `verification-metadata.xml`.
2. Kiểm checksum/signature/key của dependencies quan trọng qua nguồn chính thức độc lập.
3. Commit file metadata cùng build configuration.
4. Khi dependency version thay đổi, review diff và cập nhật có chủ đích.
5. Đảm bảo CI build fail nếu artifact không khớp metadata.

Gradle hỗ trợ SHA-256/SHA-512 cho checksum hiện đại; không dùng MD5/SHA-1 làm trust anchor mới. Signature PGP chỉ có ý nghĩa khi key được tin cậy. Bootstrapping metadata từ repository đang dùng có giới hạn: nếu repository đã bị compromise, checksum được sinh từ artifact độc hại cũng có thể bị ghi vào baseline. Review là bắt buộc.

Gradle dependency verification không bao gồm local artifacts được tạo trong build và có giới hạn với changing dependencies như SNAPSHOT. Vì vậy vẫn cần checksum/signature/provenance **riêng cho sản phẩm phát hành**.

## 13. Maven: checksum repository, chữ ký và artifact release

Maven repository lưu JAR, POM, metadata và có thể kèm checksum/signature files. Maven Deploy Plugin chịu trách nhiệm upload artifact và các file liên quan theo repository deployment workflow. Tuy nhiên:

- Sidecar checksum từ cùng repository giúp phát hiện lỗi/truyền tải, nhưng nếu cả JAR và checksum bị thay thế thì nó không tự xác thực publisher.
- Checksum algorithms/policy phụ thuộc repository manager và cấu hình; đừng mặc định một file `.sha1` hoặc `.md5` là mức bảo vệ hiện đại.
- Detached PGP signature `.asc` cần được verify với public key/trust policy đã xác nhận.
- JAR signing bằng `jarsigner` là một cơ chế khác, ký các entries trong archive.
- Cosign blob signature có thể ký toàn bộ JAR bytes và giữ bundle bên ngoài.

Một quy trình Maven release có thể:

~~~bash
mvn clean verify
mvn package
sha256sum target/app.jar > app.jar.sha256
~~~

Sau đó ký file cuối cùng bằng `jarsigner` hoặc Cosign, rồi publish artifact, checksum và signature/bundle trong repository/release storage. Dùng release profile/plugin signing đã được tổ chức cấu hình; không hardcode private key/password vào POM.

Với dependency inputs, Maven Resolver/repository checksum policy và signature verification cần được cấu hình rõ. Đừng nhầm checksum sidecar tự động được repository tạo với một chữ ký số xác thực identity của nhà phát hành.

## 14. Một workflow end-to-end cho Spring Boot

Giả sử CI tạo:

- Gradle: `build/libs/app.jar` từ task `bootJar`.
- Maven: `target/app.jar` sau goal `repackage`.
- Container image: `registry.example.com/team/app:1.0.0`.

### 14.1. Build và test

Gradle:

~~~bash
./gradlew clean test bootJar
~~~

Maven:

~~~bash
mvn clean verify
~~~

Chỉ tiếp tục khi test gate thành công và file executable đúng đã được tạo. Không ký artifact trung gian hoặc plain JAR.

### 14.2. Kiểm artifact và tạo checksum

~~~bash
sha256sum build/libs/app.jar > app.jar.sha256
sha256sum --check app.jar.sha256
~~~

Lưu checksum manifest cùng release và đưa digest vào release metadata/provenance. Nếu artifact bị ký lại bằng jarsigner, tạo checksum mới sau khi JAR signing hoàn tất.

### 14.3. Ký JAR

Một trong hai lựa chọn:

- `jarsigner` khi consumer cần JAR entry signatures và có trust/certificate policy tương ứng.
- Cosign `sign-blob` khi muốn ký toàn bộ file bytes bằng Sigstore bundle/keyless hoặc key/KMS.

Không cần tự động dùng cả hai nếu policy chỉ yêu cầu một cơ chế; nếu dùng cả hai, định nghĩa rõ mục đích và thứ tự.

### 14.4. Tạo image và lấy digest

Build/push image qua CI. Sau push, resolve immutable digest từ registry, ví dụ bằng `crane digest`. Lưu cả tag release và digest:

~~~text
tag:    registry.example.com/team/app:1.0.0
digest: registry.example.com/team/app@sha256:<digest-thực>
~~~

Ký và attest theo digest reference, không chỉ theo tag.

### 14.5. Ký image và đính kèm provenance/SBOM

~~~bash
cosign sign "$IMAGE_REF"

cosign attest \
  --type slsaprovenance1 \
  --predicate provenance.json \
  "$IMAGE_REF"

cosign attest \
  --type spdxjson \
  --predicate sbom.spdx.json \
  "$IMAGE_REF"
~~~

Trong CI, OIDC identity phải thuộc workflow release được phép. Provenance và SBOM phải được tạo từ cùng lần build/digest; không reuse attestation từ image khác chỉ vì tag giống nhau.

### 14.6. Verify trước publish/deploy

~~~bash
cosign verify "$IMAGE_REF" \
  --certificate-identity "$SIGNER_IDENTITY" \
  --certificate-oidc-issuer "$OIDC_ISSUER"

cosign verify-attestation \
  --type slsaprovenance1 \
  --certificate-identity "$SIGNER_IDENTITY" \
  --certificate-oidc-issuer "$OIDC_ISSUER" \
  "$IMAGE_REF"

cosign verify-attestation \
  --type spdxjson \
  --certificate-identity "$SIGNER_IDENTITY" \
  --certificate-oidc-issuer "$OIDC_ISSUER" \
  "$IMAGE_REF"
~~~

Sau verify, kiểm claims theo policy: repo, commit, ref, builder, invocation và subject digest. Deploy **cùng digest đã verify**, không resolve tag lại rồi vô tình kéo image khác.

## 15. Reproducible build và traceability

Reproducible build là khả năng dựng lại artifact có bytes giống nhau từ cùng source, build instructions và môi trường đã xác định. Điều này giúp so sánh độc lập artifact với release candidate.

Maven có property `project.build.outputTimestamp` và các plugin hỗ trợ reproducible archive. Gradle có archive tasks với cấu hình timestamp/file order có thể tái lập. Tuy nhiên:

- Reproducible không tự chứng minh source đáng tin.
- Non-reproducible không tự chứng minh có tấn công; timestamps, absolute paths, generated files và tool versions có thể làm output khác.
- Build-info/version/Git SHA bên trong JAR không thay provenance có chữ ký.
- Signature chỉ ký đúng artifact đã tạo; nếu rebuild ra bytes khác, digest/signature cũng khác.

Để truy vết tốt, ghi nhận:

- Source repository URL, commit SHA và release tag.
- Gradle wrapper/Maven/plugin versions, Java toolchain.
- Dependency locks/verification metadata và resolved dependency set.
- Builder image/CI workflow identity/version.
- Build invocation ID, timestamps và external parameters.
- Output JAR digest, OCI image digest và architecture.
- Signer identity, certificate issuer, signature bundle/transparency log evidence.
- SBOM, scan results và release approval.
- Digest thực tế được deploy vào từng môi trường.

Không ghi secrets, private keys, repository passwords, access tokens hoặc thông tin cá nhân không cần thiết vào provenance/SBOM/build-info. Các attestation công khai có thể tiết lộ source URLs, workflow identity, commit SHA và metadata build.

## 16. Quy tắc xác minh và fail closed

Một release consumer nên từ chối artifact nếu một điều kiện bắt buộc không đạt:

1. Checksum không khớp digest tham chiếu.
2. Signature không hợp lệ hoặc signer không nằm trong trust policy.
3. OIDC issuer/identity không khớp release workflow được phê duyệt.
4. Image signature gắn với digest khác image đang pull.
5. Provenance thiếu subject/output digest hoặc subject không khớp artifact.
6. Source repository, commit, tag hoặc builder ID không được phép.
7. Provenance được ký bởi identity không đủ quyền tạo release.
8. SBOM/scan policy bắt buộc nhưng thiếu hoặc không đạt.
9. Attestation không đọc được hoặc không xác minh được transparency evidence theo policy.

Không hạ policy xuống “warn only” trong production để build tiếp. Khi thiếu metadata do hệ thống release lỗi, dừng publish/deploy, điều tra và tạo lại artifact/attestation theo quy trình.

### 16.1. Verify chữ ký khác verify policy

`cosign verify` xác minh signature và image claims. `cosign verify-attestation` xác minh attestation signature/claims. Nhưng policy còn phải kiểm **nội dung predicate**: source repo có đúng không, builder có được tin không, commit/ref có đúng release không. Có thể dùng CUE/Rego policy với Cosign hoặc admission controller để enforce tại cluster.

### 16.2. Đừng verify bằng public key do artifact tự cung cấp

Public key/certificate nằm trong bundle có thể giúp xác minh toán học chữ ký, nhưng trust phải đến từ policy ngoài artifact: approved issuer/identity, trusted root, pinned public key/KMS identity hoặc tổ chức phát hành. Nếu attacker tự tạo key và ký artifact của họ, phép verify với public key do attacker cung cấp vẫn có thể pass nhưng không làm artifact trở nên trusted.

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| SHA-256 mismatch | File đổi, tải hỏng, nhầm version/path | Lấy artifact/digest từ nguồn tin cậy, không tự sửa sidecar |
| Checksum và file cùng thay đổi | Digest lấy từ cùng nguồn không tin cậy | Xác minh qua signed manifest hoặc trusted channel |
| Cosign blob verify fail | File khác bytes, bundle sai hoặc signer identity không khớp | Kiểm exact file, bundle, issuer và identity |
| Cosign image verify fail | Image digest khác, signature chưa publish hoặc registry không hỗ trợ | Resolve digest, kiểm registry/referrers và signing output |
| Chữ ký hợp lệ nhưng signer lạ | Public key/certificate không nằm trong trust policy | Từ chối signer, kiểm certificate identity/issuer |
| JAR signature warning | Certificate chain, timestamp, algorithm hoặc trust store có vấn đề | Đọc warnings với `-strict`, kiểm chain/algorithm/time |
| `jarsigner` pass nhưng JAR runtime fail | JAR bị thay đổi sau ký hoặc packaging/loader issue | Verify artifact cuối, chạy smoke test chính signed JAR |
| Gradle dependency verification fail | Dependency mới hoặc checksum/signature thay đổi | Điều tra nguồn, review metadata rồi mới cập nhật |
| Gradle verification bootstrap pass nhưng dependency độc hại | Baseline được tạo từ repository đã bị compromise | Đối chiếu checksum/key với nguồn độc lập |
| Maven checksum sidecar thiếu | Repository policy/transport không cung cấp file mong đợi | Kiểm repository manager policy, không bỏ qua integrity check |
| Provenance subject digest mismatch | Attestation cho image khác hoặc artifact thay đổi sau build | Tạo lại provenance cho đúng digest |
| Provenance có source repo sai | Builder/CI external parameters sai hoặc claim tự khai | Dùng provenance từ trusted builder, enforce policy |
| SBOM không có component mong đợi | SBOM tạo từ source hoặc image khác | Generate từ exact final image digest |
| Image tag trỏ sang image mới | Tag mutable bị ghi đè | Verify và deploy digest, không deploy lại theo tag |
| Private signing key bị lộ | Key nằm trong repo/logs/runner | Thu hồi/rotate, audit signatures, chuyển sang KMS/HSM |
| Signature bundle thất lạc | Chỉ publish artifact mà không lưu verification material | Publish bundle/OCI referrer cùng release và backup metadata |

## 18. Bài tập thực hành có đáp án

### Bài 1 — Checksum có chứng minh publisher?

Một JAR có checksum SHA-256 đúng với file `app.jar.sha256` tải cùng server. Có thể khẳng định JAR do công ty phát hành không?

**Đáp án:** chưa. Checksum chỉ chứng minh file khớp digest sidecar. Cần digest được ký hoặc lấy từ nguồn độc lập đáng tin, và cần xác minh signer identity.

### Bài 2 — JAR bị đổi một byte

Sau khi ký JAR bằng `jarsigner`, một người sửa resource trong archive. Kết quả verify?

**Đáp án:** verification của entry đã ký phải fail vì digest entry không khớp. Kiểm lại bằng `jarsigner -verify -strict -verbose -certs`.

### Bài 3 — Gradle verification

**Câu hỏi:** `gradle/verification-metadata.xml` kiểm tra file nào?

**Đáp án:** các dependencies/plugins/metadata được Gradle dependency engine resolve theo verification metadata. Nó không tự ký local Spring Boot JAR do build tạo; artifact release cần checksum/signature riêng.

### Bài 4 — Cosign keyless

**Câu hỏi:** keyless signing không dùng private key dài hạn, vậy có cần kiểm danh tính không?

**Đáp án:** có. Verify phải kiểm OIDC issuer và certificate identity đúng workflow/repository được phép; một identity bất kỳ không đủ.

### Bài 5 — Tag và digest

**Câu hỏi:** image `app:1.0.0` được ký, nhưng registry tag sau đó trỏ sang image khác. Consumer nên deploy gì?

**Đáp án:** resolve và verify image digest cụ thể, rồi deploy đúng digest đó. Tag chỉ là tên tham chiếu có thể thay đổi.

### Bài 6 — Provenance tự khai

**Câu hỏi:** developer tạo JSON ghi commit và builder rồi dùng Cosign ký bằng key cá nhân. Có thể tuyên bố build provenance được xác thực bởi trusted builder không?

**Đáp án:** không. Chữ ký xác thực người ký JSON; nó không chứng minh builder thực sự chạy build. Provenance cần được sinh bởi build platform tin cậy và policy phải kiểm builder identity/subject.

### Bài 7 — SBOM và vulnerability

**Câu hỏi:** image có SBOM được ký hợp lệ. Có thể kết luận image không có CVE?

**Đáp án:** không. SBOM là inventory; phải chạy vulnerability scanner với database/policy phù hợp và kiểm kết quả theo thời điểm phát hành.

### Bài 8 — Thứ tự ký và checksum

**Câu hỏi:** checksum được tạo trước khi `jarsigner` thêm signature files. Sau khi ký, sidecar cũ có còn khớp không?

**Đáp án:** không. JAR đã thay đổi bytes; phải tính checksum và Cosign blob signature trên signed JAR cuối cùng.

### Bài 9 — Provenance subject

**Câu hỏi:** attestation được ký nhưng subject digest không khớp image đang deploy. Có chấp nhận không?

**Đáp án:** không. Attestation đang mô tả artifact khác; phải từ chối và tìm provenance đúng digest.

### Bài 10 — Artifact không reproducible

**Câu hỏi:** hai lần build cùng commit cho checksum khác nhau. Có kết luận bị tấn công không?

**Đáp án:** chưa. Điều tra timestamps, archive ordering, tool versions, environment và generated metadata. Reproducibility hỗ trợ kiểm tra độc lập nhưng checksum khác nhau tự nó không xác định nguyên nhân.

## 19. Checklist trước khi publish

- [ ] Build đúng executable Boot JAR; test gate đã pass.
- [ ] Artifact cuối có tên/version/path xác định, không nhầm plain JAR.
- [ ] SHA-256 hoặc SHA-512 được tính sau mọi thao tác làm thay đổi file.
- [ ] Digest được công bố qua signed manifest hoặc trusted channel độc lập.
- [ ] Nếu dùng jarsigner, certificate chain, timestamp, algorithm và warnings đã được review.
- [ ] Nếu dùng Cosign blob, bundle được lưu cùng artifact và identity/issuer được kiểm.
- [ ] OCI image được resolve thành digest và signature gắn với đúng digest.
- [ ] Provenance được tạo bởi trusted builder, subject digest khớp artifact/image.
- [ ] Policy kiểm repository, commit/ref, builder ID, invocation và external parameters.
- [ ] SBOM được tạo từ exact final image/artifact và được scan.
- [ ] Gradle dependency verification hoặc Maven dependency policy bảo vệ dependencies đầu vào.
- [ ] Private signing key không nằm trong Git, build logs, image hoặc artifact; KMS/HSM/secret manager được dùng khi phù hợp.
- [ ] Artifact, checksum, signature bundle, provenance và SBOM được lưu cùng release record có thể audit.
- [ ] Consumer xác minh trước khi publish/deploy; lỗi verification làm release gate fail.
- [ ] Deployment sử dụng image digest đã xác minh, không resolve lại mutable tag.
- [ ] Không đưa secrets hoặc dữ liệu nội bộ không cần thiết vào public attestations.

**Kết luận:** checksum cho biết bytes có khớp digest tham chiếu; chữ ký cho biết ai ký nội dung theo một trust policy; provenance cho biết artifact được tạo từ source/builder/inputs nào; SBOM cho biết sản phẩm chứa những gì. Với Spring Boot, hãy build và test JAR cuối cùng, tạo SHA-256, ký JAR/blob hoặc OCI image bằng signer được tin cậy, đính kèm provenance/SBOM gắn với digest, rồi verify identity và claims trước khi phát hành. Không có một file checksum hay một chữ ký riêng lẻ nào thay thế toàn bộ chuỗi kiểm soát đó.

## 20. Tài liệu chính thức

- Gradle — Dependency Verification (checksums, signatures, `verification-metadata.xml`): https://docs.gradle.org/current/userguide/dependency_verification.html
- Sigstore — Cosign Quickstart: https://docs.sigstore.dev/quickstart/quickstart-cosign/
- Sigstore — Signing Blobs: https://docs.sigstore.dev/cosign/signing/signing_with_blobs/
- Sigstore — Signing Containers: https://docs.sigstore.dev/cosign/signing/signing_with_containers/
- Sigstore — Verifying Signatures: https://docs.sigstore.dev/cosign/verifying/verify/
- Sigstore — In-Toto Attestations: https://docs.sigstore.dev/cosign/verifying/attestation/
- Sigstore — Security Model (Fulcio, OIDC, Rekor): https://docs.sigstore.dev/about/security/
- SLSA — Build Provenance v1: https://slsa.dev/spec/v1.1/provenance
- Apache Maven — Deploy Plugin: https://maven.apache.org/plugins/maven-deploy-plugin/
- Apache Maven — Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Java SE 17 — jarsigner command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html
- Java SE 17 — MessageDigest API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html
- Java SE 17 — HexFormat API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html

Các cú pháp CLI, predicate aliases và registry referrer support có thể thay đổi theo Cosign/Pack/Maven/Gradle version. Trước khi đưa vào release pipeline, pin tool versions, kiểm `--help`/docs đúng phiên bản và chạy thử verification trên chính artifact digest được phát hành.