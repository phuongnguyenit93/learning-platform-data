# Ký và xác minh bằng jarsigner hoặc JarSigner API

Ký JAR tạo chữ ký số gắn với nội dung các entry trong archive. Người ký dùng private key để ký; bên nhận dùng public key trong certificate để kiểm tra chữ ký và phát hiện nội dung bị sửa sau khi ký. Quy trình phát hành an toàn cần chuẩn bị private key/certificate chain, ký sau khi JAR đã hoàn tất, thêm timestamp từ TSA và xác minh cả tính toàn vẹn lẫn danh tính/trust của signer.

Trên JDK 26/27, có hai cách ký chính thức: công cụ dòng lệnh `jarsigner` và API `jdk.security.jarsigner.JarSigner`. `JarSigner` API có từ JDK 9, nằm trong module JDK `jdk.jartool`; đây không phải preview/incubator. JDK 26 bổ sung hỗ trợ ký và xác minh JAR bằng hậu lượng tử **ML-DSA** qua cả công cụ và API. Bài này dùng keystore PKCS12, chữ ký mặc định theo key/provider và security policy hiện hành; tránh các định dạng/thuật toán đã lỗi thời.

## 1. Chữ ký JAR bảo vệ điều gì?

JAR là một ZIP archive có thể chứa class, resource, manifest và metadata. Khi ký bằng `jarsigner`, công cụ cập nhật `META-INF/MANIFEST.MF` và thêm hai loại file:

- **Signature file (`.SF`)**: chứa digest của các section trong manifest và thông tin digest của manifest.
- **Signature block (`.RSA`, `.DSA`, `.EC`)**: chứa chữ ký số trên file `.SF` cùng certificate hoặc certificate chain của signer. Phần mở rộng phụ thuộc loại key/signature; JDK 26 cũng hỗ trợ ML-DSA theo quy tắc block-file tương ứng.

Quá trình xác minh kiểm tra chữ ký trên `.SF`, digest của các section manifest và digest của từng entry đã được ký. Nếu nội dung entry thay đổi sau khi ký, việc xác minh sẽ thất bại khi entry được đọc.

Chữ ký JAR cung cấp:

- **Integrity**: nội dung các entry được ký không bị thay đổi mà không bị phát hiện.
- **Signer authentication**: chữ ký khớp với private key tương ứng public key trong certificate.
- **Certificate metadata**: archive mang theo certificate/chain để bên nhận có thể kiểm tra danh tính và trust.

Chữ ký JAR không mã hóa nội dung, không che giấu source/class/resource và không tự quyết định certificate có đáng tin hay không. Bên nhận vẫn cần trust policy để xác định certificate thuộc signer được chấp nhận.

## 2. Chuẩn bị key và certificate bằng keytool

`keytool` quản lý public/private key và certificate trong keystore. JDK 26 đặt mặc định keystore type là **PKCS12**. JKS và JCEKS vẫn có thể xuất hiện trong hệ thống cũ, nhưng JDK 26 cảnh báo khi dùng chúng vì các định dạng này dùng thuật toán bảo vệ đã cũ và được dự kiến loại bỏ trong một bản phát hành tương lai. Hãy dùng PKCS12 cho quy trình mới.

### Tạo key pair để thử nghiệm

Ví dụ tạo RSA key pair trong PKCS12:

```bash
keytool -genkeypair \
  -alias release \
  -keyalg RSA \
  -keysize 3072 \
  -dname "CN=Example Release,O=Example,C=VN" \
  -validity 365 \
  -storetype PKCS12 \
  -keystore release.p12
```

`keytool` sẽ hỏi password cho keystore và private key. Không đặt password trực tiếp trên command line trong script dùng chung hoặc môi trường CI có log lệnh. Ví dụ này tạo certificate tự ký để thử nghiệm; certificate tự ký không đại diện cho danh tính nhà phát hành đã được CA tin cậy.

Kiểm tra entry:

```bash
keytool -list -v -keystore release.p12 -storetype PKCS12 -alias release
```

Đảm bảo entry là `PrivateKeyEntry`, có certificate chain phù hợp và certificate còn hiệu lực. Với code signing production, certificate cần được cấp cho đúng nhà phát hành và có KeyUsage/ExtendedKeyUsage cho phép code signing theo yêu cầu của CA và hệ thống nhận.

### Dùng certificate do CA cấp trong production

Quy trình phổ biến:

```bash
# Tạo Certificate Signing Request (CSR) từ private key đã nằm trong keystore.
keytool -certreq -alias release -keystore release.p12 -storetype PKCS12 -file release.csr

# Sau khi CA cấp certificate/chain, import CA root/intermediate nếu cần.
keytool -importcert -alias signing-root -keystore release.p12 -storetype PKCS12 -file signing-root.pem

# Import certificate reply/chain cho alias chứa private key.
keytool -importcert -alias release -keystore release.p12 -storetype PKCS12 -file release-chain.pem
```

File `release-chain.pem` do CA cung cấp cần chứa certificate reply và các intermediate certificate theo định dạng được `keytool` hỗ trợ. Khi import reply vào alias đã có private key, `keytool` thay certificate tự ký ban đầu bằng chain mới. Xác minh lại bằng `keytool -list -v`.

Không tự tạo một certificate tự ký rồi coi nó là certificate production. Certificate tự ký chỉ có thể được tin cậy khi bên nhận chủ động pin hoặc cài nó làm trust anchor theo một chính sách riêng.

## 3. Ký JAR bằng công cụ jarsigner

Giả sử:

- `app.jar` là artifact đã build và kiểm thử xong.
- `release.p12` là PKCS12 keystore có `PrivateKeyEntry` tên `release`.
- `app-signed.jar` là file đầu ra.
- TSA là dịch vụ timestamp theo RFC 3161 do tổ chức phát hành lựa chọn.

Ký JAR và thêm timestamp:

```bash
jarsigner \
  -keystore release.p12 \
  -storetype PKCS12 \
  -signedjar app-signed.jar \
  -tsa https://tsa.example.org \
  app.jar release
```

Thay URL ví dụ bằng endpoint TSA được tổ chức phát hành phê duyệt. Nếu bỏ `-tsa`, chữ ký không có timestamp. Công cụ sẽ hỏi password khi cần; không cần truyền `-storepass`/`-keypass` trực tiếp trên command line.

Không chỉ định `-sigalg` hoặc `-digestalg` trong ví dụ cơ bản. `jarsigner` tự chọn digest và signature algorithm theo key, key size, provider và chính sách của JDK. JDK 26/27 dùng SHA-384 làm digest mặc định cho JAR entry; signature algorithm mặc định được chọn phù hợp với loại key. Các mặc định có thể được nâng cấp ở những JDK release sau. Chỉ chỉ định thuật toán tường minh khi có yêu cầu tương thích đã được xác nhận với tất cả hệ thống xác minh.

Nếu không dùng `-signedjar`, `jarsigner` ghi chữ ký trực tiếp vào file đầu vào. Trong pipeline release, nên tạo output riêng để giữ artifact chưa ký làm đầu vào tái lập và tránh ghi đè ngoài ý muốn.

## 4. Timestamp có ý nghĩa gì?

Certificate signer thường có thời hạn. Nếu chỉ ký mà không có timestamp, sau khi certificate hết hạn hoặc bị thu hồi trong tương lai, bên nhận có thể không xác minh được chữ ký theo chính sách hiện hành.

Khi dùng `-tsa`, `jarsigner` gửi yêu cầu đến Time-Stamp Authority theo **RFC 3161**. TSA trả token có chữ ký của TSA, được lưu trong signature block. Token chứng minh chữ ký JAR đã tồn tại tại một thời điểm do TSA xác nhận.

Timestamp giúp bên xác minh đánh giá certificate signer theo thời điểm ký, thay vì yêu cầu certificate còn hiệu lực tại thời điểm kiểm tra hiện tại. Tuy nhiên:

- TSA phải được tin cậy và certificate chain của TSA phải xác minh được.
- Timestamp phải hợp lệ, còn nằm trong chính sách chấp nhận và không bị vô hiệu hóa bởi policy.
- Timestamp không biến một certificate đã bị thu hồi trước thời điểm ký thành hợp lệ.
- Timestamp không thay thế certificate chain của signer hoặc trust policy của tổ chức.

Có thể dùng `-tsacert alias` thay `-tsa URL` nếu certificate TSA trong keystore có Subject Information Access extension chứa địa chỉ TSA. `-tsapolicyid` chỉ định TSA policy OID; `-tsadigestalg` chọn digest cho message imprint, mặc định là SHA-384.

## 5. Xác minh bằng jarsigner

Lệnh cơ bản:

```bash
jarsigner -verify app-signed.jar
```

Để kiểm tra chi tiết certificate và từng entry, dùng:

```bash
jarsigner -verify -verbose -certs app-signed.jar
```

Trong CI/release gate, nên dùng `-strict`:

```bash
jarsigner -verify -strict -verbose -certs app-signed.jar
```

`-strict` làm cho severe warnings ảnh hưởng exit code. Khi không có lỗi, nhưng có severe warning, lệnh không strict vẫn có thể trả exit code `0`; vì vậy không nên chỉ kiểm tra dòng `jar verified` hoặc chạy lệnh thiếu `-strict` trong release gate.

Một số severe warning thường gặp:

| Warning | Ý nghĩa |
| --- | --- |
| `hasExpiredCert` / `notYetValidCert` | Certificate signer không hợp lệ theo thời điểm xác minh |
| `chainNotValidated` | Không xây dựng/xác minh được certificate chain đến trust anchor |
| `signerSelfSigned` | Certificate signer tự ký; không có trust anchor được chấp nhận |
| `disabledAlg` | Chữ ký dùng thuật toán bị security policy vô hiệu hóa |
| `badKeyUsage` / `badExtendedKeyUsage` | Certificate không cho phép mục đích code signing |
| `hasUnsignedEntry` | Archive có entry chưa được chữ ký bảo vệ |
| `tsaChainNotValidated` | Timestamp hoặc certificate chain TSA không hợp lệ |

Các informational warning như `legacyAlg` hoặc `noTimestamp` vẫn cần được đọc và xử lý, dù `-strict` không nhất thiết biến chúng thành lỗi. `noTimestamp` đặc biệt cần được xem xét nếu JAR phải tiếp tục được xác minh sau khi certificate signer hết hạn.

Nếu muốn so khớp signer với một alias cụ thể trong keystore/truststore:

```bash
jarsigner -verify -strict -verbose -certs \
  -keystore trusted-signers.p12 \
  app-signed.jar release
```

Alias giúp kiểm tra certificate signer có khớp entry mong đợi trong keystore được chỉ định hay không. Đây là một phần của kiểm tra danh tính; vẫn cần hiểu trust anchor, certificate path và chính sách revocation của hệ thống.

## 6. Bật kiểm tra thu hồi certificate khi cần

`jarsigner` không bật kiểm tra revocation mặc định. Tùy chọn `-revCheck` yêu cầu công cụ truy cập OCSP responder hoặc CRL Distribution Point để kiểm tra trạng thái thu hồi của certificate chain:

```bash
jarsigner -verify -strict -verbose -certs -revCheck app-signed.jar
```

Lệnh này có thể cần kết nối mạng đến OCSP/CRL endpoint. Trong CI kín mạng, cần quyết định rõ chính sách: cung cấp dữ liệu revocation phù hợp, dùng trust service nội bộ hoặc không bật revocation online theo chính sách được phê duyệt. Không được diễn giải “không kiểm tra revocation” thành “certificate chắc chắn chưa bị thu hồi”.

## 7. Ký bằng JarSigner API

Nếu ứng dụng cần tích hợp ký JAR vào quy trình Java, dùng `jdk.security.jarsigner.JarSigner`. API này thuộc module JDK **`jdk.jartool`**, package `jdk.security.jarsigner`; nó có từ JDK 9 và tiếp tục có trên JDK 26/27. Vì module không thuộc `java.base`, ứng dụng classpath cần thêm module khi compile/run; ứng dụng modular khai báo `requires jdk.jartool`.

Ví dụ dùng `KeyStore.PrivateKeyEntry` từ PKCS12:

```java
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.KeyStore;
import java.util.Arrays;
import java.util.zip.ZipFile;

import jdk.security.jarsigner.JarSigner;

public final class SignJar {
    private SignJar() {}

    public static void sign(
            Path inputJar,
            Path outputJar,
            Path keystorePath,
            String alias,
            char[] storePassword,
            char[] keyPassword,
            URI tsaUri
    ) throws Exception {
        KeyStore keyStore = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(keystorePath)) {
            keyStore.load(in, storePassword);
        }

        KeyStore.PasswordProtection protection =
                new KeyStore.PasswordProtection(keyPassword);
        KeyStore.PrivateKeyEntry entry;
        try {
            entry = (KeyStore.PrivateKeyEntry) keyStore.getEntry(alias, protection);
        } finally {
            protection.destroy();
            Arrays.fill(storePassword, '\0');
            Arrays.fill(keyPassword, '\0');
        }

        JarSigner.Builder builder = new JarSigner.Builder(entry);
        if (tsaUri != null) {
            builder.tsa(tsaUri);
        }

        // Mặc định digest/signature algorithm theo JDK và private key.
        JarSigner signer = builder.build();

        // Dùng file đầu ra riêng; không ghi đè input JAR.
        try (ZipFile input = new ZipFile(inputJar.toFile());
             OutputStream output = Files.newOutputStream(
                     outputJar,
                     StandardOpenOption.CREATE_NEW,
                     StandardOpenOption.WRITE)) {
            signer.sign(input, output);
        }
    }
}
```

`JarSigner` là immutable; `JarSigner.Builder` cấu hình key/certificate chain, digest, signature algorithm, signer name và TSA trước khi gọi `build()`. `sign(ZipFile, OutputStream)` không tự đóng input hoặc output stream. Nếu lỗi I/O hoặc lỗi ký xảy ra sau khi đã ghi một phần dữ liệu, output có thể không nhất quán; hãy đóng và loại bỏ file đầu ra lỗi, sau đó ký lại vào file mới.

Không cần chỉ định `.digestAlgorithm("SHA-256")` hoặc `.signatureAlgorithm("SHA256withRSA")` cho mọi key. Builder có mặc định digest SHA-384 và chọn signature algorithm dựa trên private key. Nếu đặt thuật toán thủ công, cần xác minh thuật toán tương thích key, provider và security policy ở mọi JDK đích.

### Biên dịch và chạy JarSigner API

Ứng dụng classpath:

```bash
javac --add-modules jdk.jartool -d out src/SignJar.java
java --add-modules jdk.jartool -cp out SignJar
```

Ứng dụng dùng module-info:

```java
module com.example.signer {
    requires jdk.jartool;
}
```

Nếu tạo custom runtime image bằng `jlink`, image phải chứa module `jdk.jartool` để ứng dụng dùng API này. Nếu chỉ chạy công cụ `jarsigner` từ JDK, không cần viết code hoặc thêm module vào ứng dụng.

## 8. Xác minh bằng JarFile API

`JarSigner` API chuyên ký, không cung cấp method verify đối xứng. Để xác minh entry trong ứng dụng, dùng `java.util.jar.JarFile` với `verify=true`. JVM xác minh digest/chữ ký khi nội dung entry được đọc đến hết. Sau đó, `JarEntry.getCodeSigners()` trả các signer của entry.

```java
import java.io.InputStream;
import java.io.OutputStream;
import java.io.IOException;
import java.nio.file.Path;
import java.util.Enumeration;
import java.util.Locale;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

public final class VerifyJarEntries {
    private VerifyJarEntries() {}

    public static void verify(Path jarPath) throws IOException {
        try (JarFile jar = new JarFile(jarPath.toFile(), true)) {
            Enumeration<JarEntry> entries = jar.entries();

            while (entries.hasMoreElements()) {
                JarEntry entry = entries.nextElement();
                if (entry.isDirectory()) {
                    continue;
                }

                // Phải đọc hết entry để kích hoạt kiểm tra chữ ký/digest.
                try (InputStream in = jar.getInputStream(entry)) {
                    in.transferTo(OutputStream.nullOutputStream());
                }

                if (!isSignatureMetadata(entry.getName())
                        && entry.getCodeSigners() == null) {
                    throw new SecurityException(
                            "Unsigned JAR entry: " + entry.getName());
                }
            }
        }
    }

    private static boolean isSignatureMetadata(String entryName) {
        String name = entryName.toUpperCase(Locale.ROOT);
        if (!name.startsWith("META-INF/")) {
            return false;
        }

        String leaf = name.substring("META-INF/".length());
        if (leaf.contains("/")) {
            return false;
        }

        return leaf.equals("MANIFEST.MF")
                || leaf.endsWith(".SF")
                || leaf.endsWith(".RSA")
                || leaf.endsWith(".DSA")
                || leaf.endsWith(".EC")
                || leaf.startsWith("SIG-");
    }
}
```

Nếu một entry đã ký bị sửa, việc đọc stream có thể ném `SecurityException`. Sau khi đọc hết, `getCodeSigners()` mới có kết quả; nếu entry không được ký, method trả `null`. Ví dụ trên cũng từ chối entry payload chưa ký, vì một JAR có chữ ký hợp lệ cho một số entry nhưng còn entry không được ký không đồng nghĩa toàn bộ archive đã được bảo vệ.

**Giới hạn quan trọng:** `JarFile` xác minh tính toàn vẹn và chữ ký mật mã của entry, nhưng không tự xác minh hoặc thiết lập trust cho certificate signer. Nếu ứng dụng cần quyết định signer có được tin hay không, hãy lấy `CodeSigner.getSignerCertPath()` và xác minh bằng `CertPathValidator`/PKIX với tập `TrustAnchor` do ứng dụng quản lý. Kiểm tra revocation, policy OID, thời điểm timestamp và danh tính signer theo yêu cầu nghiệp vụ. Đừng coi việc `getCodeSigners()` khác `null` là bằng chứng certificate đáng tin.

Ví dụ phần xác minh certificate path sau khi entry đã được đọc hết:

```java
import java.security.CodeSigner;
import java.security.cert.CertPathValidator;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.util.Set;

static void validateSignerTrust(
        CodeSigner[] signers,
        Set<TrustAnchor> trustedRoots
) throws Exception {
    if (signers == null || signers.length == 0) {
        throw new SecurityException("Entry has no signer");
    }

    CertPathValidator validator = CertPathValidator.getInstance("PKIX");

    for (CodeSigner signer : signers) {
        PKIXParameters parameters = new PKIXParameters(trustedRoots);
        parameters.setRevocationEnabled(true);
        if (signer.getTimestamp() != null) {
            parameters.setDate(signer.getTimestamp().getTimestamp());
        }
        validator.validate(signer.getSignerCertPath(), parameters);
    }
}
```

`trustedRoots` phải được tạo từ trust anchor mà ứng dụng chủ động chấp nhận; không lấy certificate bất kỳ trong JAR rồi tự coi nó là trust anchor. Với chữ ký có timestamp, ví dụ đặt ngày xác minh signer certificate theo thời điểm TSA ghi nhận; ứng dụng vẫn phải xác minh certificate path của TSA và tính hợp lệ của timestamp token theo chính sách riêng. PKIX validation cũng chịu `jdk.certpath.disabledAlgorithms` và có thể cần truy cập OCSP/CRL khi bật revocation.

## 9. Chính sách thuật toán ảnh hưởng đến ký và xác minh

`jarsigner` sử dụng các security properties trong `<java-home>/conf/security/java.security` để quyết định thuật toán nào bị chặn hoặc bị coi là legacy.

| Security property | Phạm vi | Tác động |
| --- | --- | --- |
| `jdk.jar.disabledAlgorithms` | Thuật toán/key dùng trong chữ ký JAR | Nếu chữ ký dùng thuật toán bị disabled, JAR bị coi như unsigned khi xác minh |
| `jdk.security.legacyAlgorithms` | Thuật toán bị đánh giá là legacy | Vẫn có thể được chấp nhận nhưng phát informational warning; có thể bị disable trong JDK tương lai |
| `jdk.certpath.disabledAlgorithms` | Xây dựng và xác minh certificate path | Chặn certificate chain có thuật toán/key size không đáp ứng policy |
| `jdk.crypto.disabledAlgorithms` | Dịch vụ JCE/JCA như Cipher, KeyStore, MessageDigest, Signature | Property mới từ JDK 26; phạm vi khác với policy riêng của JAR và CertPath |

Không sao chép một giá trị `jdk.jar.disabledAlgorithms` từ blog hoặc JDK cũ sang hệ thống hiện hành. Danh sách có thể thay đổi theo JDK update và policy của tổ chức. Hãy đọc file `java.security` của đúng JDK chạy ký/xác minh và đối chiếu với policy release của hệ thống nhận.

Để debug thuật toán bị chặn:

```bash
jarsigner -verify -J-Djava.security.debug=jar -verbose -certs app-signed.jar
```

Nếu gặp `disabledAlg` hoặc `legacyAlg`, hãy tạo lại chữ ký bằng thuật toán/key còn được chấp nhận, thay certificate nếu cần và cập nhật hệ thống nhận. Không gỡ thuật toán khỏi disabled list chỉ để một JAR cũ tiếp tục được chấp nhận. Việc nới policy làm giảm mức bảo vệ của toàn bộ runtime.

## 10. Thuật toán chữ ký và ML-DSA trên JDK 26/27

JDK 26/27 chọn signature algorithm mặc định theo loại và kích thước private key. Các nhóm thuật toán được tài liệu hiện hành nêu gồm:

| Loại private key | Signature algorithm mặc định | Ghi chú |
| --- | --- | --- |
| RSA | SHA-256/384/512 with RSA tùy key size | Dùng key size đáp ứng policy và yêu cầu tương thích |
| EC | SHA-384 hoặc SHA-512 with ECDSA tùy curve/key size | Chọn named curve được provider và hệ thống nhận hỗ trợ |
| RSASSA-PSS | RSASSA-PSS với hash/MGF tương ứng tham số/key size | Tham số PSS phải tương thích cả hai phía |
| EdDSA | `EdDSA` | Dùng parameter set của key như Ed25519 hoặc Ed448 |
| ML-DSA | `ML-DSA` | Chữ ký hậu lượng tử; JDK 26 bổ sung hỗ trợ ký/xác minh JAR qua PKCS #7/RFC 9882 |

JDK 26 Release Notes xác nhận ML-DSA JAR signing hoạt động qua cả `jarsigner` và `JarSigner` API. JDK 27 tiếp tục có thuật toán ML-DSA trong bảng lựa chọn mặc định của `jarsigner`. Khi chọn ML-DSA, cần kiểm tra cả certificate issuance, provider, hệ thống phân phối và mọi runtime xác minh đều hỗ trợ; không phải mọi nền tảng hoặc công cụ bên ngoài đều đã hỗ trợ cùng mức.

Không chọn SHA-1, MD5 hoặc DSA cho quy trình ký mới. Một chữ ký có thể được tạo bởi provider nhưng vẫn bị policy của JDK xác minh từ chối. Khả năng gọi được thuật toán không đồng nghĩa thuật toán đó được chấp nhận để ký code.

## 11. Tác động của việc sửa JAR sau khi ký

Ký phải là một trong các bước cuối cùng của pipeline:

1. Build class/resource.
2. Đóng gói JAR.
3. Chạy test, kiểm tra dependency và nội dung archive.
4. Ký artifact cuối cùng và thêm timestamp.
5. Xác minh bằng `jarsigner -verify -strict`.
6. Tính checksum/SHA-256 của artifact đã ký và phát hành đúng file đó.

Không chạy lại `jar`, zip tool, repackage plugin hoặc bước chỉnh sửa manifest sau khi ký. Nếu thay đổi entry đã ký, digest không còn khớp. Nếu thêm entry mới sau khi ký, entry mới không được chữ ký hiện tại bảo vệ và `jarsigner` có thể báo `hasUnsignedEntry`.

Nếu cần nhiều signer, có thể ký cùng một JAR lần lượt bằng nhiều alias. Mỗi signer có cặp `.SF` và signature block riêng. Khi đó, policy xác minh cần quy định signer nào bắt buộc; không chỉ kiểm tra có ít nhất một chữ ký hợp lệ.

## 12. Dùng HSM hoặc PKCS #11

Với private key production, có thể lưu khóa trong HSM/token thay vì file PKCS12. `jarsigner` hỗ trợ PKCS #11 thông qua provider SunPKCS11:

```bash
jarsigner \
  -keystore NONE \
  -storetype PKCS11 \
  -addprovider SunPKCS11 \
  -providerArg token.cfg \
  -signedjar app-signed.jar \
  -tsa https://tsa.example.org \
  app.jar release
```

`token.cfg` là file cấu hình provider theo HSM/token đang sử dụng; alias `release` phải là key entry có certificate chain phù hợp. PIN nên được nhập qua protected authentication path hoặc cơ chế quản lý bí mật của HSM. Không đưa PIN vào script hoặc log.

Với `JarSigner` API, ứng dụng có thể nạp `KeyStore` từ provider PKCS #11 rồi lấy `PrivateKeyEntry` để truyền vào `JarSigner.Builder`. Provider và HSM phải hỗ trợ signature algorithm được chọn; hãy chạy integration test trên chính thiết bị và policy production.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `keystore was tampered with, or password was incorrect` | Sai password hoặc sai keystore type | Xác nhận PKCS12/JKS đúng loại, alias và password |
| `alias does not exist` hoặc không tìm thấy private key | Alias sai hoặc entry chỉ chứa trusted certificate | Dùng alias có `PrivateKeyEntry`; kiểm tra bằng `keytool -list -v` |
| `NoSuchAlgorithmException` khi ký | Provider không có signature/digest algorithm | Kiểm tra provider, JDK và algorithm name; không ép dùng thuật toán yếu |
| `disabledAlg` | Security property chặn digest/signature/key size | Ký lại bằng thuật toán/key còn được phép; giữ nguyên policy |
| `legacyAlg` | Thuật toán vẫn dùng được nhưng bị coi là legacy | Lập kế hoạch thay key/certificate và ký lại bằng thuật toán hiện hành |
| `chainNotValidated` | Thiếu intermediate, root chưa được tin hoặc certificate path lỗi | Import chain đúng, cấu hình trust anchor và kiểm tra validity/usage |
| `badKeyUsage` hoặc `badExtendedKeyUsage` | Certificate không cho phép code signing | Yêu cầu CA cấp certificate có usage phù hợp |
| `noTimestamp` | Chữ ký không có timestamp | Ký lại với TSA RFC 3161 được tin cậy |
| `tsaChainNotValidated` | TSA token hoặc certificate chain TSA không hợp lệ | Kiểm tra endpoint TSA, chain, timestamp policy và truststore |
| `hasUnsignedEntry` | Có entry chưa được ký hoặc được thêm sau khi ký | Tạo lại JAR hoàn chỉnh rồi ký lại artifact cuối |
| `JarFile.getCodeSigners()` trả `null` | Entry chưa được đọc hết hoặc không được ký | Đọc stream đến EOF; kiểm tra unsigned payload entry |
| `JarFile` báo signature hợp lệ nhưng ứng dụng không tin signer | `JarFile` không xác minh trust chain | Dùng PKIX `CertPathValidator` với trust anchors rõ ràng |

## 14. Checklist release

- [ ] Dùng PKCS12 hoặc HSM/PKCS #11 cho private key; không tạo keystore JKS/JCEKS mới.
- [ ] Certificate signer có chain, validity, KeyUsage và ExtendedKeyUsage phù hợp cho code signing.
- [ ] Public key/certificate được phân phối qua trust channel; bên nhận có trust anchor đúng.
- [ ] Dùng thuật toán và key size đáp ứng `jdk.jar.disabledAlgorithms`, `jdk.security.legacyAlgorithms` và policy của tổ chức.
- [ ] Dùng TSA RFC 3161 đáng tin cậy để tạo timestamp khi artifact cần xác minh lâu dài.
- [ ] Ký sau khi build/repackage/manifest/resource đã hoàn tất.
- [ ] Chạy `jarsigner -verify -strict -verbose -certs` và xử lý mọi severe warning.
- [ ] Xem xét `-revCheck` theo chính sách revocation và khả năng truy cập OCSP/CRL.
- [ ] Nếu dùng API, đọc hết mọi entry bằng `JarFile(..., true)`; kiểm tra unsigned entries.
- [ ] Xác minh certificate path và trust độc lập khi dùng `JarFile` API.
- [ ] Tính checksum và phát hành chính xác artifact đã ký, đã xác minh.
- [ ] Bảo vệ keystore/password/PIN, giới hạn quyền truy cập và audit hoạt động ký.

## Ghi nhớ

- `jarsigner` ký và xác minh JAR; `keytool` tạo/quản lý key pair, certificate và keystore.
- JDK 26/27 mặc định dùng PKCS12; JKS/JCEKS phát cảnh báo legacy và được khuyến nghị chuyển đổi.
- Ký JAR tạo manifest digest, `.SF` và signature block chứa chữ ký cùng certificate chain.
- Dùng `-tsa` để thêm timestamp RFC 3161; timestamp giúp đánh giá chữ ký tại thời điểm ký nhưng không thay thế trust/revocation policy.
- Dùng `jarsigner -verify -strict -verbose -certs` làm release gate; `-strict` biến severe warnings thành exit code khác 0.
- `jdk.jar.disabledAlgorithms` chặn chữ ký yếu; `jdk.security.legacyAlgorithms` cảnh báo thuật toán legacy; không nới policy để chấp nhận JAR cũ.
- `JarSigner` API thuộc module JDK `jdk.jartool`; builder dùng `PrivateKeyEntry`, ký `ZipFile` sang `OutputStream`.
- `JarFile(..., true)` xác minh entry khi đọc hết; `getCodeSigners()` chỉ có kết quả sau khi entry được đọc hoàn tất.
- `JarFile` không xác minh trust của certificate; ứng dụng phải dùng PKIX/trust anchor riêng.
- JDK 26 bổ sung hỗ trợ ký JAR bằng ML-DSA qua cả CLI và API; JDK 27 tiếp tục hỗ trợ.
- Ký là bước cuối sau khi JAR đã hoàn chỉnh; mọi thay đổi payload sau ký cần ký lại.

## Tài liệu tham khảo

- [The `jarsigner` Command, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jarsigner.html) — ký, xác minh, thuật toán, timestamp, `-strict`, `-revCheck` và cảnh báo.
- [The `jarsigner` Command, Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jarsigner.html) — xác nhận quy trình và thuật toán tiếp tục được hỗ trợ trong JDK 27.
- [JarSigner, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jartool/jdk/security/jarsigner/JarSigner.html) — API ký JAR.
- [JarSigner.Builder, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jartool/jdk/security/jarsigner/JarSigner.Builder.html) — `PrivateKeyEntry`, thuật toán, TSA và cấu hình signer.
- [Module `jdk.jartool`, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jartool/module-summary.html) — module cung cấp công cụ `jarsigner` và API ký JAR.
- [The `keytool` Command, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/keytool.html) — tạo key pair, CSR, import certificate và quản lý PKCS12.
- [JarFile, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/jar/JarFile.html) — xác minh entry trong signed JAR.
- [JarEntry, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/jar/JarEntry.html) — `getCodeSigners()` và giới hạn xác minh trust.
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26all-relnotes.html) — hỗ trợ ML-DSA cho signed JAR và cảnh báo JKS/JCEKS.
- [Java Security Overview, Java SE 26](https://docs.oracle.com/en/java/javase/26/security/java-security-overview1.html) — quy trình keytool → jar → jarsigner/JarSigner API và timestamp.
- [Security Properties File, Java SE 26](https://docs.oracle.com/en/java/javase/26/security/security-properties-file.html) — vị trí và cơ chế security properties.
- [RFC 3161 — Internet X.509 Public Key Infrastructure Time-Stamp Protocol](https://www.rfc-editor.org/rfc/rfc3161) — timestamp token.
- [RFC 9882 — Use of the ML-DSA Signature Algorithm in the Cryptographic Message Syntax (CMS)](https://www.rfc-editor.org/rfc/rfc9882) — định dạng chữ ký ML-DSA dùng cho JAR.
