# Ký artifact và release – Bảo vệ tính toàn vẹn chuỗi phát hành phần mềm

**Ký artifact và release (artifact/release signing)** là việc tạo **chữ ký số** cho một gói phần mềm hoặc một tập thông tin mô tả bản phát hành, để bên nhận kiểm tra rằng dữ liệu phát hành không bị thay đổi ngoài ý muốn và chữ ký được tạo bởi khóa ký được chính sách tin cậy chấp nhận. Artifact có thể là **JAR/WAR**, thư viện, tập tin thực thi, gói cài đặt, archive, bản cập nhật, **container image** hoặc manifest mô tả nhiều tệp trong một bản release.

Trong chương **Chữ ký số** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài này nối chữ ký số với toàn bộ vòng đời khóa **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy**. Một pipeline an toàn cần phối hợp mật mã bất đối xứng, hàm băm, KMS/HSM, mã hóa đối xứng khi lưu bí mật, envelope encryption khi cần bảo vệ dữ liệu, phân quyền CI/CD và nhật ký kiểm toán.

> **Nguyên tắc cốt lõi:** Chữ ký hợp lệ chứng minh artifact hoặc manifest khớp với dữ liệu được ký **bởi khóa mà bên xác minh tin cậy**. Nó **không tự chứng minh mã nguồn không có lỗ hổng, quy trình build không bị xâm nhập, người ký có quyền phát hành hay phiên bản đó là phiên bản mới nhất**. Các bảo đảm này cần chính sách, bằng chứng và kiểm tra bổ sung.

## 1. Vì sao cần ký artifact và release?

Một artifact thường trải qua nhiều bước: biên dịch, đóng gói, upload registry, đồng bộ CDN, tải về, triển khai hoặc cập nhật. Nếu chỉ tin vào tên tệp hoặc kênh tải, hệ thống có thể gặp các rủi ro:

1. **Thay thế artifact:** kẻ tấn công tráo `app.jar`, image hoặc bộ cài trên kho lưu trữ, đường truyền hay máy phân phối.
2. **Sửa đổi nội dung:** một bản phát hành bị thêm mã độc hoặc thay cấu hình sau khi build.
3. **Giả mạo bản phát hành:** artifact được ký bằng một khóa tùy ý nhưng được quảng bá là bản chính thức.
4. **Nhầm build hoặc môi trường:** bản build thử nghiệm được đẩy vào kênh production do dùng tên/version giống nhau.
5. **Rollback/downgrade:** một release cũ từng có chữ ký hợp lệ được đưa vào triển khai dù chính sách chỉ cho phép phiên bản mới hơn.
6. **Tấn công pipeline:** CI runner, dependency, workflow hoặc danh tính ký bị chiếm quyền và tạo ra artifact độc hại **được ký thật**.
7. **Rò rỉ private key:** kẻ tấn công dùng khóa phát hành để ký artifact giả mà không cần xâm nhập repository.

**Chữ ký số trực tiếp xử lý tính toàn vẹn và tính xác thực của chữ ký theo khóa tin cậy.** Muốn đối phó các trường hợp còn lại phải phối hợp bảo vệ nguồn mã, CI/CD, kho artifact, danh tính người ký, danh sách phiên bản được phép và lịch sử phát hành.

## 2. Các thành phần của một release được ký

| Thành phần | Mục đích | Lưu ý |
| --- | --- | --- |
| **Artifact** | Nội dung phần mềm được phân phối: JAR, binary, image, archive... | Phải xác định chính xác **bytes** hoặc **digest** được bảo vệ. |
| **Digest / checksum mật mã** | Giá trị băm, thường là SHA-256, đại diện cho đúng bytes của artifact. | Ai cũng tính được checksum; một checksum tự nó **không xác thực nhà phát hành**. |
| **Signature** | Chữ ký được tạo bằng private key trên dữ liệu đã xác định. | Có thể ký trực tiếp artifact hoặc ký một manifest chứa digest và metadata. |
| **Public key / certificate** | Dùng xác minh chữ ký. | Phải xác thực danh tính/nguồn tin cậy và điều kiện sử dụng; không lấy tùy ý từ chính gói không tin cậy. |
| **Manifest** | Liệt kê artifact, digest, phiên bản, kênh phát hành và ngữ cảnh. | Phải ký toàn bộ trường quan trọng hoặc ràng buộc bằng cơ chế tương đương. |
| **Attestation / provenance** | Bằng chứng có cấu trúc về nguồn mã, workflow, builder hoặc vật liệu đầu vào theo mô hình hỗ trợ. | Cũng cần xác thực **ai** đã phát hành bằng chứng và **điều gì** thực sự được chứng thực. |
| **Release policy** | Quy định thuật toán, khóa tin cậy, repo, workflow, tag/commit, kênh và phiên bản được phép. | Kiểm tra chữ ký hợp lệ chỉ là một điều kiện của policy. |

**Checksum + HTTPS chưa tương đương chữ ký phát hành.** HTTPS bảo vệ một kết nối theo mô hình tin cậy của TLS; checksum không khóa có thể bị thay nếu kẻ tấn công kiểm soát cùng nơi lưu cả artifact và checksum. Chữ ký với public key được phân phối tin cậy giúp người nhận xác minh gói ngay cả khi nhận từ một kho lưu trữ trung gian.

### 2.1. Ký tệp, ký digest hay ký manifest?

Có các mô hình triển khai khác nhau:

- **Ký trực tiếp bytes của artifact:** thuật toán chữ ký xử lý bytes theo giao diện của nó, có thể stream dữ liệu. Bên xác minh phải đọc đúng bytes và xác minh chữ ký.
- **Ký manifest chứa digest:** pipeline tính SHA-256 trên artifact, tạo một manifest có định dạng nhất quán rồi ký **bytes của manifest**. Bên nhận kiểm tra chữ ký manifest, sau đó tự tính SHA-256 của artifact và đối chiếu với digest được ký.
- **Chữ ký tích hợp theo định dạng gói:** các hệ sinh thái như JAR/package hoặc hệ thống ký mã có thể nhúng chữ ký và metadata theo một quy ước riêng.
- **Chữ ký tham chiếu artifact trong registry:** với OCI image, chữ ký có thể gắn với **image digest** và được lưu thành đối tượng liên quan theo công cụ/giao thức được hỗ trợ.

**Quan trọng:** “Ký checksum” phải có quy tắc rõ về bytes được ký, thuật toán băm, encoding (hex/base64/raw), tên tệp, phiên bản và miền ứng dụng. Không tự kết hợp các primitive rồi giả định rằng mọi phía sẽ xác minh cùng một dữ liệu.

## 3. Luồng ký và xác minh một bản release

~~~mermaid
flowchart TD
    SRC["Mã nguồn và dependency đã kiểm soát"] --> BUILD["CI build và kiểm tra"]
    BUILD --> A["Artifact bất biến"]
    A --> DIGEST["Tính SHA-256 trên đúng artifact"]
    DIGEST --> MANIFEST["Manifest: digest + version + channel + metadata"]
    MANIFEST --> SIGN["Sign manifest bằng private key release"]
    KMS["KMS/HSM + chính sách quyền Sign"] --> SIGN
    SIGN --> PUBLISH["Công bố artifact + manifest + signature"]
    A --> PUBLISH
    PUBLISH --> VERIFY["Bên nhận xác thực public key và Verify signature"]
    TRUST["Trust policy: signer, repo, channel, version"] --> VERIFY
    VERIFY --> MATCH["Tự tính digest artifact và đối chiếu manifest"]
    MATCH --> POLICY["Kiểm tra provenance, quyền phát hành, chống downgrade"]
    POLICY --> DEPLOY{"Tất cả điều kiện đạt?"}
    DEPLOY -->|Có| ACCEPT["Cho phép triển khai"]
    DEPLOY -->|Không| REJECT["Từ chối và ghi audit"]
~~~

Trong thực tế, bên nhận nên **xác minh chữ ký và chính sách trước khi sử dụng metadata chưa tin cậy để quyết định triển khai**. Hệ thống được phép đọc trường tối thiểu để tìm khóa trong danh sách đã cấu hình, nhưng không được coi `keyId`, URL lấy chứng chỉ hoặc tên thuật toán do artifact tự khai báo là nguồn tin cậy.

### 3.1. Release manifest cần chứa gì?

Một bản ghi manifest có thể có các trường dưới đây. Đây là **định dạng minh họa**, không phải một tiêu chuẩn phát hành có sẵn:

~~~yaml
schema: release-manifest-v1
project: billing-service
artifact: billing-service-1.4.2.jar
version: 1.4.2
channel: production
artifactSha256: "<64 hex characters calculated from the exact artifact>"
sourceCommit: "<immutable commit identifier>"
buildWorkflow: "<trusted workflow identifier>"
createdAt: "<RFC3339 timestamp>"
~~~

Nếu dùng định dạng cấu trúc như YAML hoặc JSON, **phải quy định canonical serialization** trước khi ký; cùng một cấu trúc có thể được biểu diễn bằng các chuỗi bytes khác nhau do thứ tự trường, khoảng trắng, Unicode hay số. Cách đơn giản hơn là ký một manifest được serialize theo một chuẩn cố định và xác minh **nguyên bytes** manifest đã xuất bản.

Các thông tin như `sourceCommit`, `buildWorkflow`, `createdAt` được ký để **phát hiện việc thay đổi tuyên bố**. Tuy nhiên, chữ ký chỉ xác nhận ai đã ký các tuyên bố đó; muốn biết builder có thực sự chạy đúng commit/workflow phải có **attestation/provenance từ nguồn đáng tin** và chính sách xác minh phù hợp.

### 3.2. Artifact nhiều tệp và nhiều kiến trúc

Một release có thể chứa JAR, file cấu hình mặc định, bản kê SBOM, container image cho nhiều kiến trúc CPU và checksum manifest. Khi đó cần:

- Liệt kê **đúng tập artifact** thuộc release, mỗi artifact có tên/phân loại và digest riêng.
- Ràng buộc **version, kênh, kiến trúc, nền tảng và mục đích** với digest đã ký.
- Xác định một **release identity** bất biến, tránh việc một gói bị tráo sang release khác nhưng vẫn còn chữ ký hợp lệ.
- Với container image, phân biệt **tag** (có thể bị gán lại) với **digest** định danh nội dung. Image đa kiến trúc có thể có **index/manifest list digest** và digest riêng từng manifest nền tảng; phải xác minh đúng đối tượng mà chính sách quy định.

Một chữ ký cho manifest tổng có thể bao phủ cả bộ phát hành **nếu** mọi digest liên quan được ràng buộc đầy đủ và consumer thực sự đối chiếu từng artifact trước khi dùng.

## 4. Các phương án ký trong hệ sinh thái phần mềm

| Phương án | Ví dụ | Điểm cần xác minh |
| --- | --- | --- |
| **Detached signature** | Tệp `artifact.sig` tách khỏi JAR/archive. | Phải ràng buộc signature với bytes/digest và public key tin cậy. |
| **JAR signing** | Cơ chế ký JAR bằng `jarsigner` hoặc công cụ tương ứng. | Verifier dùng cơ chế kiểm tra của định dạng JAR; đánh giá signer/chứng chỉ, cấu trúc và chính sách tin cậy, không chỉ đọc dòng thông báo “signed”. |
| **Gói/binary theo nền tảng** | Ký mã theo cơ chế của hệ điều hành, package manager hoặc repository. | Định dạng, chuỗi tin cậy, dấu thời gian và chính sách nền tảng. |
| **OCI image signing** | Chữ ký tham chiếu image digest, ví dụ qua công cụ ký ảnh tương thích OCI. | Xác minh đúng digest, signer identity và policy; không dựa vào tag có thể đổi. |
| **Signed release manifest** | Manifest nhiều artifact ký bằng Ed25519/ECDSA/RSA-PSS. | Mỗi digest đã ký phải được đối chiếu với bytes thật; kiểm tra release/channel/version. |
| **Signed attestation** | Bằng chứng nguồn build dưới định dạng chuẩn hóa, ví dụ in-toto/DSSE trong hệ sinh thái hỗ trợ. | Xác thực identity của attester, subject digest và nội dung tuyên bố; attestation không tự đồng nghĩa chất lượng code. |
| **Keyless signing** | Quy trình sử dụng danh tính workload OIDC để cấp chứng chỉ ngắn hạn cho khóa ký tạm thời. | Phải xác minh **issuer, subject, workflow identity, chứng chỉ, bằng chứng minh bạch nếu áp dụng và chính sách**; không chỉ kiểm tra rằng chữ ký khớp. |

**Ký bằng khóa lâu dài** và **keyless signing** có các cách quản lý khóa khác nhau, nhưng đều cần nguồn tin cậy và một chính sách verifier rõ ràng. Nếu công cụ sử dụng transparency log, log hỗ trợ kiểm toán và phát hiện sự kiện đáng ngờ; **việc có bản ghi trong log không tự chứng minh nội dung build an toàn**.

Các định dạng và API còn phụ thuộc hệ sinh thái. Không tự thay định dạng chữ ký detached bằng chữ ký JAR hoặc chữ ký OCI; mỗi verifier phải hiểu đúng loại artifact mà nó đang bảo vệ.

## 5. Thuật toán chữ ký số nào phù hợp?

| Thuật toán | Điểm mạnh | Cân nhắc |
| --- | --- | --- |
| **Ed25519** | Chữ ký và khóa công khai gọn; API ký/xác minh đơn giản khi hệ thống hỗ trợ. | Cần hỗ trợ giao thức và KMS/HSM; dùng đúng Ed25519, không nhầm với X25519. |
| **ECDSA P-256** | Có trong nhiều hệ thống PKI và công cụ ký. | Nonce mỗi lần ký phải an toàn hoặc dùng cơ chế được chuẩn hóa; định dạng chữ ký DER/raw dễ khác nhau. |
| **RSA-PSS** | Hữu ích khi cần tương thích RSA trong một giao thức hỗ trợ. | Ghim hash/MGF1/salt length, sử dụng kích thước khóa theo chính sách; tránh RSA thô. |

Không nên quyết định thuật toán chỉ dựa vào tên chữ ký “mạnh nhất”. Cần kiểm tra **khả năng xác minh trên tất cả môi trường triển khai**, tiêu chuẩn áp dụng, tuổi thọ release, hỗ trợ khóa trong KMS/HSM và phương án thay thuật toán về sau.

**Digest SHA-256 và thuật toán chữ ký là hai lựa chọn riêng.** Một manifest có thể chứa SHA-256 của artifact và được **Ed25519 ký trên toàn bộ manifest bytes**. Điều này không có nghĩa ứng dụng đã sử dụng biến thể Ed25519ph, cũng không có nghĩa phải băm manifest bằng SHA-256 thêm lần nữa trước khi gọi API Ed25519.

## 6. Ví dụ Java 17: ký manifest có SHA-256 và xác minh artifact

Ví dụ sau sinh một cặp khóa Ed25519 **trong bộ nhớ để học tập**, tính SHA-256 của artifact mô phỏng, ký **bytes manifest**, rồi xác minh cả chữ ký và digest của artifact. Bên nhận trong hệ thống thật phải có **public key/identity đã tin cậy từ trước**, không tạo key pair mới cùng lúc xác minh như ở demo.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.Signature;
import java.util.HexFormat;

public class ArtifactReleaseSigningDemo {
    private static String sha256Hex(byte[] bytes) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
        return HexFormat.of().formatHex(digest);
    }

    private static byte[] sign(byte[] bytes, KeyPair pair) throws Exception {
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(pair.getPrivate());
        signer.update(bytes);
        return signer.sign();
    }

    private static boolean verify(byte[] bytes, byte[] sig, KeyPair pair)
            throws Exception {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(pair.getPublic());
        verifier.update(bytes);
        return verifier.verify(sig);
    }

    // Demo có 5 dòng cố định. Production nên dùng định dạng canonical
    // đã chuẩn hóa, có parser giới hạn kích thước và chính sách tin cậy.
    private static String expectedSha256FromSignedManifest(byte[] manifest) {
        String value = new String(manifest, StandardCharsets.UTF_8);
        String prefix = "schema=release-v1\n" +
                "name=demo.jar\n" +
                "version=1.0.0\n" +
                "sha256=";
        String suffix = "\nchannel=production\n";

        if (!value.startsWith(prefix) || !value.endsWith(suffix)) {
            throw new IllegalArgumentException("Unexpected release metadata");
        }
        String hash = value.substring(
                prefix.length(), value.length() - suffix.length());
        if (!hash.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("Invalid SHA-256 field");
        }
        return hash;
    }

    public static void main(String[] args) throws Exception {
        // Demo dùng bytes trong bộ nhớ, chưa phải JAR có thật.
        byte[] artifact = "demo application binary v1"
                .getBytes(StandardCharsets.UTF_8);
        KeyPair pair = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();

        String digest = sha256Hex(artifact);
        byte[] manifest = ("schema=release-v1\n" +
                "name=demo.jar\n" +
                "version=1.0.0\n" +
                "sha256=" + digest + "\n" +
                "channel=production\n")
                .getBytes(StandardCharsets.UTF_8);
        byte[] signature = sign(manifest, pair);

        // Bên nhận: public key phải được lấy từ trust store độc lập.
        boolean manifestSignatureValid = verify(manifest, signature, pair);

        // Chỉ dùng metadata trong manifest sau khi chữ ký hợp lệ.
        if (!manifestSignatureValid) {
            throw new SecurityException("Untrusted release manifest");
        }

        String claimedDigest = expectedSha256FromSignedManifest(manifest);
        boolean artifactDigestValid = claimedDigest.equals(sha256Hex(artifact));
        boolean accepted = manifestSignatureValid && artifactDigestValid;
        System.out.println("Release accepted: " + accepted); // true

        byte[] tamperedArtifact = "demo application binary modified"
                .getBytes(StandardCharsets.UTF_8);
        boolean alteredAccepted = manifestSignatureValid
                && claimedDigest.equals(sha256Hex(tamperedArtifact));
        System.out.println("Tampered artifact accepted: " + alteredAccepted);
        // false

        // Nếu thay bytes manifest mà giữ chữ ký cũ, verify sẽ thất bại.
        byte[] tamperedManifest = manifest.clone();
        tamperedManifest[0] ^= 1;
        System.out.println("Tampered manifest verified: " +
                verify(tamperedManifest, signature, pair)); // false
    }
}
~~~

Mẫu này làm rõ **hai phép kiểm tra độc lập**:

1. **Xác minh chữ ký manifest:** chỉ tin manifest nếu chữ ký khớp với public key được phép ký release và thuật toán được cấu hình ở phía verifier.
2. **Đối chiếu digest artifact:** tính lại SHA-256 của bytes nhận được, so với giá trị đã nằm trong manifest được ký. Nếu artifact bị tráo, SHA-256 không khớp và release bị từ chối.

Ngoài ra, code còn ghim các trường `schema`, `name`, `version`, `channel` để thể hiện nguyên tắc ràng buộc ngữ cảnh. **Code demo không phải hệ thống CI/CD hoàn chỉnh**: chưa quản lý khóa bền vững, chứng chỉ, truy xuất artifact lớn theo stream, xác minh danh tính nhà phát hành, provenance, chống rollback hay lưu audit. Trong triển khai thật, không dùng key pair được sinh cùng phiên xác minh; hãy dùng public key/chứng chỉ được quản trị độc lập.

**Với artifact lớn:** dùng đọc file theo luồng để tính digest, giới hạn kích thước manifest và tránh nạp toàn bộ binary vào RAM. Khi tính digest trong lúc tải, chỉ triển khai sau khi bytes được lưu thành đối tượng bất biến và đã xác minh đầy đủ; tránh tình huống kiểm tra một file rồi triển khai file khác do đường dẫn bị thay giữa hai bước (**time-of-check/time-of-use**).

## 7. Bảo vệ private key ký release trong KMS/HSM

Khóa ký release có giá trị rất cao: nếu private key bị lộ, kẻ tấn công có thể phát hành một artifact giả **có chữ ký hợp lệ** theo public key mà consumer vẫn tin.

**KMS (Key Management Service)** cung cấp API tạo/sử dụng khóa và chính sách truy cập. **HSM (Hardware Security Module)** bảo vệ vật liệu khóa trong ranh giới phần cứng, tùy loại thiết bị và cấu hình. Nhiều nền tảng KMS có thể dùng HSM phía sau; không mặc định mọi sản phẩm hỗ trợ Ed25519, RSA-PSS hay mọi biến thể chữ ký.

Một kiến trúc điển hình:

~~~mermaid
flowchart LR
    CI["CI runner đã xác thực workload"] --> GATE["Release policy / approval"]
    GATE --> SIGN["Gọi KMS Sign bằng key ID"]
    KMS["Private key release trong KMS/HSM"] --> SIGN
    SIGN --> SIG["Detached signature / signed manifest"]
    ART["Artifact bất biến và digest"] --> BUNDLE["Release bundle"]
    SIG --> BUNDLE
    BUNDLE --> CONSUMER["Consumer: trust policy + Verify"]
~~~

### 7.1. Quyền ký phải nhỏ nhất có thể

- Dùng **danh tính workload riêng** cho pipeline phát hành; không dùng tài khoản cá nhân hoặc token chia sẻ lâu dài khi có lựa chọn đáng tin hơn.
- Tách **dev/staging/prod**, dự án/repository và mục đích; không dùng một private key ký production cho mọi pipeline.
- Hạn chế quyền **Sign** theo key ID và danh tính, thời gian/điều kiện phát hành nếu chính sách KMS và quy trình hỗ trợ.
- Tách quyền **tạo, cấp phép, xoay và hủy khóa** khỏi quyền gọi Sign; áp dụng phê duyệt hoặc nhiều người kiểm tra với bản phát hành nhạy cảm.
- Bật **audit log** cho các lần gọi Sign, thay đổi ACL, thao tác xoay/hủy khóa; cảnh báo việc ký ngoài luồng hoặc từ runner bất thường.
- Hạn chế đường xuất private key; ưu tiên khóa **non-exportable** trong phạm vi nhà cung cấp hỗ trợ.

**Non-exportable không ngăn lạm dụng API ký:** một CI job bị xâm nhập vẫn có thể yêu cầu KMS ký artifact độc hại nếu quyền và gate nghiệp vụ cho phép. Vì vậy phải kiểm soát **điều kiện trước khi ký**, không chỉ bảo vệ bytes private key.

### 7.2. Bí mật, khóa và vật liệu khác trong pipeline

Pipeline có thể giữ token đăng registry, credential, khóa MAC, chứng chỉ tạm thời hoặc các secret khác. Nên dùng hệ thống quản lý bí mật với mã hóa khi lưu, phân quyền và hạn dùng; các KMS có thể kết hợp **KEK/DEK qua envelope encryption** để bảo vệ dữ liệu nhạy cảm. Tuy nhiên **khóa AES/KEK dùng để mã hóa dữ liệu không tự thay thế private key ký release**. Mục đích và quyền sử dụng phải được tách rõ.

## 8. Xác minh chính sách ở phía consumer hoặc deployment gate

**Verify(signature) == true** là điều kiện cần, chưa đủ. Consumer cần xác minh cả **nguồn tin cậy**, **đối tượng**, **phiên bản** và **quyền triển khai**.

| Điều kiện | Ví dụ câu hỏi kiểm tra | Nếu thiếu sẽ có nguy cơ |
| --- | --- | --- |
| **Trusted signer** | Public key/chứng chỉ có nằm trong trust policy của dịch vụ? | Chấp nhận khóa của người ký giả. |
| **Signature & algorithm** | Chữ ký hợp lệ trên đúng manifest/artifact? Thuật toán có được phép không? | Thuật toán sai, chữ ký không khớp hoặc confusion. |
| **Artifact digest** | Digest tính lại từ bytes tải về có trùng giá trị đã ký? | Artifact bị thay thế sau khi ký. |
| **Release identity** | Project, repository, workflow, channel, target OS/arch có đúng? | Bản build thử nghiệm được đưa vào production. |
| **Version / anti-rollback** | Phiên bản có thỏa quy tắc tối thiểu/monotonic không? | Triển khai bản cũ đã có lỗ hổng dù chữ ký hợp lệ. |
| **Provenance** | Bằng chứng build có đến từ builder được phép, đúng commit và source không? | Artifact độc hại được tạo bởi quy trình không được tin. |
| **Trạng thái khóa** | Khóa/chứng chỉ có bị thu hồi, hết tin cậy hoặc thay thế theo policy không? | Tiếp tục chấp nhận artifact giả ký bằng khóa đã lộ. |
| **Triển khai bất biến** | Đang triển khai chính bytes/digest vừa xác minh? | Lỗi TOCTOU và tráo file giữa Verify và Deploy. |

**Key ID/kid không chứng minh danh tính**. Một file tự ghi `keyId=production` không có nghĩa khóa đó là khóa production thật. Với keyless signing, verifier cần ghim được **issuer và subject identity** cùng các điều kiện liên quan, thay vì chỉ thấy một chứng chỉ ngắn hạn hợp lệ bất kỳ.

**Chính sách chống rollback** là chức năng riêng: chữ ký cũ có thể vẫn hợp lệ về toán học. Ví dụ, consumer lưu phiên bản tối thiểu được phép hoặc số thứ tự phát hành đã xác thực và từ chối quay về bản thấp hơn ngoài quy trình khôi phục có phê duyệt.

## 9. Release provenance, SBOM và chuỗi cung ứng phần mềm

**Provenance** trả lời các câu hỏi như: *artifact nào được build, từ nguồn/commit nào, bằng workflow hoặc builder nào, trong điều kiện nào?* Một **attestation có chữ ký** có thể ràng buộc các tuyên bố này với digest của artifact.

**SBOM (Software Bill of Materials)** liệt kê các thành phần/phụ thuộc phần mềm. Một **SBOM được ký hoặc có digest nằm trong release manifest đã ký** có thể giúp phát hiện SBOM bị sửa đổi; điều đó không chứng minh SBOM đầy đủ hay mọi thành phần đều an toàn. Tương tự, chữ ký provenance không tự chứng minh mọi dependency đều đã qua kiểm tra.

Có thể kết hợp những lớp sau:

1. **Signed source/ref:** xác thực commit/tag hoặc chính sách merge và phê duyệt đối với nguồn.
2. **Trusted build process:** bảo vệ CI runner, workflow, dependency và credential khỏi sửa đổi trái phép.
3. **Signed provenance:** ghi nhận nguồn, builder, workflow và subject digest theo định dạng đã chọn.
4. **Signed release manifest/artifact:** ràng buộc đối tượng phân phối với release identity và signer.
5. **Consumer policy:** xác minh các bằng chứng độc lập và chỉ cho triển khai những artifact phù hợp.

Một số hệ sinh thái sử dụng **in-toto, SLSA và DSSE** để mô tả hoặc ký bằng chứng supply chain. Tên tiêu chuẩn không tự cấp mức tin cậy; kết quả còn phụ thuộc khả năng cách ly builder, việc xác thực identity, các kiểm soát CI thực tế và cấu hình verifier.

## 10. Vòng đời khóa ký và tác động tới release lịch sử

| Giai đoạn | Công việc chính | Rủi ro nếu quản lý sai |
| --- | --- | --- |
| **Tạo** | Chọn Ed25519/ECDSA/RSA-PSS phù hợp; sinh khóa bằng CSPRNG hoặc KMS/HSM đáng tin. | Khóa yếu, sai thuật toán hoặc dùng lại giữa môi trường. |
| **Cấp phát** | Đặt owner, key ID, usage SIGN, chính sách release, public key/chứng chỉ tin cậy. | Pipeline hoặc consumer dùng nhầm khóa. |
| **Lưu trữ** | Bảo vệ private key, hạn chế xuất, kiểm soát backup và credential được phép gọi Sign. | Lộ khóa qua runner, secret, log, image hoặc bản sao lưu. |
| **Sử dụng** | Chỉ ký artifact bất biến đã qua gate; ghi audit hoạt động Sign theo release ID. | Ký artifact chưa được phê duyệt hoặc ký ngoài pipeline. |
| **Xoay vòng** | Tạo khóa mới, cập nhật trust store/verifier trước, chuyển signer, theo dõi bản cũ. | Release mới bị từ chối hoặc kẻ tấn công lợi dụng khóa cũ còn được tin quá rộng. |
| **Thu hồi/vô hiệu hóa** | Ngừng quyền Sign, cập nhật chính sách công nhận khóa/chứng chỉ, điều tra ảnh hưởng. | Artifact giả vẫn được consumer chấp nhận. |
| **Hủy** | Hủy private key và bản sao theo chính sách sau khi xử lý phụ thuộc và bằng chứng. | Khóa tồn dư hoặc mất khả năng thực hiện quy trình ký còn cần. |

### 10.1. Xoay từ release key S1 sang S2

1. Sinh **S2** và công bố public key/chứng chỉ qua **kênh tin cậy** cho consumer.
2. Cập nhật các verifier để nhận **S2** đúng project, channel và thuật toán; không mở quyền tin cậy không giới hạn cho mọi khóa mới.
3. Chuyển pipeline sang ký artifact mới bằng S2, đưa key ID/identity vào manifest có chữ ký.
4. Giữ thông tin xác minh release đã ký bằng **S1** theo thời gian và chính sách cần thiết. Với một số hệ thống, phải giữ chứng chỉ, bằng chứng thời gian và trạng thái thu hồi.
5. Ngừng quyền tạo chữ ký mới bằng S1, điều tra các lệnh Sign còn phát sinh, cuối cùng xử lý khóa cũ theo lịch thu hồi/hủy.

**Không nhất thiết phải giữ private key S1 để kiểm tra chữ ký lịch sử**; về mặt mật mã, public key tương ứng đủ để Verify. Nhưng việc có **chấp nhận** một release lịch sử hay không vẫn tùy chính sách thời hạn, thu hồi, anti-rollback và bằng chứng ký vào thời điểm nào.

### 10.2. Khi private key ký release bị nghi lộ

Ưu tiên **ngăn hành vi ký mới** bằng khóa/danh tính bị nghi xâm nhập, cô lập pipeline, thu hồi credential, đánh giá log ký và công bố quy trình thay khóa. Các consumer cần cập nhật trust policy để không tiếp tục chấp nhận bản phát hành giả có thể đã được ký trong thời gian sự cố.

Chỉ sinh S2 **không tự giải quyết** sự cố nếu consumer vẫn tin S1 vô thời hạn. Tuy nhiên, chặn mọi release S1 lập tức cũng có thể ảnh hưởng tính sẵn sàng hoặc việc xác minh bản cũ đã được phê duyệt; chính sách ứng phó cần đánh giá thời điểm ký, bằng chứng tin cậy và rủi ro cụ thể. Khi cần, có thể dùng danh sách digest release đã phê duyệt thay vì chỉ xét “chữ ký bằng S1”.

## 11. Tình huống: phát hành ứng dụng Java và container image

Một nhóm phát triển **Billing Service** sử dụng Java, phát hành cả `billing-service.jar` và OCI image lên production.

**Phía CI/CD:**

1. Nguồn được merge theo quy định; CI chạy kiểm tra cần thiết, tạo JAR và image trong môi trường build có kiểm soát.
2. Hệ thống tính **SHA-256 của JAR** và lấy **digest OCI** của image đã xuất bản. Lưu tên version, commit, build identity và các digest vào release manifest.
3. Workflow phát hành production được kiểm soát yêu cầu quyền hoặc phê duyệt phù hợp trước khi gọi API **Sign** bằng khóa `release-prod-S2` trong KMS/HSM.
4. Pipeline ký manifest (và thực hiện ký image theo công cụ OCI được chọn nếu cần), công bố chữ ký, provenance và SBOM cùng artifact tại kho phát hành.
5. Tạo bản ghi audit liên kết **release ID, digest, key ID, workflow run, commit, người/phần mềm phê duyệt và thời gian**.

**Phía triển khai:**

1. Controller lấy release manifest và chữ ký; chỉ chấp nhận public key/identity đã gắn với Billing Service production.
2. Xác minh chữ ký, digest của JAR và image, chính sách nguồn build và kênh phát hành.
3. Kiểm tra version không vi phạm anti-rollback, môi trường đúng, và image được triển khai bằng **digest đã xác minh**.
4. Nếu tất cả điều kiện đạt mới triển khai; nếu không thì từ chối và ghi audit.

**Tình huống A – registry bị thay image tag:** tag `billing:1.4.2` bị trỏ sang digest khác. Nếu deployment chỉ tham chiếu tag và bỏ qua digest, hệ thống có thể chạy image sai. Khi pin bằng digest đã xác minh, việc thay tag không làm đổi nội dung được triển khai.

**Tình huống B – private key không lộ nhưng CI bị chiếm quyền:** kẻ tấn công thay bước build rồi yêu cầu KMS ký. Chữ ký có thể hợp lệ nếu policy cho phép. Bắt buộc phải bảo vệ pipeline, kiểm tra provenance và giới hạn quyền gọi Sign.

**Tình huống C – phát hành bản cũ có chữ ký hợp lệ:** một artifact 1.3.0 không bị sửa đổi nhưng chứa lỗ hổng đã được sửa ở 1.4.2. Nếu consumer không kiểm tra version/release policy, một chữ ký hợp lệ không ngăn downgrade.

**Tình huống D – sai mapping:** manifest phát hành ghi JAR 1.4.2 nhưng một image được build từ commit khác. Cần đảm bảo mỗi digest và provenance của mỗi artifact được ràng buộc vào cùng release identity và chính sách nguồn tương ứng.

## 12. Sai lầm thường gặp và biện pháp

| Sai lầm | Hậu quả | Biện pháp |
| --- | --- | --- |
| Đăng SHA-256 ở cùng nơi với artifact rồi coi đã xác thực | Kẻ tấn công sửa cả artifact lẫn checksum. | Ký digest/manifest và dùng public key từ nguồn tin cậy. |
| Lấy public key từ chính artifact mà không xác minh nguồn | Chữ ký giả vẫn có thể Verify thành công bằng khóa do kẻ tấn công cung cấp. | Trust store, PKI hoặc identity policy độc lập. |
| Ký artifact nhưng không ký kênh/version/mục đích | Đưa gói hợp lệ vào ngữ cảnh khác ngoài dự kiến. | Ràng buộc release identity trong dữ liệu được ký và xác minh policy. |
| Dùng tag image thay vì digest trong bước triển khai | Tag bị gán lại làm thay đổi nội dung triển khai. | Pin image digest đã được xác minh. |
| Chỉ kiểm signature, bỏ qua checksum artifact thật | Manifest hợp lệ nhưng artifact nhận được bị tráo. | Tính lại digest trên đúng bytes trước khi dùng. |
| Khóa prod dùng chung với dev/test | Môi trường ít tin cậy có thể ký giả bản phát hành prod. | Tách khóa, danh tính và chính sách theo môi trường. |
| KMS non-exportable nhưng mọi CI job đều có quyền Sign | Pipeline bị chiếm quyền có thể tạo chữ ký hợp lệ. | Gate ký, phân quyền tối thiểu, phê duyệt và audit. |
| Tự ghép JSON/YAML rồi ký mà thiếu canonicalization | Verifier và signer xử lý bytes khác nhau hoặc tạo định dạng mơ hồ. | Chuẩn hóa serialization và kiểm thử liên thông. |
| Chỉ xác minh digest ở lúc tải, rồi triển khai bằng đường dẫn thay đổi được | TOCTOU cho phép thay artifact giữa check và use. | Kho bất biến, deploy bằng digest và bảo vệ phạm vi đã xác minh. |
| Quên kiểm tra provenance/source identity | Artifact độc hại build từ workflow giả vẫn được phép dùng. | Chỉ tin builder/workflow/commit đã xác thực. |
| Không kiểm tra anti-rollback | Artifact cũ hợp lệ được triển khai lại. | Policy phiên bản và trường hợp rollback có phê duyệt. |
| Xoay khóa nhưng chưa cấp public key mới cho consumer | Release mới bị từ chối hàng loạt. | Phân phối trust trước, chuyển ký sau, giám sát tương thích. |
| Private key bị nghi lộ nhưng không cập nhật trust của consumer | Bản release giả ký bằng khóa cũ tiếp tục được chấp nhận. | Quy trình thu hồi, điều tra và cập nhật verifier. |
| Log secret/private key để debug | Mất quyền kiểm soát khóa ký. | Chỉ log key ID, actor, kết quả và metadata không nhạy cảm. |

## 13. Câu hỏi tự kiểm tra

1. Tại sao tệp `SHA256SUMS` không có chữ ký riêng không đủ để xác thực tác giả bản release?
2. Khác biệt giữa ký **toàn bộ artifact** và ký **manifest chứa digest của artifact** là gì?
3. Nếu manifest được ký hợp lệ nhưng bytes của JAR tải về không khớp digest, consumer phải làm gì?
4. Vì sao `image:tag` và `image@sha256:digest` cho bảo đảm triển khai khác nhau?
5. Chữ ký artifact có chứng minh mã nguồn không chứa lỗ hổng hoặc CI build không bị tấn công không?
6. Vì sao một private key `non-exportable` vẫn có thể bị lạm dụng trong pipeline CI/CD?
7. Nếu release 1.3.0 có chữ ký hợp lệ, làm thế nào ngăn việc triển khai nó thay cho release 1.4.2?
8. Việc ký provenance hoặc SBOM có đồng nghĩa tất cả dependency được kiểm tra an toàn không?
9. Khi xoay khóa phát hành S1 sang S2, consumer cần cập nhật gì trước khi pipeline chuyển ký?
10. Nếu private key S1 bị lộ, có cần đánh giá lại các release lịch sử và trust policy không?
11. Tại sao `keyId` trong manifest và việc một certificate được cấp vẫn chưa đủ nếu verifier chưa kiểm tra identity/issuer/chính sách?
12. Trong ví dụ Java, vì sao phải xác minh cả **signature manifest** lẫn **SHA-256 của artifact**?

**Ghi nhớ:** Ký artifact/release là một phần của **bảo vệ chuỗi cung ứng phần mềm**. Hệ thống an toàn cần **định danh artifact bằng digest, ký dữ liệu phát hành chính xác, xác thực public key/identity, ghim chính sách nguồn build và phiên bản, bảo vệ quyền Sign trong KMS/HSM, kiểm toán và quản lý vòng đời khóa**. Chỉ khi consumer kiểm tra đầy đủ các điều kiện trước triển khai, chữ ký số mới thực sự giúp ngăn thay thế bản phát hành và giảm rủi ro phát tán phần mềm giả mạo.
