# 11.7 Khóa có thể xuất so với khóa chỉ được sử dụng thông qua provider

## 1. Tại sao hai đối tượng `Key` giống giao diện nhưng có mức kiểm soát khác nhau?

Trong Java Cryptography Architecture/Extension (JCA/JCE), các giao diện `java.security.Key`, `SecretKey`, `PublicKey`, `PrivateKey` chỉ mô tả một khóa và những thao tác có thể thực hiện thông qua provider. Chúng **không** bảo đảm material nằm trong JVM, file, hệ điều hành, token/HSM hay một dịch vụ KMS.

Hai khái niệm cần phân biệt:

- **Khóa có thể xuất (exportable):** có một biểu diễn byte của secret/private key được phép lấy ra, thường qua `key.getEncoded()`; Java process có thể giữ, sao chép, lưu hoặc nhập lại bằng API thích hợp. Mỗi bản sao mở rộng bề mặt rủi ro: heap, core dump, debug, log, file, backup, network, dịch vụ downstream.
- **Khóa chỉ được sử dụng qua provider (provider-bound/opaque):** Java giữ **handle** tham chiếu một key trong token/HSM/keystore đặc thù hoặc adapter. Backend sở hữu key material, có thể cấm việc lấy raw bytes nhưng vẫn cho phép gọi các phép `sign`, `decrypt`, `encrypt`, `MAC`, `derive` hoặc `wrap` theo policy. Mục đích là **sử dụng key mà không cần trao key material cho ứng dụng**.

```text
Ứng dụng Java
   |
   +---- exportable SecretKey/PrivateKey
   |          |
   |      getEncoded() -> byte[]
   |          |
   |      có thể import/copy/lưu nếu được phép
   |          |
   |      Cipher/Signature trên provider tương thích
   |
   +---- opaque provider key handle
              |
          getEncoded() -> thường null
              |
          Cipher/Signature/KeyAgreement
              |
          provider -> token/HSM/KMS adapter
                         |
                    operation đã cho phép
                         |
                    trả kết quả, không trả raw key
```

**Quan trọng:** `getEncoded()==null` chỉ chứng minh API Java không cung cấp encoding qua lời gọi đó. Nó **không đủ chứng minh khóa là non-extractable ở phần cứng** hoặc bất khả trích xuất bằng mọi API khác; cũng **không làm một key giả lập trở nên dùng được với provider**. Bảo đảm thực tế phụ thuộc key attributes, token policy, IAM, cơ chế import/generation, firmware và kiểm tra an ninh.

## 2. Hợp đồng của Key.getAlgorithm, getFormat và getEncoded

| API | Có nghĩa gì? | Không có nghĩa gì? |
| --- | --- | --- |
| `getAlgorithm()` | Tên thuật toán như `AES`, `RSA`, `EC` | Không nói key được tạo ở đâu, có đủ quyền sử dụng hay có thể export |
| `getFormat()` | Format encoding nếu có: `RAW`, `X.509`, `PKCS#8`, hoặc `null` | Không phải cơ chế bảo vệ dữ liệu; `null` không xác minh HSM |
| `getEncoded()` | Byte encoding nếu provider hỗ trợ, hoặc `null` | Không chứng minh danh tính chủ key; không cấp quyền bọc/xuất hay đảm bảo mọi bản sao được xóa |

Trong Java 17+ với phần mềm provider thông dụng:

- `KeyGenerator.getInstance("AES")` thường sinh `SecretKey` có `getFormat() == "RAW"`; `getEncoded()` trả 16, 24 hoặc 32 byte tùy AES-128/192/256.
- Khóa công khai RSA từ `KeyPairGenerator` thường có `getFormat()=="X.509"` và bytes DER `SubjectPublicKeyInfo`. Có thể dựng lại qua `X509EncodedKeySpec` và `KeyFactory("RSA")`.
- Khóa riêng RSA phần mềm thường có `getFormat()=="PKCS#8"` và DER `PrivateKeyInfo`. Có thể dựng lại qua `PKCS8EncodedKeySpec` và `KeyFactory("RSA")` nếu được phép.
- Khóa phần cứng có thể cho phép xuất **public key** nhưng cấm xuất **private key** cùng cặp. Public key cần xác thực nguồn/định danh trước khi dùng trong giao thức; bản thân nó không phải bí mật.

### Key export khác Key usage

Có thể key exportable nhưng bị giới hạn bởi policy để chỉ ký; ngược lại opaque key có thể ký và giải mã trong backend mà không trả raw material. Những quyền `sign`, `verify`, `encrypt`, `decrypt`, `derive`, `wrap` và `unwrap` là các quyền/chức năng **tách biệt**. Trong token có thể có key chỉ được phép `CKA_SIGN` mà không có `CKA_DECRYPT`; ứng dụng không được suy đoán từ tên thuật toán rằng mọi operation đều hợp lệ.

`getEncoded()` có thể trả `null` đối với key không hỗ trợ encoding. Không xử lý `null` bằng `new byte[0]`, không tự hash key ID thành raw key và không cố lấy private key từ serialized `toString()` hoặc các trường phản chiếu. Một handle khác raw key material.

## 3. Khi được phép xuất key, phải hiểu đúng định dạng

| Loại | `getFormat()` thường gặp | Bytes trả về | API dựng lại |
| --- | --- | --- | --- |
| AES/HMAC secret key phần mềm | `RAW` | Secret bytes có entropy thích hợp | `SecretKeySpec(raw,"AES")` hay tên algorithm tương ứng |
| RSA public | `X.509` | DER SubjectPublicKeyInfo | `KeyFactory("RSA").generatePublic(new X509EncodedKeySpec(der))` |
| RSA private | `PKCS#8` | DER PrivateKeyInfo | `KeyFactory("RSA").generatePrivate(new PKCS8EncodedKeySpec(der))` |
| EC public/private phần mềm | `X.509` / `PKCS#8` | DER có thuật toán/đường cong | `KeyFactory("EC")` với spec đúng loại |
| Khóa HSM không cho xuất | có thể `null` | `getEncoded()==null` | Dùng key handle qua provider, không nhập lại từ byte[] |

Độ dài đúng của AES chỉ là điều kiện cú pháp: 16/24/32 byte **không bảo đảm entropy**. `SecretKeySpec` không tạo randomness, không tự kiểm tra nguồn tin cậy và **không tạo key nằm trong HSM** từ một mảng thông thường. Dùng `KeyGenerator` và `SecureRandom` cho khóa mới, hoặc raw bytes đã được cung cấp an toàn.

Không nhầm **PEM** (Base64 text armor) với **DER** (mã hóa ASN.1 nhị phân): `PKCS8EncodedKeySpec` nhận DER, không nhận bytes ASCII của `-----BEGIN PRIVATE KEY-----`. Và `BEGIN PRIVATE KEY` là PKCS#8 **không mã hóa**; `BEGIN ENCRYPTED PRIVATE KEY` là container bảo vệ mật khẩu/thuật toán riêng, cần xử lý `EncryptedPrivateKeyInfo` trước. Base64/hex chỉ là encoding, không làm private key bí mật hơn.

### Rủi ro của việc export

Gọi `getEncoded()` trên private/secret key là **tạo thêm một bản sao dữ liệu nhạy cảm**. Tránh thực hiện chỉ để làm fingerprint, debug hay chuyển object giữa các module. Nếu phải export để backup hoặc migration: giới hạn người được phép, thiết lập kênh mã hóa, nguyên tắc least privilege, audit, key wrapping và xóa bản sao theo chính sách.

`Arrays.fill(bytes,(byte)0)` giúp giảm lifetime của mảng ứng dụng, nhưng không xóa bản sao key bên trong `SecretKeySpec`, provider, `Cipher`, JVM hoặc bản dump đã tạo. Chuyển private key thành `String` càng khó xóa vì immutable. Việc `getEncoded()==null` cũng không bảo đảm tất cả nội bộ JVM không chứa vật liệu nhạy cảm.

## 4. Chương trình Java 17+: export AES/RSA và ví dụ key opaque giả lập

Lưu thành **`ExportabilityDemo.java`**. Chương trình đầy đủ sau đây:

1. Sinh AES-256 bằng `KeyGenerator`, lấy encoding raw của software key.
2. Dựng `SecretKeySpec` từ bytes, dùng AES-GCM mã hóa bằng key gốc và giải mã bằng key nhập lại.
3. Xóa mảng bytes trả về từ `getEncoded()` rồi xác nhận key gốc **vẫn còn**.
4. Định nghĩa một `SecretKey` giả không có encoding (trả `null`); provider phần mềm từ chối dùng nó. Đây **không phải HSM mock hợp lệ**, mà là bằng chứng rằng API method đơn lẻ không đủ.
5. Export/import RSA private `PKCS#8` và RSA public `X.509`, ký một thông điệp và kiểm chứng chữ ký.

```java
import java.nio.charset.StandardCharsets;
import java.security.InvalidKeyException;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class ExportabilityDemo {
    private static final class OpaqueLookingKey implements SecretKey {
        public String getAlgorithm() { return "AES"; }
        public String getFormat() { return null; }
        public byte[] getEncoded() { return null; }
    }

    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();
        KeyGenerator kg = KeyGenerator.getInstance("AES");
        kg.init(256, random);
        SecretKey aes = kg.generateKey();

        byte[] exported = aes.getEncoded();
        if (exported == null) {
            throw new IllegalStateException("This demo requires exportable AES");
        }
        try {
            System.out.println("aesFormat=" + aes.getFormat());
            System.out.println("aesRawBytes=" + exported.length);
            SecretKey imported = new SecretKeySpec(exported, "AES");

            byte[] nonce = new byte[12];
            random.nextBytes(nonce);
            byte[] message = "key lifecycle".getBytes(StandardCharsets.UTF_8);
            Cipher encryption = Cipher.getInstance("AES/GCM/NoPadding");
            encryption.init(Cipher.ENCRYPT_MODE, aes,
                    new GCMParameterSpec(128, nonce));
            byte[] ciphertext = encryption.doFinal(message);
            Cipher decryption = Cipher.getInstance("AES/GCM/NoPadding");
            decryption.init(Cipher.DECRYPT_MODE, imported,
                    new GCMParameterSpec(128, nonce));
            System.out.println("aesRoundTrip=" +
                    Arrays.equals(message, decryption.doFinal(ciphertext)));

            Arrays.fill(exported, (byte) 0);
            byte[] checkCopy = aes.getEncoded();
            try {
                System.out.println("clearingCopyDoesNotDestroyKey="
                        + !MessageDigest.isEqual(exported, checkCopy));
            } finally {
                Arrays.fill(checkCopy, (byte) 0);
            }

            OpaqueLookingKey fake = new OpaqueLookingKey();
            System.out.println("mockEncodedNull=" + (fake.getEncoded() == null));
            try {
                Cipher unsupported = Cipher.getInstance("AES/GCM/NoPadding");
                unsupported.init(Cipher.ENCRYPT_MODE, fake,
                        new GCMParameterSpec(128, nonce));
                System.out.println("mockAccepted=false");
            } catch (InvalidKeyException expected) {
                System.out.println("mockRejectedByProvider=true");
            }
        } finally {
            Arrays.fill(exported, (byte) 0);
        }

        KeyPairGenerator rsa = KeyPairGenerator.getInstance("RSA");
        rsa.initialize(2048, random);
        KeyPair pair = rsa.generateKeyPair();
        byte[] publicDer = pair.getPublic().getEncoded();
        byte[] privateDer = pair.getPrivate().getEncoded();
        if (publicDer == null || privateDer == null) {
            throw new IllegalStateException("RSA example needs exportable keys");
        }
        try {
            System.out.println("rsaPublicFormat=" + pair.getPublic().getFormat());
            System.out.println("rsaPrivateFormat=" + pair.getPrivate().getFormat());
            KeyFactory factory = KeyFactory.getInstance("RSA");
            Signature signer = Signature.getInstance("SHA256withRSA");
            signer.initSign(factory.generatePrivate(
                    new PKCS8EncodedKeySpec(privateDer)));
            byte[] message = "check".getBytes(StandardCharsets.UTF_8);
            signer.update(message);
            byte[] signature = signer.sign();
            Signature verifier = Signature.getInstance("SHA256withRSA");
            verifier.initVerify(factory.generatePublic(
                    new X509EncodedKeySpec(publicDer)));
            verifier.update(message);
            System.out.println("importedRsaSignatureValid="
                    + verifier.verify(signature));
        } finally {
            Arrays.fill(publicDer, (byte) 0);
            Arrays.fill(privateDer, (byte) 0);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 ExportabilityDemo.java
java ExportabilityDemo
```

Đầu ra trên JDK/SunJCE + RSA provider đã kiểm thử:

```text
aesFormat=RAW
aesRawBytes=32
aesRoundTrip=true
clearingCopyDoesNotDestroyKey=true
mockEncodedNull=true
mockRejectedByProvider=true
rsaPublicFormat=X.509
rsaPrivateFormat=PKCS#8
importedRsaSignatureValid=true
```

Giải thích: `getEncoded()` cung cấp bytes mà ứng dụng có thể sao chép; việc làm sạch bản sao không hủy đối tượng `aes` đã sinh. `OpaqueLookingKey` cố ý **không có provider nào quản lý**: `mockEncodedNull=true` không đồng nghĩa key bảo mật, còn `mockRejectedByProvider=true` là kết quả cụ thể của provider AES trong phép thử.

**GCM nonce:** `nonce` 12 byte chỉ được dùng **một lần để mã hóa**, rồi dùng lại **đúng cho phép giải mã ciphertext đó**. Với lần **mã hóa mới** dưới cùng AES key, phải chọn nonce **khác**; cặp key+nonce không được lặp.

**Ký RSA:** `KeyFactory` được chọn theo `RSA`. Với public key dùng `X509EncodedKeySpec`, private key dùng `PKCS8EncodedKeySpec`. Chữ ký được xác thực nghĩa là import hoạt động đúng, nhưng không chứng minh việc export private key là chính sách an toàn cho sản phẩm.

## 5. Java KeyStore có tự làm khóa non-exportable không?

**Không.** `java.security.KeyStore` là abstraction lưu và tìm `PrivateKeyEntry`, `SecretKeyEntry`, `TrustedCertificateEntry`. Khả năng raw export tùy **store type/provider, key attributes và nơi key material thực sự cư trú**.

| Loại | Đặc điểm | Có thể export key? |
| --- | --- | --- |
| `PKCS12` software | Container/file bảo vệ bằng password; entry được lấy khi mở store | Có thể export; demo dưới đây chứng minh |
| `JKS` truyền thống | Software keystore chủ yếu với private keys/certificates | Phụ thuộc entry/implementation; không phải HSM |
| `PKCS11` trên token/HSM | Provider gọi native PKCS#11, handle có thuộc tính security | Có thể không export theo policy hardware |
| Android Keystore | Key handle qua OS/backend hardware khi khả dụng | Nhiều private/secret keys không cho export; phụ thuộc API/device |
| Cloud KMS | Key ID, IAM, audit, API/RPC tới dịch vụ | Nhiều key không xuất raw; SDK có thể không cung cấp JCA `Key` |

Password-protected PKCS12 bảo vệ **bản lưu ở trạng thái nghỉ**. Nhưng sau khi unlock, software key có thể vẫn cho `getEncoded()`; điều này **khác** key chưa từng rời HSM.

### 5.1 Chương trình: PKCS12 có thể chứa AES SecretKeyEntry exportable

Lưu thành **`Pkcs12ExportabilityDemo.java`**. Ví dụ chạy trong memory, không tạo file key trên disk. Nó lưu một AES-256 key trong PKCS12, nạp lại bằng đúng password rồi so sánh raw bytes. Password mẫu chỉ phục vụ demo, không được hardcode trong code sản phẩm.

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class Pkcs12ExportabilityDemo {
    public static void main(String[] args) throws Exception {
        char[] storePassword = "demo-store-password".toCharArray();
        char[] entryPassword = "demo-entry-password".toCharArray();
        byte[] storedBytes = null;
        byte[] recoveredBytes = null;

        try {
            KeyGenerator generator = KeyGenerator.getInstance("AES");
            generator.init(256, new SecureRandom());
            SecretKey generated = generator.generateKey();
            storedBytes = generated.getEncoded();
            if (storedBytes == null) {
                throw new IllegalStateException("Demo requires exportable key");
            }

            KeyStore store = KeyStore.getInstance("PKCS12");
            store.load(null, storePassword);
            KeyStore.ProtectionParameter protection =
                    new KeyStore.PasswordProtection(entryPassword);
            store.setEntry("session-key",
                    new KeyStore.SecretKeyEntry(generated), protection);
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            store.store(output, storePassword);

            KeyStore restored = KeyStore.getInstance("PKCS12");
            restored.load(new ByteArrayInputStream(output.toByteArray()),
                    storePassword);
            SecretKey restoredKey =
                    (SecretKey) restored.getKey("session-key", entryPassword);
            recoveredBytes = restoredKey.getEncoded();

            System.out.println("keystoreType=" + restored.getType());
            System.out.println("isSecretKeyEntry="
                    + restored.entryInstanceOf(
                            "session-key", KeyStore.SecretKeyEntry.class));
            System.out.println("recoveredExportable="
                    + (recoveredBytes != null));
            System.out.println("sameRawMaterial="
                    + (recoveredBytes != null
                    && MessageDigest.isEqual(storedBytes, recoveredBytes)));
        } finally {
            Arrays.fill(storePassword, '\0');
            Arrays.fill(entryPassword, '\0');
            if (storedBytes != null) Arrays.fill(storedBytes, (byte) 0);
            if (recoveredBytes != null) Arrays.fill(recoveredBytes, (byte) 0);
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 Pkcs12ExportabilityDemo.java
java Pkcs12ExportabilityDemo
```

```text
keystoreType=PKCS12
isSecretKeyEntry=true
recoveredExportable=true
sameRawMaterial=true
```

**Diễn giải:** PKCS12 được mở và trích xuất `SecretKeyEntry` thành công; `recoveredExportable=true` chứng minh keystore **không tự tạo ràng buộc non-extractable**. Một provider khác có thể khác về hỗ trợ SecretKeyEntry/password; phải kiểm thử runtime thực tế. Mặc dù không ghi file key, `ByteArrayOutputStream` và các key objects vẫn giữ bản sao nhạy cảm trong heap, nên demo **không** chứng minh memory erasure an toàn.

## 6. Opaque key thật cần provider biết handle và key policy

Một key trên HSM có thể được đại diện bằng một đối tượng `PrivateKey` mà `getEncoded() == null`. Khi đó:

```text
Java KeyStore("PKCS11") --lookup alias--> HSM-backed PrivateKey handle
                                 |
Signature.initSign(handle) -------+-- token provider -- HSM sign()
                                            |
                                      signature bytes
```

Ở đây **private key material nằm trong HSM**, nhưng Java có thể nhận chữ ký. Muốn thay đổi thao tác cần dùng cơ chế được thiết bị hỗ trợ: một key chỉ cho `sign` không mặc nhiên cho `decrypt` hay `derive`. Nếu key nằm trên KMS cloud, hoạt động có thể được cung cấp qua REST/gRPC SDK chứ **không** qua JCA `Signature` hay `KeyStore`; không mặc định KMS nào cũng cung cấp JCA adapter.

**Provider matching:** `Signature.getInstance("SHA256withRSA",tokenProvider)` chỉ hữu ích nếu provider và key handle hỗ trợ thuật toán đó. `Cipher.getInstance("AES/GCM/NoPadding")` không bảo đảm chọn đúng provider cho một key opaque; nếu rơi vào software provider không hiểu handle, `Cipher.init` có thể ném `InvalidKeyException`. Cần chọn engine đúng nhà cung cấp, đúng transformation và đúng key usage.

### Khung tích hợp SunPKCS11 (không chạy độc lập)

```java
// CHỈ MINH HỌA: cần token/HSM, native PKCS#11 library, config,
// key alias, quyền và PIN thật. Không hardcode PIN.
java.security.Provider base =
        java.security.Security.getProvider("SunPKCS11");
if (base == null) {
    throw new IllegalStateException("SunPKCS11 unavailable");
}
java.security.Provider tokenProvider =
        base.configure("/secure/config/token-pkcs11.cfg");
java.security.KeyStore store =
        java.security.KeyStore.getInstance("PKCS11", tokenProvider);
store.load(null, pin);

java.security.Key key = store.getKey("signing-key", null);
if (!(key instanceof java.security.PrivateKey privateKey)) {
    throw new IllegalStateException("Signing key not found");
}
java.security.Signature signer =
        java.security.Signature.getInstance(
                "SHA256withRSA", tokenProvider);
signer.initSign(privateKey);
// signer.update(messageBytes); byte[] signature = signer.sign();
// Token/session cleanup và audit theo vendor policy.
```

`SunPKCS11` liên quan module `jdk.crypto.cryptoki` trong JDK có hỗ trợ. Có thể thiếu trên runtime tối giản; file cấu hình và native PKCS#11 library/slot/token phải được tạo chính xác. Token login/session và alias mapping có thể khác nhau. Đoạn này **không tạo được opaque key** nếu chưa có HSM và key generation policy thực; không dùng để giả vờ HSM hoạt động chỉ vì `getEncoded()==null`.

### Key usage vẫn có thể nguy hiểm

Non-extractable key chỉ giúp hạn chế **lấy raw material**. Nếu attacker chiếm quyền service gọi `sign`, họ có thể tạo chữ ký không được phép; nếu có quyền gọi `decrypt`, họ có thể lấy plaintext trả về. **HSM/KMS không thay thế authorization**. Hạn chế payload được xử lý, key usage, IAM, rate limits, context/tenant, audit, session lifetime và dual control theo rủi ro.

## 7. Các quyền và thuật ngữ phải phân biệt

| Thuật ngữ | Câu hỏi thực sự | Hệ quả |
| --- | --- | --- |
| Exportable qua `getEncoded` | Có thể nhận raw/DER bytes qua Java API không? | Cho phép sao chép/nhập lại khi có quyền |
| Non-extractable | Device có cấm trích xuất key bằng mọi mechanism được policy áp dụng không? | Phụ thuộc token/HSM và thuộc tính tạo key |
| Sensitive | Device có che giấu private attributes không? | Không đồng nghĩa mọi phép toán đều bị cấm |
| Sign/decrypt/derive permission | Key được thực hiện operation nào? | Từng quyền độc lập; không suy từ key type |
| Wrappable | Cho phép xuất **dưới dạng được bọc bằng KEK** không? | Có thể có policy riêng cho wrapped export |
| Migratable/backup | Có cơ chế backup giữa HSM/cluster hoặc restore không? | Không mặc định có ở key non-exportable |
| Destroyable/deletable | Có thể revoke/hủy key trong backend không? | Xóa object reference Java không bằng hủy key thật |

Trong PKCS#11, có các thuộc tính như `CKA_EXTRACTABLE`, `CKA_SENSITIVE`, `CKA_SIGN`, `CKA_DECRYPT`, `CKA_WRAP`, `CKA_UNWRAP`; **tập thuộc tính và ràng buộc** của token quyết định kết quả. Không khẳng định một flag duy nhất là đầy đủ nếu chưa xem standard/vendor policy và cơ chế wrap/trusted key.

`Cipher.wrap(key)` thuộc JCE engine wrap mode. Nó không thể **vượt** chính sách non-extractable bằng phép màu; backend sẽ từ chối nếu key không được export theo cơ chế wrap tương ứng. Ngược lại, một số key chỉ cho wrapped migration tới KEK đáng tin: đó là **export dưới lớp bảo vệ có kiểm soát**, không phải raw export tự do.

## 8. Vòng đời key trong hai mô hình

| Vòng đời | Software exportable | Provider-bound/non-extractable |
| --- | --- | --- |
| Tạo | `KeyGenerator`/`KeyPairGenerator` software hoặc raw material hợp lệ | Generate **trực tiếp trên token/HSM/KMS** với policy non-extractable từ đầu |
| Nhập | `SecretKeySpec`, `KeyFactory` theo định dạng | Import qua API backend và thuộc tính key; không chỉ tạo `KeySpec` |
| Lưu | PKCS12/wrapped bytes/secret storage, kiểm soát file/backup | Application lưu key ID/alias; backend giữ material |
| Sử dụng | Software provider; raw key có thể đến heap | Engine/provider hoặc SDK làm operations theo key handle và quyền |
| Backup/restore | Tạo bản sao/wrapped backup có bảo vệ | Cơ chế vendor HSM cluster/backup/HA, đôi khi không cho export |
| Rotation | Tạo version mới, rewrap/re-encrypt và quản lý key cũ | Backend cấp version/alias mới; key cũ vẫn cần để đọc dữ liệu được phép |
| Hủy | Xử lý tất cả raw copies, file, backup, phiên bản | Backend revoke/delete và session handling; GC không phải hủy vật liệu |

**Nếu yêu cầu “private key không bao giờ ra khỏi HSM”:** phải sinh key **trên HSM** ngay từ đầu với policy phù hợp. Không thể khẳng định ràng buộc ấy sau khi sinh key bằng Java software rồi export/import vào thiết bị: raw material đã từng tồn tại bên ngoài.

**Backup là yêu cầu kiến trúc:** key non-exportable không có kế hoạch HA/backup có thể mất vĩnh viễn khi token hỏng, khiến ciphertext cũ không giải mã được. Đừng đặt ràng buộc không-export rồi quên phương án phục hồi hợp lệ. Hỗ trợ backup có thể đòi nhiều thiết bị và vendor mechanisms, không đồng nghĩa cho phép export raw.

**Thay key:** mỗi ciphertext/signature nên có key ID/version hoặc metadata để xác định đúng key. Key mới không tự giải mã dữ liệu do key cũ mã hóa; phải giữ version cũ theo thời hạn hoặc thực hiện re-encryption/rewrapping có kiểm soát. Đừng xóa key cũ trước khi xác minh khối lượng dữ liệu đã migrate.

## 9. Thiết kế API không ép mọi key thành byte[]

Một service thường nên yêu cầu **operation**, không yêu cầu raw key:

```java
// API minh họa thiết kế, không phải chương trình độc lập.
interface SigningGateway {
    byte[] sign(String keyId, byte[] message) throws Exception;
}

interface DecryptionGateway {
    byte[] decrypt(String keyId, byte[] ciphertext,
                   byte[] associatedData) throws Exception;
}
```

Implementation có thể là phần mềm `Signature.initSign(privateKey)`, HSM provider với private key handle, hoặc cloud KMS SDK RPC. Caller không cần `privateKey.getEncoded()`. Khi cần fingerprint, hãy lấy **public key** hoặc key ID đáng tin; **không export private key chỉ để in hash/private fingerprint**.

Lưu metadata phù hợp: provider/backend identifier, algorithm, key ID, key version, allowed purposes và thông tin rotation. Tránh lưu class name của handle làm định danh bền vững; token session có thể hết hạn, provider object có thể không portable qua restart. Sau restart, lookup lại theo alias/key ID và chính sách xác thực backend.

`KeyStore` hay provider API không bắt buộc dùng chung một instance toàn hệ thống: cryptographic engines như `Cipher`, `Mac`, `Signature` có state riêng, không nên chia sẻ trạng thái giữa thread/request nếu không có hợp đồng thread-safety cụ thể. Khi provider timeout, xử lý retry/idempotency thích hợp cho từng operation và không âm thầm fallback ra software để lấy secret.

## 10. So sánh trade-off và chọn mô hình

| Tiêu chí | Exportable software key | Provider-only key |
| --- | --- | --- |
| Khả năng di chuyển giữa provider | Thường cao nếu format raw/DER chuẩn | Phụ thuộc vendor, sessions, SDK và migration policy |
| Kiểm soát trích xuất raw | Process có thể đọc/copy raw khi được phép | Backend có thể cấm raw extraction thực sự |
| Sao lưu/phục hồi | Dễ copy nhưng nhiều bản sao cần bảo vệ | Backup có thể phức tạp, phải có HA/cluster phù hợp |
| Tốc độ và độ trễ | Software local thường thuận lợi cho nhiều thao tác | Hardware/RPC có throughput/latency/quota riêng |
| Số thuật toán hỗ trợ | Theo JDK/provider phần mềm | Theo firmware/token mechanisms/service API |
| Khi process bị xâm nhập | Có thể bị đánh cắp key rồi dùng offline | Có thể lạm dụng sign/decrypt trong phạm vi quyền, khó lấy raw nếu policy đúng |
| Độ phức tạp quản trị | Keystore/secret manager, filesystem, backup, key rotation | IAM, PIN, sessions, audit, availability, key ceremony, disaster recovery |

**Không có lựa chọn tốt nhất cho mọi trường hợp.** Khóa ký của CA/gateway tài chính, master KEK hoặc root key quan trọng thường có yêu cầu kiểm soát mạnh hơn khóa phiên ngắn hạn trong một process cô lập. Chọn theo tài sản cần bảo vệ, threat model, vòng đời, latency, khả năng phục hồi và compliance.

## 11. Sai lầm phổ biến và cách xử lý

| Biểu hiện | Nguyên nhân | Biện pháp |
| --- | --- | --- |
| `NullPointerException` sau `getEncoded()` | Opaque key trả `null` hợp lệ | Kiểm tra `null`, chọn provider operation thay vì cố export |
| `InvalidKeyException` tại `Cipher.init` hoặc `Signature.initSign` | Sai key type/provider, policy không cho operation | Dùng đúng provider/mechanism và key usage |
| `UnrecoverableKeyException`, `KeyStoreException` | Sai alias, entry password/PIN, store type hay policy | Kiểm tra type, credentials và session |
| `NoSuchAlgorithmException` / `NoSuchProviderException` | Algorithm/provider không được cấu hình/hỗ trợ | Kiểm tra runtime và capabilities |
| `getFormat()==null` | Provider không cung cấp encoding portable | Không ép `KeyFactory` import từ dữ liệu không tồn tại |
| Coi `PKCS12` là HSM | Nhầm password-protected file với token | Kiểm tra key location và backend policy |
| Tự implement `SecretKey` trả `null` rồi mong sử dụng | Không có provider sở hữu handle | Cần API/provider thực sự |
| Bọc khóa bằng `Cipher.wrap` nhưng bị từ chối | Key có restriction non-extractable/wrapping | Theo policy; không bypass bằng export |
| Key mới không giải mã được ciphertext cũ | Không quản lý key ID/version hoặc xóa key cũ | Versioning/re-wrapping/re-encrypt có kế hoạch |
| HSM private key bị lạm dụng dù không export | Service được phép ký/giải mã đầu vào attacker chọn | Authorization theo nghiệp vụ, audit và rate limits |
| Xóa byte[] rồi nghĩ đã xóa key | Key object/provider vẫn giữ bản sao | Hạn chế export và quản lý lifecycle đúng backend |
| Token/session restart làm handle không hợp lệ | Handle gắn session/backend | Lookup lại theo alias/key ID và tái xác thực |
| KMS chỉ có RPC nhưng code ép vào `KeyStore` | Không có JCA bridge phù hợp | Dùng SDK/adapter chính thức |
| Downgrade tự động sang software khi HSM lỗi | Fallback phá vỡ policy non-extractable | Fail closed, báo lỗi và theo escalation process |

### Checklist triển khai

- [ ] Chọn exportable hay non-exportable **trước khi sinh key**, dựa trên threat model và backup requirement.
- [ ] Biết chính xác `KeyStore` type/provider/backend, không suy đoán từ tên API.
- [ ] `getEncoded()==null` được xử lý có chủ đích; không tự tạo key rỗng hay xuất raw bằng đường vòng.
- [ ] Không log/serialize raw private/secret key; hạn chế sao chép và xử lý memory.
- [ ] Chọn provider tương thích với key handle và operation; kiểm tra usage policy.
- [ ] Phân quyền ở mức key ID, tenant, thao tác và nội dung nghiệp vụ; có audit và rate limit.
- [ ] Biết wrapped export khác raw export; không dùng `wrap` để vượt policy token.
- [ ] Có key version, vòng đời, rotation, rollback, HA/backup và disaster-recovery test.
- [ ] Đã thử key disabled, HSM unavailable, PIN sai, alias không tồn tại và provider mismatch.
- [ ] Hủy/thu hồi theo backend, không đồng nhất xóa biến Java với hủy key trong thiết bị.

## 12. Câu hỏi tự kiểm tra

1. **`getEncoded()==null` có chứng minh key nằm trong phần cứng không?** Không; chỉ có nghĩa method không cung cấp encoded bytes.
2. **Một `SecretKey` giả trả `null` có được SunJCE dùng như HSM key không?** Không; nó thiếu key material/handle được provider nhận diện.
3. **AES-256 software key `RAW` dài bao nhiêu byte?** 32 byte.
4. **RSA public/private thường export theo định dạng gì?** Public `X.509` SPKI, private `PKCS#8` DER.
5. **Xóa mảng lấy từ `getEncoded()` đã xóa đối tượng key gốc chưa?** Chưa; key gốc/provider giữ state riêng.
6. **PKCS12 password-protected có đồng nghĩa non-extractable?** Không; key tải ra có thể `getEncoded()` như demo.
7. **Một key chỉ `CKA_SIGN` có tự cho phép `decrypt` không?** Không; policy thao tác riêng.
8. **`Cipher.wrap` có tự lấy được mọi opaque key không?** Không; phụ thuộc key extraction/wrap policy và engine mechanism.
9. **Private key chưa từng rời HSM có nên tạo bằng software trước rồi import vào HSM không?** Không, trái điều kiện “chưa từng”.
10. **Cloud KMS luôn trả `java.security.PrivateKey` dùng được với JCE không?** Không, có KMS chỉ cung cấp SDK/RPC.
11. **Không xuất được raw key thì attacker không gây hại được nữa?** Sai; họ có thể lạm dụng `sign/decrypt` nếu có quyền gọi.
12. **Nếu mất HSM chứa key non-exportable mà không có backup thì sao?** Có thể không phục hồi được dữ liệu mã hóa.
13. **Vai trò của key ID/version khi rotation?** Tra đúng key cho bản ghi cũ hoặc xác định bản ghi cần migrate.
14. **Làm sao biết key thật sự non-extractable?** Kiểm tra policy/backend/token và thử các thao tác được phép/không phép trong quy trình bảo mật, không chỉ dựa `getEncoded()`.
15. **Khi cần thiết kế API tích hợp HSM/KMS, nên truyền raw bytes hay yêu cầu phép toán?** Ưu tiên interface operation dùng key ID/handle, hạn chế raw key tiếp xúc ứng dụng.

## Tài liệu API chính thức (Java SE 21) và tham khảo

- [Key: getAlgorithm, getFormat, getEncoded](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Key.html)
- [SecretKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/SecretKey.html)
- [PrivateKey và PublicKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/PrivateKey.html)
- [KeyGenerator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KeyGenerator.html)
- [SecretKeySpec](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/SecretKeySpec.html)
- [KeyFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyFactory.html)
- [KeyStore, SecretKeyEntry và PasswordProtection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.html)
- [Provider](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Provider.html)
- [Java PKCS#11 Reference Guide](https://docs.oracle.com/en/java/javase/21/security/pkcs11-reference-guide1.html)
- [Cipher và wrap/unwrap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html)
- [Signature](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Signature.html)
- [Destroyable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/Destroyable.html)
