# 11.1. Phân loại khóa dữ liệu, khóa bọc khóa và khóa ký theo trách nhiệm

## Mục tiêu bài học

Trong một hệ thống Java dùng mật mã, từ “khóa” có thể chỉ nhiều loại bí mật với **trách nhiệm và hậu quả lộ lọt khác nhau**. Không nên dùng một khóa AES cho mọi việc, cũng không nên xem private key ký số là “khóa mã hóa mạnh hơn”. Thiết kế đúng cần phân chia rõ:

1. **Data Encryption Key (DEK)**: trực tiếp mã hóa/giải mã dữ liệu ứng dụng.
2. **Key Encryption Key (KEK)**, còn gọi *key-wrapping key*: bảo vệ DEK hoặc key material khác khi lưu trữ/vận chuyển.
3. **Signing key**: private key tạo chữ ký số, đi cùng public key dùng để xác minh nguồn gốc/tính toàn vẹn của thông điệp.

Sau bài này, bạn có thể nhận diện đúng vai trò của từng khóa, gắn thao tác JCA phù hợp, thiết kế một **envelope encryption** cơ bản, kiểm tra dữ liệu được ký, lựa chọn nơi giữ khóa và quyền truy cập, cũng như phân biệt **rewrap KEK**, **reencrypt DEK** và **thay signing key**.

Các ví dụ dùng **Java 17+**, AES-GCM để mã hóa dữ liệu, AES Key Wrap (RFC 3394) để bọc DEK và RSA-PSS để ký một bản ghi. Ví dụ dùng khóa phần mềm sinh trong RAM để minh họa API, **không phải** hệ thống quản lý khóa production hoàn chỉnh.

## 1. Ba loại khóa giải quyết ba câu hỏi khác nhau

| Vai trò | Câu hỏi nó giải quyết | Khóa và thao tác điển hình | Đối tượng được bảo vệ |
| --- | --- | --- | --- |
| **DEK** — khóa dữ liệu | “Ai có thể đọc nội dung bí mật?” | `SecretKey` AES; `Cipher.getInstance("AES/GCM/NoPadding")`, `ENCRYPT_MODE`/`DECRYPT_MODE` | Plaintext của file, bản ghi, blob hoặc field |
| **KEK** — khóa bọc khóa | “Ai có thể khôi phục/sử dụng DEK đã lưu dưới dạng bọc?” | AES-KEK cùng `Cipher.getInstance("AESWrap")`, `WRAP_MODE`/`UNWRAP_MODE`; hoặc cơ chế wrapping/transport khác đã phê duyệt | **Key material** của DEK hoặc khóa con |
| **Signing key** — khóa ký | “Thông điệp/bản ghi có được ký bởi chủ thể kiểm soát private key đã được tin cậy không?” | RSA/EC/EdDSA private key qua `Signature`; public key tương ứng dùng `verify` | Tính toàn vẹn và xác thực nguồn ký của thông điệp/metadata đã ký |

**Các phát biểu dễ nhầm:**

- DEK **mã hóa dữ liệu**, KEK **mã hóa/bọc khóa**. Dù cả hai có thể là khóa AES 128/256 bit, vai trò, phạm vi truy cập, thời hạn và cách xoay vòng **khác nhau**. “Cùng thuật toán AES” không làm chúng có thể hoán đổi trách nhiệm.
- **Private signing key** là bí mật; **public verification key** có thể được phân phối cho bên xác minh, nhưng **cách gắn nó với danh tính đáng tin** vẫn phải được kiểm chứng. Public key không giúp giải mã DEK.
- Một chữ ký số **không giữ bí mật** nội dung. Mã hóa xác thực AES-GCM bảo đảm ciphertext không thể bị sửa mà không bị phát hiện (khi key/nonce/AAD được dùng đúng), nhưng **không tự chứng minh danh tính tổ chức gửi** cho người nhận cùng nắm DEK. Hai dịch vụ bảo vệ khác nhau.
- **HMAC key** là khóa đối xứng xác thực dữ liệu qua `javax.crypto.Mac`. HMAC có tác dụng xác thực giữa các bên cùng giữ bí mật nhưng **không phải** private signing key dùng với `Signature` và public-key verification. Không tự gọi khóa HMAC là “khóa ký RSA” hoặc xem HMAC có tính chất xác minh công khai.
- **Key Derivation Key (KDK)/master key** có thể là loại thứ tư, dùng để dẫn xuất key qua KDF. Không mặc nhiên xem một master key đồng thời là DEK, KEK và signing key; phải thiết kế domain separation đúng theo primitive/protocol.

NIST SP 800-57 Part 1 phân loại các loại khóa theo **cryptographic function**, cùng các khía cạnh vòng đời và bảo vệ riêng. Một nguyên tắc quan trọng là **giới hạn khóa vào mục đích đã được cấp**, giúp thu hẹp thiệt hại khi khóa bị lộ và đơn giản hóa audit, thu hồi, phân quyền.

## 2. Hiểu DEK (Data Encryption Key) cho đúng

**Nhiệm vụ duy nhất theo chính sách:** mã hóa và giải mã dữ liệu ở một ranh giới cụ thể (tài liệu, đối tượng lưu trữ, tenant hoặc phiên; tùy kiến trúc).

Ví dụ một hệ thống lưu trữ tài liệu:

- Tạo một DEK ngẫu nhiên AES-256 hoặc AES-128 cho **một tài liệu**.
- Tạo nonce/IV thích hợp cho mỗi lần mã hóa bằng AES-GCM; một cấu hình thông dụng là **nonce 12 byte**, tag 128 bit.
- Mã hóa plaintext: `Cipher.getInstance("AES/GCM/NoPadding")`, `init(ENCRYPT_MODE, dek, new GCMParameterSpec(128, nonce))`, tùy chọn `updateAAD`, rồi `doFinal(plaintext)`.
- Chỉ giữ ciphertext, nonce và metadata cần thiết cùng **DEK đã được bọc**; không lưu plaintext DEK bên cạnh ciphertext dưới dạng không bảo vệ.
- Khi đọc, chỉ thành phần có quyền truy cập dữ liệu và quyền giải bọc phù hợp mới được lấy DEK rồi decrypt.

**Phạm vi DEK là lựa chọn bảo mật:** một DEK cho mỗi object giúp tách ảnh hưởng nếu một DEK bị lộ; một DEK cho cả tenant có thể giảm số key nhưng mở rộng phạm vi thiệt hại. Quyết định cần dựa vào kích thước dữ liệu, lưu lượng, quy tắc phân quyền, hiệu năng và quy trình reencrypt.

**AES-GCM lưu ý:** tuyệt đối tránh trùng **(DEK, nonce)** cho hai lần mã hóa khác nhau; tạo DEK ngẫu nhiên mới cho object giúp giảm nguy cơ nhưng **không loại bỏ yêu cầu nonce unique** nếu cùng DEK dùng nhiều lần. Truyền/lưu nonce cùng ciphertext là bình thường vì nonce không phải key; bảo vệ tính toàn vẹn và binding theo protocol. Nếu sai DEK/nonce/AAD/tag, decryption phải thất bại và ứng dụng không sử dụng plaintext trước khi `doFinal` xác thực thành công.

DEK thường cần có mặt ở nơi **thực sự thực hiện phép mã hóa/giải mã**. Nếu chạy phần mềm trong app, có thể có bản DEK plaintext trong RAM ngắn hạn, nên hạn chế log, heap dump, telemetry, truyền qua service và thời gian sống. HSM/KMS có thể thực hiện cryptographic operation trực tiếp hoặc cấp plaintext DEK cho client tùy API; đừng giả định cứ “sử dụng KMS” là DEK không bao giờ rời KMS.

## 3. Hiểu KEK (Key Encryption Key) cho đúng

**Nhiệm vụ:** bảo vệ khóa khác, ví dụ DEK, khi khóa này phải lưu trong database, object metadata hoặc chuyển qua một biên tin cậy. KEK thường được quản lý tập trung hơn DEK và có thể bọc **rất nhiều DEK**.

Một hệ thống có thể dùng:

- **KEK đối xứng** (AES) và chuẩn **AES Key Wrap** theo RFC 3394/NIST SP 800-38F, hoặc AES Key Wrap with Padding theo RFC 5649.
- **Public key wrapping/transport** cho trường hợp nhận dữ liệu bằng khóa công khai; cơ chế cụ thể (ví dụ RSA-OAEP) có format và ràng buộc riêng. Không dùng raw RSA hoặc RSA signing key chung cho “ký và bọc khóa”.
- **KMS/HSM wrapping key** có usage policy `wrap/unwrap`, key ID, version và audit, trong đó ứng dụng không có plaintext KEK khi provider/HSM hỗ trợ API này.

Trong Java 17, `Cipher.getInstance("AESWrap")` tương ứng AES-KW (RFC 3394), được tài liệu Java Standard Algorithm Names liệt kê. `Cipher.getInstance("AESWrapPad")` tương ứng AES-KWP (RFC 5649). Một môi trường/provider cụ thể có thể không triển khai tất cả tên; luôn kiểm tra hỗ trợ và test interoperability.

Sơ đồ wrapping đối xứng:

```text
DEK (secret key bytes / key handle)
      |
      | Cipher AESWrap + KEK (bí mật hơn / cấp quản lý)
      v
wrapped DEK (ciphertext dạng key blob)  ---> có thể lưu cùng ciphertext dữ liệu
      |
      | chỉ actor được cấp phép mới được UNWRAP qua KEK
      v
DEK khôi phục -> sử dụng với thuật toán mã hóa dữ liệu được cho phép
```

**Tính chất quan trọng:**

- **Wrapped DEK không phải mật khẩu**, không phải ciphertext dữ liệu và không thể đem làm DEK trực tiếp. Nó là blob bảo vệ **key material**.
- KEK được bọc bằng một tầng KEK khác (hierarchy) hoặc root key của KMS/HSM là mẫu thường gặp, nhưng **cần tránh chu trình phụ thuộc** khiến không có khóa gốc khả dụng để phục hồi.
- AES-KW chuẩn có **kiểm tra tính toàn vẹn** của key data khi unwrap; nó không tự gắn đầy đủ thông tin *tenant, object, algorithm, usage policy, key ID* trừ khi protocol thiết kế cách binding. Không thay thế xác thực metadata, quyền truy cập, logging hoặc trust model.
- RFC 3394 AES-KW yêu cầu đầu vào key data là ít nhất hai block 64 bit và là bội số 64 bit. AES-128 DEK dài 16 byte thỏa mãn, thường sinh wrapped blob 24 byte. Khi cần wrap dữ liệu key kích thước bất kỳ, chọn primitive phù hợp như AES-KWP, không tự padding tùy tiện.
- KEK có thể **không xuất được** plaintext từ HSM/KMS. Khi đó Java `Key.getEncoded()` có thể trả `null` và code dựa trên byte export của KEK sẽ không chạy; dùng key handle/provider integration được hỗ trợ, thay vì cố trích khóa.
- Một KEK quá rộng (dùng cho mọi tenant, mọi ứng dụng) tạo blast radius lớn. Phân vùng KEK theo chính sách và key hierarchy có thể giúp giới hạn tác động, nhưng cũng tăng số metadata/permissions phải quản lý.

Không gọi `Cipher.getInstance("AES")` với defaults provider không xác định để “tự bọc” key; dùng primitive wrapping có kiểm tra tính toàn vẹn rõ ràng và được hệ thống KMS/phương thức chuẩn hỗ trợ.

## 4. Hiểu signing key cho đúng

Một cặp **khóa ký bất đối xứng** gồm:

- **Private signing key:** chỉ signer đã được cấp quyền `sign` sử dụng. Nên lưu trong KeyStore/HSM/KMS hỗ trợ thuật toán và chính sách phù hợp. Nếu bị lộ, bên tấn công có thể tạo chữ ký mạo danh trong phạm vi trust của key.
- **Public verification key:** dùng `verify`, có thể phân phối rộng nhưng phải gắn với danh tính/key ID đáng tin qua certificate chain/trust store, key pinning hoặc phân phối cấu hình có kiểm soát.

Java:

```java
Signature signer = Signature.getInstance("RSASSA-PSS");
signer.initSign(privateSigningKey);
signer.setParameter(pssProfile);
signer.update(bytesToSign);
byte[] signature = signer.sign();
```

Đây là **snippet**, giả định `privateSigningKey`, `pssProfile` và `bytesToSign` đã được tạo; các import và xử lý exception cần theo application context. Một lựa chọn khác là `Signature.getInstance("Ed25519")` khi các hệ thống và chính sách liên quan hỗ trợ; không tự đổi algorithm giữa signer và verifier.

**Chọn đúng dữ liệu được ký:** nếu hệ thống cần chứng minh một phiên bản object cụ thể bao gồm cả metadata, nên định nghĩa **bản ghi canonical** chứa version, algorithm IDs, key IDs, nonce/AAD, wrapped DEK, ciphertext và ký **toàn bộ chuỗi byte canonical**. Nếu chỉ ký mỗi ciphertext nhưng bỏ qua các trường điều khiển, attacker có thể sửa metadata mà không làm đổi chữ ký. Cần quy định độ dài/encoding từng trường để tránh nhập nhằng: `"ab"+"c"` và `"a"+"bc"` cho cùng chuỗi byte nếu nối mù quáng.

**Chữ ký và AES-GCM tag khác nhau:** GCM tag xác nhận người giải mã nắm DEK nhận đúng ciphertext/AAD, nhưng không chứng minh “ai là người gửi” nếu nhiều actor cùng có DEK; chữ ký công khai gắn với private signing key và được verify bởi bên giữ public key tin cậy. Nếu dữ liệu chỉ cần bảo mật và chống sửa đổi ở kho nội bộ, AES-GCM với quyền truy cập chặt có thể đủ; không phải mọi object đều cần chữ ký. Cần quyết định theo trust boundary, không theo cảm giác “thêm thuật toán luôn tốt”.

**Signing key không nên dùng làm KEK.** RSA private key là một kiểu `PrivateKey` nên developer có thể nhầm “có RSA thì ký và giải mã đều được”. Việc dùng một cặp key cho ký và key transport khiến quyền, cryptoperiod và hậu quả compromise trộn lẫn. Dùng cặp key, thuật toán, certificate KeyUsage và chính sách riêng theo mục đích.

## 5. So sánh quyền, vòng đời và mức độ ảnh hưởng

| Khía cạnh | DEK | KEK | Signing private key |
| --- | --- | --- | --- |
| Principal sử dụng | Workload encrypt/decrypt đúng object | Dịch vụ wrapping/unwrapping được ủy quyền | Signer được ủy quyền |
| Tác vụ được phép | `encrypt`, `decrypt` payload | `wrapKey`, `unwrapKey`; có thể hạn chế theo tenant/app | `sign`; public counterpart dùng `verify` |
| Phạm vi điển hình | Object/field/segment/tenant | Nhóm DEK hoặc boundary của KMS | Danh tính ứng dụng/tổ chức và chính sách ký |
| Nơi lưu lâu dài | **Wrapped DEK**, không plaintext cạnh dữ liệu | KMS/HSM/KeyStore bảo vệ, key handle non-exportable nếu phù hợp | HSM/KMS/KeyStore bảo vệ; public key/cert có thể phân phối |
| Nếu bị lộ | Dữ liệu trong phạm vi DEK có thể bị giải mã; cần DEK mới/reencrypt | Nhiều wrapped DEK có thể bị lộ; có thể cần rekey/reencrypt hàng loạt tùy tác động | Có thể giả mạo chữ ký của chủ thể; thu hồi trust, thay key, điều tra các bản ghi đã ký |
| Khi rotation thông thường | Thay DEK rồi **reencrypt data** | Thay KEK và **rewrap DEK** (không nhất thiết reencrypt payload) | Thay signing key, cập nhật public key/certificate/trust và chính sách kiểm chứng |
| Khi cần archive/read lịch sử | Giữ đường phục hồi DEK theo retention | Giữ bản KEK cũ có giới hạn cho wrapped DEK chưa di trú | Giữ verify public key/certificate và lịch sử trust để xác minh signature cũ |

**Không nên coi bảng “rotation thông thường” là quy trình xử lý compromise.** Ví dụ nếu plaintext DEK đã bị lộ, chỉ thay KEK không thu hồi quyền đọc của kẻ đã có DEK; phải đánh giá **thay DEK và mã hóa lại payload**. Nếu KEK đã bị lộ, attacker có thể đã giải bọc các DEK trong quá khứ; rewrap bằng KEK mới **không xóa được bản DEK mà attacker đã lấy**. Cần đánh giá phạm vi dữ liệu, key versions và bước reencrypt/đáp ứng sự cố.

### Key ID, phiên bản và phạm vi

Các tên như `dekId`, `kekId`, `signingKeyId` là **metadata định tuyến**, không phải bí mật và không đại diện cho quyền truy cập. Một server không được cấp quyền unwrap chỉ vì client gửi đúng `kekId`. Mỗi thao tác phải được kiểm tra danh tính actor, tenant/object scope, key state (active/decrypt-only/retired), usage policy và audit.

Khi xoay vòng một KEK, có thể có `kek-v1` và `kek-v2` cùng tồn tại trong giai đoạn chuyển đổi; **key ID phải trỏ chính xác version** phù hợp với wrapped DEK. Khi signing key thay, verifier cũ có thể vẫn cần public key cũ để xác minh những signature hợp lệ đã tạo trước đó, theo chính sách retention và sự cố bảo mật.

## 6. Envelope encryption: ba vai trò phối hợp như thế nào?

Một sơ đồ một object:

```text
                 ┌─ DEK ngẫu nhiên ────────────────────┐
                 │                                      │
  plaintext ───> AES-GCM.encrypt(DEK, nonce, AAD)       │
                 │                   │                  │
                 v                   v                  v
         ciphertext+tag         nonce/AAD         AESWrap(KEK, DEK)
                                                      │
                                                      v
                                                  wrappedDEK
                 │                   │                  │
                 └──────────┬────────┴──────────────────┘
                            v
               canonical envelope bytes
          (version, algorithms, key IDs,
           nonce, AAD, wrappedDEK, ciphertext)
                            |
          Sign(privateSigningKey, envelope)
                            |
                            v
       Lưu: envelope + signature + signer key reference

Bên nhận:
  - kiểm tra quyền truy cập + signer public-key trust
  - verify signature trên EXACT envelope bytes theo policy
  - chọn KEK theo server-side authorization, unwrap DEK
  - AES-GCM.decrypt(DEK, nonce, AAD, ciphertext+tag)
  - chỉ công bố plaintext sau khi tag xác minh thành công
```

Các bước cụ thể:

1. **Tạo DEK** bằng CSPRNG/`KeyGenerator` phù hợp; quyết định scope của DEK (một object hay khác).
2. **Mã hóa payload** bằng AEAD như AES-GCM với nonce unique cho cặp (DEK, nonce), AAD có context ổn định cần xác thực (chẳng hạn object/tenant/version).
3. **Bọc DEK** bằng KEK có quyền wrap; lưu `wrappedDEK`, `kekId` và `wrapAlgorithm`.
4. **Tạo envelope có định dạng byte chính tắc** với version, algorithm IDs, identifiers, nonce, AAD, wrapped key và ciphertext. Không dựa vào phép nối string có ranh giới mơ hồ.
5. **Ký envelope** nếu bài toán cần xác thực nguồn ký. Bên ký cần private signing key; signature được lưu kèm signer key ID và thông tin tin cậy cần thiết.
6. **Khi đọc**, kiểm tra authorization và signature **trên đúng bytes đã ký** rồi mới giải bọc DEK theo KEK đã được server ủy quyền. Sau đó giải mã data, kiểm tra GCM tag rồi mới đưa plaintext vào hệ thống.
7. **Ghi log có chọn lọc:** actor, key IDs, operation, object reference, timestamp và kết quả. Không log plaintext, raw DEK, KEK, signing private key hoặc wrapped key blob không cần thiết.

**Lưu ý quan trọng với rewrap:** nếu bạn đưa `kekId` hoặc `wrappedDEK` vào **AAD của AES-GCM payload**, việc thay KEK/wrappedDEK sẽ đổi AAD và làm tag cũ không hợp lệ. Khi cần rewrap **mà không reencrypt data**, thiết kế AAD payload chỉ chứa metadata **bất biến qua rewrap** (ví dụ tenant, object, content version), còn các trường wrapping có thể được xác thực bằng **chữ ký/hệ thống metadata có bảo vệ khác**. Vì signature ở ví dụ bao phủ wrapping fields, sau rewrap cần **tạo signature manifest mới có ủy quyền**; đừng sửa metadata signed mà vẫn giữ signature cũ.

### Ví dụ bản ghi lưu lâu dài

```json
{
  "formatVersion": 1,
  "objectId": "doc-42",
  "contentVersion": 3,
  "dataAlgorithm": "AES/GCM/NoPadding",
  "nonce": "<base64url>",
  "aadContext": "tenant-7|doc-42|v3",
  "ciphertextAndTag": "<base64url>",
  "wrappedDek": "<base64url>",
  "kekId": "tenant-7-kek-v2",
  "wrapAlgorithm": "AESWrap",
  "signatureAlgorithm": "RSASSA-PSS",
  "signingKeyId": "signer-v4",
  "signature": "<base64url>"
}
```

Các giá trị trong dấu `<...>` là **ký hiệu ví dụ**, không phải một credential có thật. Bản ghi này chỉ trình bày **các trường**; trước khi ký phải quy định **canonical byte serialization**, quy tắc length-prefix/canonical JSON, version và thứ tự, không ký một JSON object mơ hồ rồi mong việc serialize lần sau giữ nguyên bytes. Nếu dùng nhiều môi trường, lưu rõ PSS digest/MGF1/saltLen/trailer hoặc dùng một profile được protocol xác định cứng (PS256).

Một signature được lưu trong record **không tự xác minh chính nó**: phải có public key tin cậy độc lập với input không tin cậy và không được chấp nhận tùy tiện algorithm/key ID do attacker chọn.

## 7. Ví dụ Java 17+ đầy đủ: DEK + KEK + signing key

Ví dụ sau minh họa đồng thời **ba vai trò** trong một tiến trình:

- Hai khóa AES 128 bit **được sinh độc lập**: `dek` cho AES-GCM data, `kek` cho AES Key Wrap.
- Một cặp RSA 2048 bit độc lập cho chữ ký RSASSA-PSS SHA-256, MGF1-SHA256, salt 32 byte.
- `pack(...)` dùng **length-prefix 4 byte big-endian** trên từng trường để giảm nguy cơ nhập nhằng input signature. Bản ghi đã ký bao gồm algorithm labels, key IDs, nonce, AAD, wrapped DEK và ciphertext.
- Cả khôi phục DEK, giải mã data và kiểm chứng signature đều được thực hiện. Sửa byte của bản ghi đã ký phải khiến verify trả false.

Lưu file **`KeyRolesDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class KeyRolesDemo {
    private KeyRolesDemo() {}

    private static byte[] pack(byte[]... parts) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            for (byte[] part : parts) {
                out.writeInt(part.length);
                out.write(part);
            }
        }
        return bytes.toByteArray();
    }

    private static boolean verify(PublicKey key, PSSParameterSpec spec,
            byte[] message, byte[] signature) throws Exception {
        Signature verifier = Signature.getInstance("RSASSA-PSS");
        verifier.initVerify(key);
        verifier.setParameter(spec);
        verifier.update(message);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator keys = KeyGenerator.getInstance("AES");
        keys.init(128);
        SecretKey dek = keys.generateKey();
        SecretKey kek = keys.generateKey();

        byte[] payload = "secret document".getBytes(StandardCharsets.UTF_8);
        byte[] aad = "tenant=42;purpose=report".getBytes(StandardCharsets.UTF_8);
        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);

        Cipher dataEncrypt = Cipher.getInstance("AES/GCM/NoPadding");
        dataEncrypt.init(Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(128, nonce));
        dataEncrypt.updateAAD(aad);
        byte[] sealed = dataEncrypt.doFinal(payload);

        Cipher keyWrap = Cipher.getInstance("AESWrap");
        keyWrap.init(Cipher.WRAP_MODE, kek);
        byte[] wrappedDek = keyWrap.wrap(dek);

        Cipher keyUnwrap = Cipher.getInstance("AESWrap");
        keyUnwrap.init(Cipher.UNWRAP_MODE, kek);
        SecretKey restoredDek = (SecretKey) keyUnwrap.unwrap(
                wrappedDek, "AES", Cipher.SECRET_KEY);

        Cipher dataDecrypt = Cipher.getInstance("AES/GCM/NoPadding");
        dataDecrypt.init(Cipher.DECRYPT_MODE, restoredDek,
                new GCMParameterSpec(128, nonce));
        dataDecrypt.updateAAD(aad);
        byte[] restored = dataDecrypt.doFinal(sealed);

        KeyPairGenerator signingKeys = KeyPairGenerator.getInstance("RSA");
        signingKeys.initialize(2048);
        KeyPair signingPair = signingKeys.generateKeyPair();

        PSSParameterSpec pss = new PSSParameterSpec(
                "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
                32, PSSParameterSpec.TRAILER_FIELD_BC);

        byte[] record = pack(
                "AES/GCM/NoPadding".getBytes(StandardCharsets.US_ASCII),
                "AESWrap".getBytes(StandardCharsets.US_ASCII),
                "kek-v1".getBytes(StandardCharsets.US_ASCII),
                "sign-v1".getBytes(StandardCharsets.US_ASCII),
                nonce, aad, wrappedDek, sealed);

        Signature signer = Signature.getInstance("RSASSA-PSS");
        signer.initSign(signingPair.getPrivate());
        signer.setParameter(pss);
        signer.update(record);
        byte[] signature = signer.sign();

        byte[] modified = record.clone();
        modified[modified.length - 1] ^= 1;

        System.out.println("dekBytes=" + dek.getEncoded().length);
        System.out.println("kekBytes=" + kek.getEncoded().length);
        System.out.println("wrappedDekBytes=" + wrappedDek.length);
        System.out.println("ciphertextBytes=" + sealed.length);
        System.out.println("keyRecovered=" +
                Arrays.equals(dek.getEncoded(), restoredDek.getEncoded()));
        System.out.println("dataRecovered=" + Arrays.equals(payload, restored));
        System.out.println("signatureBytes=" + signature.length);
        System.out.println("signatureValid=" +
                verify(signingPair.getPublic(), pss, record, signature));
        System.out.println("modifiedRecordAccepted=" +
                verify(signingPair.getPublic(), pss, modified, signature));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 KeyRolesDemo.java
java KeyRolesDemo
```

**Stdout đã kiểm tra với JDK hỗ trợ các thuật toán nêu trên:**

```text
dekBytes=16
kekBytes=16
wrappedDekBytes=24
ciphertextBytes=31
keyRecovered=true
dataRecovered=true
signatureBytes=256
signatureValid=true
modifiedRecordAccepted=false
```

Kích thước giải thích được: `"secret document"` có 15 byte UTF-8/ASCII; AES-GCM với tag 128 bit tạo **15 + 16 = 31 byte** ciphertext+tag. Wrapped AES-128 DEK có 16 byte key material, AES-KW theo RFC 3394 thêm 8 byte overhead thành **24 byte**. RSA-2048 signature dài **256 byte**. Nội dung bí mật/khóa/nonce và signature bytes **thay đổi giữa các lần chạy**, nhưng các giá trị boolean/length nêu trong stdout ổn định trong provider tương thích.

### Phân tích theo ranh giới trách nhiệm

1. `KeyGenerator` sinh **hai AES keys độc lập**. Dù thuộc cùng interface `SecretKey`, `dek` chỉ đi qua data cipher và `kek` chỉ đi qua wrapping cipher. Java object type `SecretKey` **không tự thực thi lệnh cấm sử dụng sai mục đích**; đây mới là quy ước trong code. Production cần IAM/KMS/HSM policy và phân quyền.
2. `dataEncrypt` sử dụng **DEK**, nonce 12 byte và AAD. `doFinal` sinh ciphertext+tag. Kết quả không bao gồm plaintext DEK.
3. `keyWrap` sử dụng **KEK** ở `WRAP_MODE`, input là `dek`, output là wrapped key blob. `keyUnwrap` dùng cùng KEK ở `UNWRAP_MODE` và dựng lại `SecretKey` AES. Nó không cần biết plaintext của tài liệu.
4. `dataDecrypt` sử dụng **DEK vừa được giải bọc**, cùng nonce và AAD. Chỉ sau khi GCM tag được kiểm chứng mới chấp nhận `restored`.
5. `signingPair` là cặp key RSA **không liên quan** đến DEK/KEK. Private key ký bytes của envelope; public key verify. Code không dùng RSA để wrap AES key và không dùng AES key để giả lập chữ ký số.
6. `pack` mã hóa ranh giới fields bằng tiền tố `int`. Đây là minh họa cho input byte xác định; version/header, trường tin cậy và giới hạn kích thước khi parse vẫn cần được bổ sung trong protocol production.
7. `modifiedRecordAccepted=false` chứng minh sửa byte cuối bản ghi đã ký không phù hợp với signature gốc. **Verify bằng public key được truyền từ attacker là vô nghĩa về danh tính**; demo giữ public key trong cùng tiến trình chỉ để chứng minh cách gọi API.
8. Vì khóa AES trong demo có thể xuất bằng `getEncoded()`, việc so sánh raw bytes hoạt động. Với HSM-backed nonexportable keys, `getEncoded()` có thể là `null`; hãy dùng operation qua key handle, không ép export key để làm test.

Trong code minh họa, bên giải mã đã có `kek` và private signing key chỉ nằm ở signer. Khi phân tách thành nhiều service, **không chuyển private signing key sang verifier** và **không cấp KEK plaintext cho service chỉ cần verify signature**.

## 8. Thay KEK không nhất thiết phải mã hóa lại dữ liệu

**Rewrap** là thao tác thay lớp bảo vệ của DEK. Nếu DEK còn an toàn và ciphertext không đổi, có thể unwrap DEK bằng KEK cũ, wrap lại DEK bằng KEK mới, rồi **ghi atomically** metadata `wrappedDek`/`kekId` mới.

```text
Before:
 ciphertext = AES-GCM(DEK, plaintext, nonce, AAD)
 wrappedDekV1 = AESWrap(KEK-v1, DEK)

Rewrap:
 DEK = AESUnwrap(KEK-v1, wrappedDekV1)
 wrappedDekV2 = AESWrap(KEK-v2, DEK)

After:
 ciphertext giữ nguyên
 nonce + AAD của payload giữ nguyên
 wrappedDekV2 + kekId=v2 thay thế wrappedDekV1
```

Chỉ làm vậy khi AAD của payload **không bị đổi bởi KEK metadata**; nếu metadata thay đổi nằm trong AAD, cần điều chỉnh thiết kế hoặc thực hiện quy trình reencrypt phù hợp. Nếu toàn envelope được **ký**, thao tác rewrap thay `kekId`/`wrappedDek` cũng làm bytes đã ký thay đổi: phải tạo attestation/chữ ký mới có ủy quyền, không giữ signature cũ như thể không có gì đổi.

### Ví dụ Java độc lập về rewrap

Lưu **`RewrapOnlyDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class RewrapOnlyDemo {
    private RewrapOnlyDemo() {}

    private static SecretKey newAesKey() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        return generator.generateKey();
    }

    private static byte[] wrap(SecretKey kek, SecretKey dek)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AESWrap");
        cipher.init(Cipher.WRAP_MODE, kek);
        return cipher.wrap(dek);
    }

    private static SecretKey unwrap(SecretKey kek, byte[] wrapped)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AESWrap");
        cipher.init(Cipher.UNWRAP_MODE, kek);
        return (SecretKey) cipher.unwrap(wrapped, "AES", Cipher.SECRET_KEY);
    }

    public static void main(String[] args) throws Exception {
        SecretKey dek = newAesKey();
        SecretKey oldKek = newAesKey();
        SecretKey newKek = newAesKey();

        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);
        byte[] message = "stored record".getBytes(StandardCharsets.UTF_8);

        Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
        encrypt.init(Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(128, nonce));
        byte[] ciphertext = encrypt.doFinal(message);

        byte[] oldWrapped = wrap(oldKek, dek);
        SecretKey recoveredDek = unwrap(oldKek, oldWrapped);
        byte[] newWrapped = wrap(newKek, recoveredDek);

        SecretKey afterRotation = unwrap(newKek, newWrapped);
        Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
        decrypt.init(Cipher.DECRYPT_MODE, afterRotation,
                new GCMParameterSpec(128, nonce));
        byte[] restored = decrypt.doFinal(ciphertext);

        System.out.println("oldWrappedBytes=" + oldWrapped.length);
        System.out.println("newWrappedBytes=" + newWrapped.length);
        System.out.println("sameDataKey=" +
                Arrays.equals(dek.getEncoded(), afterRotation.getEncoded()));
        System.out.println("payloadUnchanged=" +
                Arrays.equals(message, restored));
        System.out.println("ciphertextBytes=" + ciphertext.length);
    }
}
```

```bash
javac -encoding UTF-8 RewrapOnlyDemo.java
java RewrapOnlyDemo
```

Stdout:

```text
oldWrappedBytes=24
newWrappedBytes=24
sameDataKey=true
payloadUnchanged=true
ciphertextBytes=29
```

`"stored record"` có 13 byte UTF-8 và tag GCM 16 byte, vì vậy ciphertext 29 byte. `sameDataKey=true` chứng minh DEK **không đổi** sau giải bọc/bọc lại, và `payloadUnchanged=true` cho thấy **cùng ciphertext cũ** có thể được decrypt bằng DEK đã khôi phục qua KEK mới.

Ví dụ không có database, signer, transaction hoặc kiểm tra quyền; nó chỉ minh họa nguyên lý rewrap. Trong production, bước commit phải nhất quán: `newWrappedDek` và `newKekId` cần cập nhật **cùng một giao dịch/phiên bản**, kiểm chứng unwrap thành công và bảo đảm rollback không làm mất khả năng đọc. Đừng xóa KEK cũ khi vẫn còn object trỏ tới phiên bản đó.

### So sánh ba quy trình rotation

| Khi thay đổi | Việc tối thiểu cần làm | Cái gì **không** được hiểu nhầm |
| --- | --- | --- |
| **KEK rotation thông thường** | Rewrap từng DEK còn phải lưu, cập nhật key ID/metadata atomically, kiểm tra đọc lại | Không nhất thiết phải đổi DEK hoặc reencrypt payload. |
| **DEK rotation** | Sinh DEK mới, **decrypt bằng DEK cũ** và **encrypt payload bằng DEK mới với nonce phù hợp**, wrap DEK mới | Chỉ đổi wrappedDEK không đổi DEK thực tế. |
| **Signing key rotation** | Key pair mới, phân phối public verification key/cert mới, cập nhật signer key ID và trust policy | Không thể chỉ “rewrap private signing key” rồi coi signer identity/validity đã chuyển. |
| **KEK bị compromise** | Đánh giá DEK nào có thể đã bị giải bọc; có thể cần DEK mới/reencrypt, thu hồi quyền và điều tra | Rewrap sau sự cố không làm attacker quên DEK cũ. |
| **Signing key bị compromise** | Thu hồi/đình chỉ quyền ký, công bố/truyền chính sách trust mới, đánh giá các chữ ký đã phát hành | Thay key không tự biến những chữ ký giả mạo trước đó thành không thể tồn tại. |

Không áp dụng “xóa khóa cũ ngay lập tức” như một quy tắc. Mỗi key có thể cần giai đoạn **active → decrypt/unwrap/verify only → retired → destroyed** theo retention, legal hold, key compromise và backup/restore requirements. Với chữ ký lưu trữ lâu dài, phải giữ đủ public verification material và bằng chứng về trạng thái tin cậy tại thời điểm ký nếu protocol yêu cầu.

## 9. Quyền truy cập và vị trí lưu khóa

Việc gắn nhãn “DEK”, “KEK”, “signing key” trong code là chưa đủ. Cần xây **permission boundary** sao cho actor chỉ thực hiện đúng chức năng.

| Actor/service | DEK usage | KEK usage | Signing private key | Signing public key |
| --- | --- | --- | --- | --- |
| Data writer | Encrypt dữ liệu được cấp phép | Xin wrap DEK (thông qua KMS/HSM nếu áp dụng) | Chỉ sign nếu được ủy quyền riêng | Verify metadata khi cần |
| Data reader | Decrypt object có quyền đọc | Xin unwrap DEK qua policy phù hợp | Không cần | Verify envelope khi cần |
| Key management service | Điều phối generate/wrap/unwrap/rotation, không cần đọc payload | Quản trị KEK theo policy | Không mặc nhiên | Có thể quản trị trust anchors |
| Signing service | Không cần plaintext DEK | Không cần KEK | Có quyền `sign` với key thuộc phạm vi được ủy quyền | Có thể kiểm chứng |
| Public verifier | Không cần | Không cần | **Không bao giờ** | Có, nhưng phải xác thực nguồn public key |

**Các điều kiện production nên có:**

- **Policy theo key purpose:** chỉ được phép encrypt/decrypt, wrap/unwrap hoặc sign/verify đúng key. KMS/HSM/API có thể áp dụng `KeyUsage`/operations; phải kiểm tra tài liệu provider, không suy diễn từ tên object Java.
- **Key identity và version:** mỗi key có ID ổn định, key version, algorithm, size, scope/tenant, trạng thái và quy tắc sử dụng. Không dùng user-supplied key ID làm authorization.
- **Key generation:** dùng RNG an toàn và quản lý keys bằng hệ thống phù hợp; không hard-code key trong code, image/container, Git, secret logs hoặc spreadsheet.
- **Không export khi không cần:** tránh truyền KEK và signing private key ra nhiều service; cân nhắc handle trong HSM/KMS. DEK nếu phải xuất cho application thì giới hạn lifetime/caching và quyền truy cập.
- **Audit & incident response:** ghi `who/what/which key/which object/when`, kết quả unwrap/sign/rotation, nhưng không ghi raw key, plaintext hoặc private material. Giám sát bất thường (vọt số lần unwrap, signer signing ngoài giờ/tenant).
- **Backup/recovery:** backup ciphertext mà **không có khả năng khôi phục DEK/KEK** có thể khiến dữ liệu không thể giải mã. Thiết kế khôi phục key có kiểm soát, không tạo bản plaintext backup trôi nổi.
- **Separation of duties:** người quản lý key policy không đương nhiên được đọc toàn bộ data, người có quyền đọc data không mặc nhiên được ký thay tổ chức, signer không tự động được unwrap mọi tenant.

### Java types không tương đương key policy

- `javax.crypto.SecretKey` đại diện khóa bí mật, có thể dùng cho DEK hoặc KEK. Chỉ dựa vào type không bảo đảm **đúng purpose**.
- `java.security.PrivateKey`/`PublicKey` là cặp khóa bất đối xứng, nhưng RSA private key không tự xác định quyền **chỉ được ký** nếu backend không kiểm tra policy.
- `java.security.KeyStore` có cơ chế lưu/truy xuất key và certificate (tùy loại/provider), **không thay thế** toàn bộ IAM, key lifecycle, KMS audit và separation of duties.
- `Key.getEncoded()` có thể trả `null` nếu key không thể xuất/opaque. Code phải xử lý các provider HSM/PKCS#11 mà không giả định có raw key bytes.
- Metadata X.509 `KeyUsage` có thể phân biệt `digitalSignature`, `keyEncipherment`, `keyAgreement`; nó có giá trị khi xử lý chứng chỉ, nhưng enforcement phụ thuộc verifier/protocol/policy. Không chỉ nhìn thấy certificate là coi key tự động đúng mục đích.

## 10. Đe dọa và sự cố: phản ứng theo loại khóa

### Nếu DEK của một object bị lộ

Cần đánh giá **đối tượng và phiên bản dữ liệu** liên quan đã có thể bị đọc. Nếu vẫn dùng DEK đó, phải sinh DEK khác, reencrypt dữ liệu với nonce mới, wrap DEK mới, cập nhật metadata/signature tương ứng và thu hồi quyền đọc nếu cần. Không giả định việc xóa bản key khỏi database sẽ xóa những bản đã bị sao chép.

### Nếu KEK dùng cho nhiều object bị lộ

Một KEK bị lộ có thể cho phép giải bọc **nhiều DEK** từ những bản ghi đã thu thập. Thay KEK chỉ bảo vệ các wrapped DEK **từ nay về sau**; không thể đảm bảo các DEK trước đó chưa bị đối phương thu thập. Đánh giá toàn bộ các object/version từng dùng KEK, khả năng cần reencrypt với DEK mới, thời gian lưu backup, lịch sử quyền truy cập và phạm vi thông báo sự cố. Ưu tiên có **key inventory** để truy ra đối tượng bị ảnh hưởng mà không phải quét mò.

### Nếu signing private key bị lộ

Đối phương có thể tạo một chữ ký mới phù hợp với public key mà verifier đang tin cậy. Cần thu hồi/ngưng key, cập nhật key registry/cert/trust policy, kiểm soát signer mới và rà soát các artefact đã ký. **AES-GCM ciphertext vẫn giữ bí mật nếu DEK/KEK không lộ**, nhưng giả mạo metadata/chữ ký có thể làm trust boundary bị xâm phạm. Thông tin thời điểm ký, transparency log hoặc timestamp authority (nếu có) có thể quan trọng khi đánh giá chữ ký lịch sử.

### Nếu bị thay metadata/key IDs

Không cho phép chuyển `wrappedDek` từ tenant A sang tenant B chỉ bằng sửa `kekId`. Dùng authorization phía server và bảo vệ/binding context (AAD bất biến, signature hoặc MAC phù hợp). Khi phục hồi từ backup hoặc migrate dữ liệu, nhất quán giữa `kekId`, `wrappedDek`, `dataAlgorithm`, `nonce`, `AAD` và ciphertext là điều kiện cần.

**Nguyên tắc:** cùng một crypto primitive có thể xử lý nhiều loại key về mặt thuật toán, nhưng **không loại bỏ** nhu cầu phân quyền và tách biệt trách nhiệm ở hệ thống quản lý khóa.

## 11. Những lỗi thường gặp và cách sửa

| Sai lầm | Rủi ro | Cách sửa |
| --- | --- | --- |
| Dùng cùng một AES key cho cả encrypt data và wrap key | Trộn mục đích, khó giới hạn blast radius và quyền sử dụng | Sinh DEK/KEK riêng; policy/handle riêng. |
| Lưu plaintext DEK cùng ciphertext | Ai lấy được database có thể giải mã ngay | Lưu wrapped DEK dưới KEK/KMS có policy. |
| Dùng signer private key để vận chuyển/bọc DEK | Vi phạm separation of use và ràng buộc certificate/protocol | Dùng KEK/key transport key riêng. |
| Coi signature như mã hóa | Data vẫn có thể đọc bằng plaintext | Encrypt bằng DEK; sign khi cần xác thực người ký. |
| Coi GCM tag như chữ ký nguồn gửi | Các actor cùng có DEK đều có thể tạo ciphertext/tag hợp lệ | Dùng signature nếu cần identity provenance. |
| Gửi public key trong record rồi tin verify=true | Attacker tự tạo key/signature của mình | Xác thực public key theo trust store/certificate/pinning. |
| Cho client chọn `kekId` rồi unwrap không kiểm tra | Vượt tenant hoặc ACL, tạo oracle | Authorize actor/tenant/object/key usage ở phía server. |
| Quên binding nonce, wrapped DEK, algorithm IDs khi ký metadata | Metadata có thể bị thay không nằm trong signature coverage | Canonical envelope và ký đủ các trường security-critical. |
| Dùng AES-GCM mà lặp (DEK, nonce) | Nguy cơ phá bảo mật | Nonce unique cho mỗi encryption với cùng DEK. |
| Rewrap KEK mà giữ nguyên signature trên wrapped key cũ | Signature không khớp với envelope mới | Re-sign version mới có ủy quyền, giữ audit chain. |
| Đặt `kekId` thay đổi được trong AAD payload rồi cố rewrap không reencrypt | AEAD tag không hợp lệ sau khi AAD thay đổi | Thiết kế AAD ổn định hoặc reencrypt đúng quy trình. |
| Đổi KEK sau khi đã lộ DEK rồi tuyên bố an toàn | Attacker vẫn giữ DEK cũ | Đánh giá phạm vi và rotate DEK/reencrypt nếu cần. |
| Xóa KEK cũ trước khi di trú hết wrapped DEK | Mất khả năng giải mã dữ liệu lịch sử | Inventory, migration checkpoint, rollback và retention. |
| Đưa raw key/private material vào logs | Lộ secrets qua observability | Log key ID, operation, status thay vì key material. |
| Cho rằng `SecretKey` Java tự enforcing “data-only” | Object Java không phải security policy đầy đủ | Dùng IAM/KMS/HSM usage restrictions và giới hạn service. |
| Giả định mọi khóa đều `getEncoded()!=null` | Lỗi với nonexportable HSM keys | Dùng provider-bound `Key` handles và cryptographic operations hỗ trợ. |
| Dùng `AESWrap` cho dữ liệu tùy ý/mọi độ dài | RFC 3394 có điều kiện input key data và purpose cụ thể | Chọn AES-KWP hoặc AEAD thích hợp theo chuẩn. |

## 12. Bài tập áp dụng

1. **Phân loại:** hệ thống quản lý 10.000 tài liệu có một KEK trong KMS và 10.000 DEK bọc. Một signing private key dùng tạo attestation của manifest. Hãy chỉ ra actor nào nên giữ quyền `encrypt/decrypt`, `wrap/unwrap`, `sign` và `verify`.
2. **Đọc code:** trong `KeyRolesDemo`, tại sao `dekBytes=16` và `kekBytes=16` không chứng minh hai khóa có cùng trách nhiệm? Tại sao `wrappedDekBytes=24` khác `ciphertextBytes=31`?
3. **Sửa code:** đổi một byte trong `record` đã ký và quan sát `modifiedRecordAccepted=false`. Nếu lấy public key mới do attacker tự tạo, vì sao verify=true với signature attacker không xác thực người gửi thật?
4. **Thực hành rewrap:** chạy `RewrapOnlyDemo` và giải thích tại sao ciphertext/AAD/nonce không cần sửa để giải mã qua KEK mới; nếu ký toàn envelope, bước nào bắt buộc bổ sung?
5. **Thiết kế metadata:** liệt kê trường phải lưu để giải mã một object sau 3 năm khi KEK đã rotate nhiều lần. Trường nào là secret? Trường nào phải được xác thực/binding?
6. **Compromise:** giả sử chỉ KEK bị lộ và attacker đã tải bản sao mọi wrapped DEK. So sánh tác dụng của (A) rewrap cùng DEK và (B) tạo DEK mới + reencrypt từng object.
7. **Sai policy:** một service chỉ cần verify chữ ký nhưng đang được cấp `UNWRAP_MODE` với KEK. Hãy điều chỉnh IAM/KeyStore/KMS policy để thu hẹp quyền.
8. **AAD và rewrap:** vì sao thiết kế dùng `kekId` trong AES-GCM AAD sẽ làm rewrap khó hơn? Đề xuất một tập metadata bất biến để đưa vào AAD và tập metadata wrapping nằm trong signature.
9. **Multi-tenant:** một API nhận `tenantId` và `kekId` từ request. Đề xuất ba bước xác thực/ủy quyền chống việc tenant A trỏ sang KEK của tenant B.
10. **Audit và retention:** signing key cũ chỉ còn verify-only nhưng DEK cũ vẫn phải decrypt dữ liệu lưu trữ. Thiết kế trạng thái key và quy trình thu hồi khác nhau cho signing public/private pair so với KEK.
11. **Cơ chế khác:** giải thích khi nào một hệ thống chỉ dùng AES-GCM với DEK/KEK mà không cần signing key, và khi nào cần chữ ký số để xác minh nguồn phát hành được tin cậy qua nhiều bên.

**Tiêu chí đạt:** giải thích chính xác ba vai trò; mô tả được cách DEK, KEK và signing private/public key đi qua envelope; chứng minh bằng ví dụ rằng thay KEK có thể không đổi ciphertext; biết rằng KEK compromise có thể kéo theo DEK compromise; và mô tả được enforcement, metadata, nonce, trust và rotation hợp lý theo từng loại.

## Tài liệu tham khảo

- [NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final)
- [NIST SP 800-38F — Methods for Key Wrapping](https://csrc.nist.gov/pubs/sp/800/38/f/final)
- [RFC 3394 — Advanced Encryption Standard (AES) Key Wrap Algorithm](https://www.rfc-editor.org/rfc/rfc3394)
- [RFC 5649 — AES Key Wrap with Padding](https://www.rfc-editor.org/rfc/rfc5649)
- [Java 17 Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html)
- [Java 17 `Cipher` — `WRAP_MODE`/`UNWRAP_MODE`, `wrap`/`unwrap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html)
- [Java 17 `Signature` — `initSign`/`initVerify`/`sign`/`verify`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html)
- [Java 17 `Key` — `getEncoded` có thể trả `null`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Key.html)
- [Java 17 `KeyStore` — quản lý key và certificate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html)
