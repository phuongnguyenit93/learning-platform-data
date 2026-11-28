# Quản lý khóa, provider và tính tương thích

Từ Java SE 26, ứng dụng có thể dùng Hybrid Public Key Encryption (HPKE) qua Java Cryptography Architecture (JCA). API cung cấp Cipher có tên thuật toán chuẩn HPKE và HPKEParameterSpec để cấu hình bộ ba KEM, KDF, AEAD cùng các tham số của chế độ HPKE. Đây là API chính thức trong JDK 26, không phải preview hoặc incubator.

HPKE theo RFC 9180 kết hợp ba thành phần: Key Encapsulation Mechanism (KEM) để thiết lập bí mật dùng chung, Key Derivation Function (KDF) để dẫn xuất khóa, và Authenticated Encryption with Associated Data (AEAD) để mã hóa thông điệp. Việc gọi API đúng chỉ là một phần của triển khai. Ứng dụng còn phải quản lý khóa riêng, phân phối khóa công khai, chọn provider hỗ trợ đúng suite, đóng gói dữ liệu truyền nhận và kiểm soát vòng đời encryption context.

## 1. API HPKE trong JDK 26

Hai thành phần chính:

- `Cipher.getInstance("HPKE")`: lấy implementation HPKE từ provider JCA. HPKE không dùng transformation dạng `algorithm/mode/padding`; truyền đúng tên đơn `"HPKE"`.
- `HPKEParameterSpec`: cấu hình các mã định danh KEM, KDF, AEAD theo RFC 9180; thêm `info`, PSK, khóa xác thực hoặc encapsulation message.

Sender khởi tạo `Cipher` ở chế độ `ENCRYPT_MODE` bằng **public key của recipient**. Recipient khởi tạo `Cipher` ở chế độ `DECRYPT_MODE` bằng **private key của chính recipient**. Cả hai phía phải dùng cùng bộ mã định danh và cùng các tham số ứng dụng liên quan.

Ví dụ trao đổi một thông điệp bằng X25519, HKDF-SHA256 và AES-128-GCM:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.HPKEParameterSpec;

public class HpkeRoundTrip {
    public static void main(String[] args) throws Exception {
        // Recipient tạo cặp khóa dài hạn; private key phải được bảo vệ.
        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        KeyPair recipientKeys = generator.generateKeyPair();

        byte[] info = "orders-api/v1".getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "Order A-1042".getBytes(StandardCharsets.UTF_8);

        HPKEParameterSpec senderParameters = HPKEParameterSpec.of(
                HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
                HPKEParameterSpec.KDF_HKDF_SHA256,
                HPKEParameterSpec.AEAD_AES_128_GCM)
                .withInfo(info);

        Cipher sender = Cipher.getInstance("HPKE");
        sender.init(Cipher.ENCRYPT_MODE, recipientKeys.getPublic(),
                senderParameters);

        // Đây là KEM encapsulation message (enc), không phải IV AEAD
        // thông thường dù API trả nó qua getIV().
        byte[] encapsulation = sender.getIV();
        byte[] ciphertext = sender.doFinal(plaintext);

        HPKEParameterSpec recipientParameters = HPKEParameterSpec.of(
                HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
                HPKEParameterSpec.KDF_HKDF_SHA256,
                HPKEParameterSpec.AEAD_AES_128_GCM)
                .withInfo(info)
                .withEncapsulation(encapsulation);

        Cipher recipient = Cipher.getInstance("HPKE");
        recipient.init(Cipher.DECRYPT_MODE, recipientKeys.getPrivate(),
                recipientParameters);

        byte[] recovered = recipient.doFinal(ciphertext);
        if (!Arrays.equals(plaintext, recovered)) {
            throw new IllegalStateException("HPKE round-trip failed");
        }
    }
}
```

Ví dụ minh họa luồng API. Trong ứng dụng thực tế, recipient tạo và lưu cặp khóa theo vòng đời quản lý khóa; sender chỉ nhận public key đã được xác thực qua kênh tin cậy. Không tạo cặp khóa recipient mới cho từng request nếu giao thức của ứng dụng yêu cầu một danh tính recipient ổn định.

## 2. Bộ mã định danh KEM, KDF và AEAD

`HPKEParameterSpec.of(kem_id, kdf_id, aead_id)` nhận các mã số theo RFC 9180 và trả về cấu hình ở `mode_base` với `info` rỗng. JDK 26 cung cấp các hằng số chuẩn:

| Thành phần | Hằng số trong JDK 26 | Ý nghĩa |
|---|---|---|
| KEM | `KEM_DHKEM_P_256_HKDF_SHA256` | DHKEM với P-256 và HKDF-SHA256 |
| KEM | `KEM_DHKEM_P_384_HKDF_SHA384` | DHKEM với P-384 và HKDF-SHA384 |
| KEM | `KEM_DHKEM_P_521_HKDF_SHA512` | DHKEM với P-521 và HKDF-SHA512 |
| KEM | `KEM_DHKEM_X25519_HKDF_SHA256` | DHKEM với X25519 và HKDF-SHA256 |
| KEM | `KEM_DHKEM_X448_HKDF_SHA512` | DHKEM với X448 và HKDF-SHA512 |
| KDF | `KDF_HKDF_SHA256`, `KDF_HKDF_SHA384`, `KDF_HKDF_SHA512` | Dẫn xuất khóa bằng HKDF tương ứng |
| AEAD | `AEAD_AES_128_GCM`, `AEAD_AES_256_GCM` | Mã hóa xác thực AES-GCM |
| AEAD | `AEAD_CHACHA20_POLY1305` | Mã hóa xác thực ChaCha20-Poly1305 |
| AEAD | `EXPORT_ONLY` | Chế độ chỉ xuất bí mật; không dùng như AEAD để mã hóa payload |

Hai bên phải thống nhất chính xác cả ba mã định danh. Không chỉ chọn KEM giống nhau rồi giả định KDF hoặc AEAD có thể tự thương lượng. Giao thức ứng dụng cần xác định suite được phép, phiên bản giao thức và cách hai bên biết suite nào đã được dùng.

Trong Oracle JDK 26, tài liệu release notes công bố hỗ trợ các mã định danh KEM, KDF và AEAD được định nghĩa trong RFC 9180. Tuy nhiên, hợp đồng của `HPKEParameterSpec` nói rõ một implementation HPKE khác có thể chỉ hỗ trợ một phần hoặc không hỗ trợ một số mã định danh; provider cũng có thể bổ sung mã riêng. Vì vậy, khi chuyển sang JDK vendor khác, provider khác hoặc HSM, phải kiểm tra suite thực tế.

HPKE RFC 9180 sử dụng các DHKEM dựa trên đường cong elliptic/XDH. Không được suy luận rằng việc JDK có ML-KEM đồng nghĩa HPKE RFC 9180 đang dùng ML-KEM hoặc đã trở thành post-quantum HPKE. Nếu yêu cầu bảo mật hậu lượng tử, cần một thiết kế và chuẩn HPKE/KEM được hỗ trợ rõ ràng; không tự thay mã KEM trong cấu hình RFC 9180.

## 3. Quản lý khóa recipient

Trong mô hình HPKE phổ biến, recipient có một cặp khóa bất đối xứng:

- **Public key** được phân phối cho sender để họ có thể mã hóa dữ liệu gửi đến recipient.
- **Private key** chỉ được giữ ở phía recipient để giải mã.

Public key không cần giữ bí mật, nhưng cần xác thực tính toàn vẹn và danh tính của chủ sở hữu. Nếu sender nhận nhầm public key do bị thay thế, dữ liệu có thể được mã hóa cho kẻ tấn công. HPKE không tự cung cấp một PKI, directory hay quy trình xác minh chứng thư; ứng dụng phải xác thực public key bằng certificate, pinning, directory tin cậy hoặc cơ chế quản trị khóa tương đương.

Private key cần được bảo vệ bằng keystore, secret-management system hoặc HSM theo yêu cầu vận hành. Không ghi private key, PSK, shared secret hoặc nội dung bí mật vào log. Hạn chế quyền đọc khóa theo service identity và tách quyền quản trị khóa khỏi quyền truy cập dữ liệu thông thường.

Ví dụ tạo khóa X25519 trong môi trường kiểm thử:

```java
KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
KeyPair recipientKeyPair = generator.generateKeyPair();

byte[] publicKeyEncoding = recipientKeyPair.getPublic().getEncoded();
// Lưu private key vào KeyStore/HSM theo chính sách của hệ thống.
// Chỉ phân phối public key sau khi gắn với danh tính và key ID tin cậy.
```

Đoạn mã trên chỉ tạo khóa trong bộ nhớ. Ứng dụng production cần quy định rõ:

1. Ai được phép tạo, kích hoạt, thay thế và thu hồi khóa.
2. Khóa nào được dùng để mã hóa dữ liệu mới.
3. Khóa cũ nào vẫn phải được giữ để giải mã ciphertext đã lưu.
4. Cách gắn `recipientKeyId` vào envelope để chọn đúng private key khi giải mã.
5. Thời hạn lưu trữ, backup, khôi phục và xóa khóa.

Khi xoay khóa, không ghi đè private key cũ nếu vẫn còn ciphertext cần giải mã. Dùng key ID và trạng thái vòng đời để sender chọn public key hiện hành, còn recipient có thể tra cứu khóa cũ trong thời gian lưu trữ được quy định.

## 4. Provider JCA và khả năng tương thích

HPKE là dịch vụ JCA dựa trên provider. API `Cipher` và `HPKEParameterSpec` chuẩn hóa cách gọi; provider chịu trách nhiệm thực thi thuật toán và quyết định loại key/suite nào được chấp nhận.

Tài liệu Oracle JDK 26 và JDK 27 liệt kê `HPKE` trong dịch vụ `Cipher` của SunJCE. SunJCE cũng liệt kê KDF `HKDF-SHA256`, `HKDF-SHA384`, `HKDF-SHA512` và KEM `DHKEM`; tài liệu provider ghi DHKEM chấp nhận EC keys trên `secp256r1`, `secp384r1`, `secp521r1` và XDH keys trên Curve25519/Curve448.

Không nên hard-code tên provider cho ứng dụng thông thường:

```java
// Ưu tiên để JCA chọn implementation phù hợp.
Cipher hpke = Cipher.getInstance("HPKE");
```

Việc gọi `Cipher.getInstance("HPKE")` thành công chỉ chứng minh runtime tìm được một provider đăng ký dịch vụ này. Nó chưa chứng minh provider hỗ trợ key type và bộ tham số mà ứng dụng sẽ dùng. Provider có thể bị từ chối ở bước `init()` nếu key hoặc suite không được hỗ trợ.

Có thể kiểm tra các provider đăng ký dịch vụ `Cipher.HPKE`:

```java
import java.security.Provider;
import java.security.Security;

Provider[] providers = Security.getProviders("Cipher.HPKE");
if (providers == null || providers.length == 0) {
    throw new IllegalStateException("No HPKE Cipher provider is installed");
}

for (Provider provider : providers) {
    System.out.printf("HPKE provider: %s %s%n",
            provider.getName(), provider.getVersionStr());
}
```

Sau khi `Cipher.init()` thành công, ghi nhận `cipher.getProvider()` trong diagnostics để biết provider thực sự được chọn. JCA có thể trì hoãn chọn provider đến lúc khởi tạo vì key object có thể chỉ được một số provider chấp nhận.

## 5. Kiểm tra provider với đúng key và suite

Một phép kiểm tra tương thích nên thực hiện trên đúng JDK, provider, loại khóa, KEM/KDF/AEAD và chế độ sẽ dùng trong production. Không chỉ kiểm tra `Security.getProviders()` rồi kết luận mọi cấu hình HPKE đều hoạt động.

Ví dụ kiểm tra một suite X25519:

```java
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import javax.crypto.Cipher;
import javax.crypto.spec.HPKEParameterSpec;

static String probeHpkeX25519() throws GeneralSecurityException {
    KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
    KeyPair recipientKeys = generator.generateKeyPair();

    HPKEParameterSpec parameters = HPKEParameterSpec.of(
            HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
            HPKEParameterSpec.KDF_HKDF_SHA256,
            HPKEParameterSpec.AEAD_AES_128_GCM);

    Cipher cipher = Cipher.getInstance("HPKE");
    cipher.init(Cipher.ENCRYPT_MODE, recipientKeys.getPublic(), parameters);
    return cipher.getProvider().getName();
}
```

Trong quá trình kiểm thử, phân biệt các lỗi:

| Lỗi | Nguyên nhân có thể gặp | Hướng xử lý |
|---|---|---|
| `NoSuchAlgorithmException` | Không có provider đăng ký `Cipher.HPKE` | Chọn runtime/provider có hỗ trợ hoặc bổ sung provider đã được kiểm định |
| `InvalidKeyException` | Không có implementation chấp nhận loại key hoặc key không hợp lệ | Kiểm tra KEM, key algorithm, curve và provider |
| `InvalidAlgorithmParameterException` | Suite hoặc tham số HPKE không được implementation chấp nhận | Kiểm tra KEM/KDF/AEAD, mode, `info`, PSK, auth key và encapsulation |
| `InvalidKeyException` ở khóa HSM | Provider HPKE không dùng được key token/non-extractable | Xác nhận provider HPKE có hỗ trợ key đó; không xuất private key khỏi HSM để né lỗi |

Kiểm tra phải bao gồm cả mã hóa và giải mã, không chỉ khởi tạo sender. Một provider có thể chấp nhận sender key nhưng recipient key hoặc tham số encapsulation không phù hợp.

## 6. HSM, PKCS#11 và môi trường FIPS

Trong môi trường dùng HSM hoặc smart card, private key có thể là key object không thể export. Provider SunPKCS11 kết nối JCA với thư viện PKCS#11 của thiết bị; tuy nhiên, việc thiết bị hỗ trợ các primitive như ECDH, AES-GCM hoặc HKDF không tự chứng minh nó cung cấp dịch vụ `Cipher.HPKE`.

Trước khi chọn HSM/provider:

- Xác nhận provider có đăng ký `Cipher.HPKE`.
- Xác nhận HPKE implementation có thể dùng trực tiếp loại key token đang có.
- Kiểm tra đúng KEM, KDF, AEAD và mode được thiết bị/provider hỗ trợ.
- Chạy round-trip và interoperability test với key không exportable trong môi trường gần production.
- Xác nhận key rotation, backup, recovery và quyền truy cập HSM.

Với yêu cầu FIPS hoặc chứng nhận tuân thủ, kiểm tra phạm vi chứng nhận của cryptographic module, provider, thuật toán tổ hợp và cấu hình vận hành. Không suy luận HPKE đã được phê duyệt chỉ vì một thành phần như AES-GCM hoặc SHA-256 có trong provider được chứng nhận. Cần xác nhận chính xác dịch vụ HPKE và cấu hình suite có nằm trong phạm vi được chấp thuận hay không.

## 7. Bốn chế độ HPKE và quản lý khóa xác thực

`HPKEParameterSpec.of(...)` mặc định tạo cấu hình `mode_base`. Có thể bổ sung tham số để sử dụng các mode khác:

| Mode | Tham số bổ sung | Ý nghĩa xác thực |
|---|---|---|
| `mode_base` | Không có PSK hoặc sender authentication key | Mã hóa tới public key recipient; không xác thực danh tính sender |
| `mode_psk` | `withPsk(psk, psk_id)` ở cả hai bên | Recipient xác nhận sender biết PSK tương ứng |
| `mode_auth` | `withAuthKey(...)` | Recipient xác nhận sender sở hữu private key xác thực tương ứng |
| `mode_auth_psk` | Cả `withAuthKey(...)` và `withPsk(...)` | Kết hợp xác thực bằng asymmetric key và PSK |

Đối với `mode_auth`, sender gọi `withAuthKey()` bằng private key của chính sender; recipient gọi bằng public key của sender. Đối với PSK mode, hai bên phải có cùng PSK và `psk_id`. PSK và `psk_id` phải được cung cấp cùng nhau theo quy tắc RFC 9180.

Ví dụ xây dựng cấu hình auth mode:

```java
HPKEParameterSpec senderAuth = HPKEParameterSpec.of(
        HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
        HPKEParameterSpec.KDF_HKDF_SHA256,
        HPKEParameterSpec.AEAD_AES_128_GCM)
        .withInfo(info)
        .withAuthKey(senderPrivateKey);

HPKEParameterSpec recipientAuth = HPKEParameterSpec.of(
        HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
        HPKEParameterSpec.KDF_HKDF_SHA256,
        HPKEParameterSpec.AEAD_AES_128_GCM)
        .withInfo(info)
        .withEncapsulation(encapsulation)
        .withAuthKey(senderPublicKey);
```

Không nhầm `mode_base` với xác thực hai chiều. Trong base mode, bất kỳ ai có recipient public key đều có thể tạo ciphertext hợp lệ cho recipient; dữ liệu được bảo vệ bí mật và toàn vẹn, nhưng recipient không biết ai là sender. Auth mode xác thực việc sở hữu sender private key ở cấp mật mã; ứng dụng vẫn phải ánh xạ sender public key sang danh tính tin cậy.

Với các DHKEM trong RFC 9180, bảo đảm sender authentication có giới hạn liên quan đến key-compromise impersonation (KCI) như RFC mô tả. Không xem Auth mode là chứng thư danh tính hoặc cơ chế thay thế việc xác minh khóa sender và chính sách tin cậy của ứng dụng.

PSK cần được sinh ngẫu nhiên với entropy đủ mạnh và lưu trong secret manager hoặc HSM phù hợp. Không dùng mật khẩu người dùng trực tiếp làm PSK; nếu nghiệp vụ bắt buộc bắt đầu từ password, phải có thiết kế password-based key derivation và chính sách riêng, không đưa password thô vào `withPsk()`.

## 8. Tham số info, AAD và ngữ cảnh ứng dụng

`info` là dữ liệu ứng dụng đưa vào key schedule để ràng buộc ngữ cảnh sử dụng khóa. Sender và recipient phải cung cấp cùng byte sequence. Có thể dùng một chuỗi context ổn định chứa protocol name, version, tenant hoặc loại thông điệp:

```java
byte[] info = "billing-api/v2|invoice-envelope".getBytes(StandardCharsets.UTF_8);
HPKEParameterSpec parameters = HPKEParameterSpec.of(
        HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
        HPKEParameterSpec.KDF_HKDF_SHA256,
        HPKEParameterSpec.AEAD_AES_128_GCM)
        .withInfo(info);
```

Không đặt secret vào `info`; đây không phải nơi lưu mật khẩu hay khóa. `info` cũng không thay thế sender authentication, authorization hoặc xác minh public key.

`Cipher.updateAAD(byte[])` có thể dùng để xác thực metadata ngoài plaintext, ví dụ content type, message ID hoặc phiên bản envelope. AAD không được mã hóa, nhưng thay đổi AAD sẽ làm xác thực ciphertext thất bại. Hai bên phải truyền chính xác cùng dữ liệu AAD và gọi `updateAAD()` trước dữ liệu plaintext/ciphertext.

Không dùng AAD hoặc `info` như một cơ chế chống replay tự động. Nếu ứng dụng cần chống replay, phải có message ID/sequence number, trạng thái đã xử lý và chính sách từ chối thông điệp trùng ở tầng giao thức.

## 9. Đóng gói dữ liệu truyền nhận

HPKE API không tự định nghĩa envelope của ứng dụng. Sender cần gửi ít nhất:

- `recipientKeyId`: định danh public key recipient để bên nhận chọn private key tương ứng.
- `suiteId` hoặc cấu hình suite đã được giao thức xác định.
- `encapsulation`: bytes lấy từ `senderCipher.getIV()` sau khi khởi tạo.
- `ciphertext`: kết quả `senderCipher.doFinal(...)`.
- Metadata cần thiết như protocol version, message ID hoặc content type.

`getIV()` có tên giống API IV thông thường, nhưng trong HPKE nó trả về KEM encapsulation message (`enc`) để recipient tái tạo shared secret. Không xử lý bytes này như nonce AES-GCM và không tự thay thế bằng IV do ứng dụng tạo.

Recipient tra cứu private key theo `recipientKeyId`, kiểm tra suite thuộc allowlist của giao thức, tạo `HPKEParameterSpec` cùng `info`, AAD và `withEncapsulation(encapsulation)`, rồi giải mã ciphertext. Không tin suite ID tùy ý từ message nếu nó cho phép attacker ép hai bên chuyển xuống thuật toán yếu hơn; chính sách suite cần được cấu hình và kiểm soát bởi ứng dụng.

Ví dụ cấu trúc envelope ở mức khái niệm:

```text
Envelope {
  version,
  recipientKeyId,
  suiteId,
  encapsulation,
  messageId,
  ciphertext
}
```

Các trường trên cần được serialize bằng định dạng có framing rõ ràng và giới hạn kích thước. Khi metadata phải được bảo vệ, đưa biểu diễn canonical của nó vào AAD hoặc xác thực bằng cơ chế giao thức phù hợp. Tránh nối chuỗi không có delimiter hoặc serialize cùng một object theo hai cách khác nhau ở hai bên.

## 10. Vòng đời Cipher và sequence counter

HPKE khác cách dùng một AEAD cipher thông thường. Sau khi khởi tạo, mỗi lần `doFinal()` hoàn thành một thông điệp HPKE và sử dụng nonce riêng được dẫn xuất từ sequence counter nội bộ. Có thể gọi `doFinal()` nhiều lần trên cùng encryption context.

Recipient phải xử lý đúng một ciphertext hoàn chỉnh cho mỗi lần `doFinal()`. Số lượng và thứ tự lời gọi phía nhận phải khớp với phía gửi. Điều này có nghĩa:

- Nếu gửi nhiều message trong cùng context, phải bảo đảm transport giữ thứ tự và không bỏ mất message.
- Không dùng một `Cipher` context chung cho các luồng xử lý đồng thời nếu không có cơ chế tuần tự hóa phù hợp.
- Nếu thông điệp được lưu trữ, phân phối độc lập hoặc có thể đến không đúng thứ tự, cân nhắc tạo context riêng cho từng message hoặc định nghĩa framing/sequence rõ ràng ở tầng ứng dụng.
- Khi context bị mất trạng thái, không thể tùy tiện khởi tạo lại recipient rồi tiếp tục giải mã các ciphertext tiếp theo của sender context cũ.

Ví dụ thêm AAD và thực hiện một message:

```java
byte[] aad = "invoice|tenant-42|message-1001"
        .getBytes(StandardCharsets.UTF_8);

sender.updateAAD(aad);
byte[] ciphertext = sender.doFinal(plaintext);

recipient.updateAAD(aad);
byte[] plaintextAgain = recipient.doFinal(ciphertext);
```

Đối với nhiều message, mỗi lần gọi `doFinal()` tương ứng một ciphertext độc lập trong cùng context và AAD của message đó cần được cung cấp ở cả hai phía trước dữ liệu của message. Quản lý sequence, số lượng message và lỗi giải mã là một phần của protocol state.

## 11. Các giới hạn bảo mật cần xử lý ở tầng ứng dụng

HPKE cung cấp cơ chế mã hóa và xác thực ciphertext theo suite đã chọn, nhưng RFC 9180 không thay thế toàn bộ giao thức truyền thông:

- **Không tự phân phối khóa:** ứng dụng phải xác thực public key recipient và quản lý danh tính/key ID.
- **Base mode không xác thực sender:** dùng Auth, PSK hoặc AuthPSK nếu nghiệp vụ cần xác thực nguồn gửi.
- **Không tự chống replay:** message ID, sequence tracking và chính sách chống phát lại phải do ứng dụng thiết kế.
- **Không tự xử lý reorder/loss:** context nhiều message phụ thuộc đúng thứ tự; cần framing và transport phù hợp.
- **Không che độ dài plaintext:** nếu độ dài là dữ liệu nhạy cảm, ứng dụng phải padding hoặc áp dụng biện pháp riêng theo giao thức.
- **Không cung cấp forward secrecy đối với việc lộ recipient private key:** attacker lưu ciphertext có thể giải mã chúng nếu sau này chiếm được private key recipient tương ứng. Quản lý vòng đời khóa và rủi ro lưu trữ cần tính đến điều này.
- **Không ngăn downgrade tự động:** suite allowlist và phiên bản giao thức phải được xác định, xác thực và kiểm soát.

HPKE cũng không thay thế TLS. TLS vẫn bảo vệ kênh truyền, xác thực endpoint và cung cấp các thuộc tính transport. HPKE có thể bổ sung mã hóa ở tầng message khi cần bảo vệ payload qua nhiều hop hoặc lưu ciphertext ở hệ thống trung gian.

## 12. Ma trận kiểm thử khóa và provider

Trước khi đưa HPKE vào production, nên có integration test cho từng cặp runtime/provider/key:

| Nhóm kiểm thử | Nội dung |
|---|---|
| Provider discovery | `Cipher.HPKE` có provider đăng ký; ghi nhận provider được chọn |
| KEM/key compatibility | X25519, X448 hoặc EC curve được cấu hình thực sự hoạt động |
| KDF/AEAD suite | Từng suite trong allowlist khởi tạo và round-trip thành công |
| Mode | Base, PSK, Auth và AuthPSK được kiểm thử theo nhu cầu |
| Interoperability | Sender/recipient trên hai runtime hoặc provider khác nhau giải mã được cùng envelope |
| Key lifecycle | Key ID, rotation, revoke, decrypt ciphertext cũ và phục hồi backup |
| Authentication | Sai sender key, PSK, `psk_id`, `info` hoặc AAD phải thất bại theo kỳ vọng |
| Message context | Nhiều `doFinal()`, sai thứ tự, thiếu message, duplicate và context reset |
| HSM/FIPS | Non-extractable key, provider thực thi HPKE và phạm vi chứng nhận |
| Failure handling | NoSuchAlgorithmException, InvalidKeyException, InvalidAlgorithmParameterException và AEAD tag failure |

Không chỉ test với hai Cipher trong cùng JVM và cùng provider. Để xác nhận tương thích thực tế, cần test phiên bản JDK, provider, key encoding và envelope mà các hệ thống độc lập sẽ dùng. Lưu test vector công khai của RFC 9180 nếu triển khai cần tương thích với thư viện HPKE ngoài Java.

## 13. Trạng thái API và điều kiện nâng cấp

| Thành phần | Trạng thái trong Java SE 26 |
|---|---|
| `Cipher` thuật toán `HPKE` | API JCA chính thức |
| `HPKEParameterSpec` | API chính thức, `Since: 26`; vẫn có trong Java SE 27 |
| KEM/KDF/AEAD identifiers theo RFC 9180 | Hằng số trong `HPKEParameterSpec`; khả năng thực thi phụ thuộc provider |
| SunJCE HPKE | Được Oracle JDK 26 và 27 liệt kê trong dịch vụ Cipher |
| Provider ngoài JDK/HSM | Phải kiểm tra dịch vụ, key type, suite và mode cụ thể |

Khi biên dịch bằng JDK 26 trở lên, API HPKE có sẵn mà không cần `--enable-preview`. Khi chạy trên JDK 25 hoặc thấp hơn, `HPKEParameterSpec` không có trong Java SE API của runtime đó; ứng dụng phải nâng runtime hoặc dùng thư viện/provider tương thích được kiểm định. Không tự sao chép API JDK 26 vào ứng dụng để giả lập hỗ trợ.

## 14. Những điểm cần nhớ

- HPKE trong Java SE 26 dùng `Cipher.getInstance("HPKE")` và `HPKEParameterSpec`; không dùng transformation dạng `HPKE/AES/GCM`.
- Sender dùng recipient public key ở `ENCRYPT_MODE`; recipient dùng private key tương ứng ở `DECRYPT_MODE`.
- `Cipher.getIV()` trả KEM encapsulation message cho recipient, không phải IV AES-GCM thông thường.
- Hai bên phải thống nhất KEM, KDF, AEAD, `info`, PSK/PSK ID và khóa xác thực nếu mode yêu cầu.
- SunJCE trong Oracle JDK 26 có HPKE, HKDF và DHKEM; provider khác có thể hỗ trợ một phần hoặc không hỗ trợ suite đang cần.
- Chỉ kiểm tra provider discovery là chưa đủ; phải `init()` bằng đúng key và `HPKEParameterSpec`, sau đó chạy round-trip/interoperability test.
- Private key và PSK phải được quản lý qua keystore, secret manager hoặc HSM; public key phải được xác thực và gắn với key ID.
- Base mode không xác thực sender; chọn Auth/PSK/AuthPSK khi nghiệp vụ yêu cầu.
- HPKE context quản lý sequence counter; mỗi `doFinal()` là một message và phía nhận phải giữ đúng thứ tự.
- HPKE không tự phân phối khóa, chống replay, chống downgrade hoặc thay thế TLS; các yêu cầu đó thuộc thiết kế giao thức ứng dụng.
- HPKE RFC 9180 với DHKEM không đồng nghĩa với post-quantum HPKE; không suy luận ML-KEM đã được tích hợp vào suite này.

## Tài liệu tham khảo

- [Java SE 26 API: HPKEParameterSpec](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/spec/HPKEParameterSpec.html)
- [Java SE 26 JCA Reference Guide: Securely Exchanging Messages with HPKE](https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html)
- [Java SE 26: Oracle JDK Providers — SunJCE and HPKE](https://docs.oracle.com/en/java/javase/26/security/oracle-providers.html)
- [JDK 26 Release Notes: Hybrid Public Key Encryption](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [RFC 9180: Hybrid Public Key Encryption](https://www.rfc-editor.org/rfc/rfc9180.html)
- [Java SE 26 API: Cipher](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/Cipher.html)
- [Java SE 26 API: Provider](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Provider.html)
- [Java SE 26 API: Security](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Security.html)
- [Java SE 27 API: New API List](https://docs.oracle.com/en/java/javase/27/docs/api/new-list.html)
- [Java SE 27: Oracle JDK Providers — SunJCE and HPKE](https://docs.oracle.com/en/java/javase/27/security/oracle-providers.html)
