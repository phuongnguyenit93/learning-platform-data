# X.509 SubjectPublicKeyInfo và PKCS#8 cho khóa EdEC (Java 15+)

## 1. Vì sao khóa EdEC cần định dạng mã hóa?

Java 15 chính thức đưa hỗ trợ **EdDSA** vào JCA với hai biến thể ký số **Ed25519** và **Ed448**. Sau khi gọi `KeyPairGenerator.generateKeyPair()`, chương trình có hai đối tượng:

- **Public key:** dùng để xác minh chữ ký; có thể phân phối khi bên nhận biết cách xác thực nguồn khóa.
- **Private key:** dùng để ký; dữ liệu này phải được bảo vệ và không bao giờ ghi ra log.

Đối tượng Java `PublicKey` hay `PrivateKey` tồn tại trong bộ nhớ, nhưng nhiều ứng dụng cần **trao đổi hoặc khôi phục khóa** qua file, giao thức, thư viện hay hệ thống khác. Hai cấu trúc chuẩn giải quyết nhu cầu đó:

- **X.509 SubjectPublicKeyInfo (SPKI):** cấu trúc ASN.1 dùng để biểu diễn **public key**, có thông tin thuật toán và dữ liệu khóa công khai.
- **PKCS#8:** cấu trúc ASN.1 dùng để biểu diễn **private key**, có thông tin thuật toán và dữ liệu khóa riêng.

Với JCA và khóa EdEC xuất được, `getFormat()` của public key thường là `"X.509"`, private key thường là `"PKCS#8"`. Cả hai thường được `getEncoded()` xuất ra dưới dạng **DER bytes**.

**Trọng tâm:** SPKI/PKCS#8 là định dạng biểu diễn khóa; **Ed25519/Ed448 là thuật toán chữ ký số**. Một dạng encoding không thay thế cho thuật toán và cũng không tự cung cấp tính năng bảo mật cho khóa riêng.

## 2. Phân biệt các tên dễ gây nhầm lẫn

| Khái niệm | Chứa hoặc thực hiện gì? | Có phải khóa EdEC theo dạng có thể nhập bằng KeyFactory? |
| --- | --- | --- |
| Raw Ed25519 public-key bytes | Dữ liệu điểm công khai theo RFC 8032 | **Chưa phải** SPKI DER; thiếu cấu trúc ASN.1 và OID |
| X.509 **SubjectPublicKeyInfo** | AlgorithmIdentifier + public-key BIT STRING | **Có**; dùng `X509EncodedKeySpec` |
| X.509 **certificate** | Chủ thể, issuer, thời hạn, SPKI, extensions, chữ ký certificate... | **Không phải chỉ SPKI**; cần `CertificateFactory` nếu đầu vào là certificate |
| Raw private seed/bytes | Dữ liệu bí mật theo thuật toán | **Chưa phải** PKCS#8 DER |
| **PKCS#8** private key | PrivateKeyInfo/OneAsymmetricKey với thuật toán và private-key data | **Có**; dùng `PKCS8EncodedKeySpec` khi chưa mã hóa |
| **Encrypted** PKCS#8 | Cấu trúc private-key bytes được bảo vệ bởi cơ chế mã hóa | **Không nhập trực tiếp** bằng `PKCS8EncodedKeySpec` trước khi giải mã |
| `KeyPair` | Hai đối tượng `PublicKey` và `PrivateKey` của cùng cặp | Đối tượng Java; không phải một định dạng byte duy nhất |
| PEM | DER được Base64 hóa và bao bởi BEGIN/END markers | Phải tách marker, Base64-decode để có bytes DER |

**SPKI không phải chứng chỉ X.509**: nó không chứa đủ thông tin chứng thực danh tính. Ngay cả khi chữ ký được xác minh bằng public key SPKI, bên nhận còn phải biết khóa đó thuộc về chủ thể đáng tin cậy nào.

**PKCS#8 không đồng nghĩa khóa riêng được mã hóa:** một `PrivateKey.getEncoded()` dạng PKCS#8 có thể cho phép bất kỳ ai có bytes đó khôi phục private key. Base64 hoặc PEM không thay thế cơ chế mã hóa hay HSM/KMS.

## 3. Cấu trúc X.509 SubjectPublicKeyInfo

Theo RFC 8410 và ASN.1 của X.509:

```text
SubjectPublicKeyInfo ::= SEQUENCE {
    algorithm         AlgorithmIdentifier,
    subjectPublicKey  BIT STRING
}
```

- `algorithm` xác định loại khóa bằng OID như Ed25519 hoặc Ed448.
- `subjectPublicKey` chứa public-key data ở dạng byte theo RFC 8032, bên trong `BIT STRING`.

Dữ liệu DER xuất từ public key chứa cả **vỏ ASN.1 và định danh thuật toán**, không chỉ tọa độ hoặc point bytes. Vì vậy, mảng raw key không thể đưa trực tiếp vào `new X509EncodedKeySpec(rawKeyBytes)` nếu chưa có mã hóa SPKI đúng chuẩn.

### 3.1. OID theo RFC 8410

| Thuật toán | OID | Công dụng |
| --- | --- | --- |
| **Ed25519** | `1.3.101.112` | Chữ ký EdDSA |
| **Ed448** | `1.3.101.113` | Chữ ký EdDSA |
| X25519 | `1.3.101.110` | Thỏa thuận khóa XDH |
| X448 | `1.3.101.111` | Thỏa thuận khóa XDH |

**Quy định quan trọng:** trường `parameters` trong `AlgorithmIdentifier` của bốn OID trên **phải vắng mặt**. Đừng tự thêm ASN.1 `NULL` cho Ed25519/Ed448. Quy định này được RFC 8410 nêu rõ và vẫn áp dụng trong hiện tại.

Đặc biệt, **Ed25519 không phải X25519**: một bên ký số, một bên là key agreement. Đổi OID hoặc đổi tên thuật toán trong code không biến đổi bản chất khóa.

## 4. Cấu trúc PKCS#8 cho private key EdEC

PKCS#8 lưu private key **cùng thông tin thuật toán**. Các cấu trúc `PrivateKeyInfo`/ `OneAsymmetricKey` có dạng khái niệm:

```text
PrivateKeyInfo / OneAsymmetricKey ::= SEQUENCE {
    version,
    privateKeyAlgorithm,
    privateKey OCTET STRING,
    ... optional fields
}
```

Với Ed25519/Ed448 theo RFC 8410, `privateKey` chứa một giá trị `CurvePrivateKey ::= OCTET STRING`; tức private-key material được **bọc trong ASN.1 OCTET STRING** của cấu trúc PKCS#8. Raw seed không tự động là một file PKCS#8.

Ví dụ ứng dụng nhận một mảng 32 byte raw Ed25519 seed thì **không** được giả định:

```java
// Sai khi rawSeed chưa phải PKCS#8 DER:
new PKCS8EncodedKeySpec(rawSeed);
```

Nếu thực sự dùng seed/raw material, cần `KeySpec` tương thích với thuật toán và provider hoặc chuyển đổi qua thư viện hiểu đúng RFC 8410. Với khóa đã được JCA sinh và cho phép export, cách đơn giản nhất là lấy PKCS#8 DER trực tiếp từ `privateKey.getEncoded()`.

## 5. API JCA cần dùng

| API | Vai trò |
| --- | --- |
| `KeyPairGenerator.getInstance("Ed25519")` | Sinh public/private key Ed25519 |
| `KeyPairGenerator.getInstance("Ed448")` | Sinh public/private key Ed448 |
| `KeyPair.getPublic()` | Trả `PublicKey` |
| `KeyPair.getPrivate()` | Trả `PrivateKey` |
| `Key.getFormat()` | Tên dạng encoding của khóa, có thể là `null` |
| `Key.getEncoded()` | Bytes encoding của khóa; có thể là `null` nếu provider không cho xuất |
| `X509EncodedKeySpec` | Chứa bytes DER của **public-key SPKI** |
| `PKCS8EncodedKeySpec` | Chứa bytes DER của **private-key PKCS#8 chưa mã hóa** |
| `KeyFactory.getInstance("Ed25519")` | Chọn factory cho thuật toán khóa Ed25519 |
| `KeyFactory.generatePublic(...)` | Tạo `PublicKey` từ KeySpec public |
| `KeyFactory.generatePrivate(...)` | Tạo `PrivateKey` từ KeySpec private |
| `Signature` | Kiểm chứng việc nhập lại khóa bằng ký/xác minh |

Một đoạn code dùng trong **method hoặc test** với các import và xử lý ngoại lệ thích hợp:

```java
KeyPair pair = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();

byte[] spkiDer = pair.getPublic().getEncoded();   // X.509 SPKI
byte[] pkcs8Der = pair.getPrivate().getEncoded(); // PKCS#8

KeyFactory factory = KeyFactory.getInstance("Ed25519");
PublicKey publicKey = factory.generatePublic(
        new X509EncodedKeySpec(spkiDer));
PrivateKey privateKey = factory.generatePrivate(
        new PKCS8EncodedKeySpec(pkcs8Der));
```

**Điểm cần nhớ:** Tên dùng trong `KeyFactory.getInstance(...)` là **tên thuật toán**, ví dụ `"Ed25519"`, không phải `"X.509"` hay `"PKCS#8"`. Hai định dạng được chọn bằng **loại KeySpec**.

Nếu chọn sai loại KeySpec, dùng bytes đã hỏng hoặc thuật toán không khớp, `generatePublic` / `generatePrivate` có thể ném `InvalidKeySpecException`.

## 6. Chương trình Java 17+ hoàn chỉnh: xuất/nhập Ed25519 và Ed448

Ví dụ độc lập sau:

1. Sinh cặp khóa Ed25519 và Ed448 bằng `KeyPairGenerator`.
2. Xuất public key thành **SPKI DER** và private key thành **PKCS#8 DER**.
3. Nhập cả hai qua `KeyFactory`.
4. Dùng private key đã nhập để ký, public key đã nhập để xác minh.
5. Thử xác minh chữ ký với thông điệp đã bị đổi.

Tạo file **`EdECEncodingRoundTripDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;

public class EdECEncodingRoundTripDemo {
    public static void main(String[] args) throws GeneralSecurityException {
        roundTrip("Ed25519");
        roundTrip("Ed448");
    }

    static void roundTrip(String algorithm) throws GeneralSecurityException {
        KeyPair pair = KeyPairGenerator.getInstance(algorithm).generateKeyPair();

        byte[] spkiDer = pair.getPublic().getEncoded();
        byte[] pkcs8Der = pair.getPrivate().getEncoded();
        if (spkiDer == null || pkcs8Der == null) {
            throw new IllegalStateException("Key material is not exportable");
        }

        KeyFactory factory = KeyFactory.getInstance(algorithm);
        PublicKey importedPublic = factory.generatePublic(
                new X509EncodedKeySpec(spkiDer));
        PrivateKey importedPrivate = factory.generatePrivate(
                new PKCS8EncodedKeySpec(pkcs8Der));

        byte[] message = "verify round trip".getBytes(StandardCharsets.UTF_8);
        Signature signer = Signature.getInstance(algorithm);
        signer.initSign(importedPrivate);
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance(algorithm);
        verifier.initVerify(importedPublic);
        verifier.update(message);
        boolean valid = verifier.verify(signature);

        verifier.initVerify(importedPublic);
        verifier.update("modified message".getBytes(StandardCharsets.UTF_8));
        boolean tamperedValid = verifier.verify(signature);

        System.out.println(algorithm
                + " publicFormat=" + pair.getPublic().getFormat()
                + " privateFormat=" + pair.getPrivate().getFormat()
                + " restoredAndValid=" + valid
                + " changedMessageValid=" + tamperedValid);
    }
}
```

Chạy bằng JDK 17 hoặc mới hơn:

```bash
javac --release 17 EdECEncodingRoundTripDemo.java
java EdECEncodingRoundTripDemo
```

**Stdout chính xác** đã kiểm chứng với provider SunEC của JDK 24 khi biên dịch bằng `--release 17`:

```text
Ed25519 publicFormat=X.509 privateFormat=PKCS#8 restoredAndValid=true changedMessageValid=false
Ed448 publicFormat=X.509 privateFormat=PKCS#8 restoredAndValid=true changedMessageValid=false
```

### 6.1. Giải thích kết quả

- `publicFormat=X.509`: public key được mã hóa thành **SubjectPublicKeyInfo DER**.
- `privateFormat=PKCS#8`: private key được mã hóa thành **PKCS#8 DER**.
- `restoredAndValid=true`: khóa đã nhập lại vẫn đúng cặp và tương thích với thuật toán chữ ký.
- `changedMessageValid=false`: dữ liệu thay đổi không thể xác minh bằng chữ ký cũ.
- Mã **không in byte khóa riêng** hoặc chữ ký; mỗi lần sinh key pair sẽ tạo dữ liệu mới, nên không thể mong stdout chứa một private key cố định.

Các tên `getFormat()` và khả năng xuất khóa phụ thuộc provider. Chương trình được kiểm chứng với provider tích hợp tiêu chuẩn; một HSM/KMS có thể không cho export private key và khi đó đoạn kiểm tra `pkcs8Der == null` sẽ chặn round-trip đúng mục đích.

## 7. DER và PEM: đừng đưa text PEM thẳng vào KeySpec

**DER** là encoding nhị phân của ASN.1. **PEM** là dạng văn bản Base64 có các dòng mở/đóng. Dấu nhận diện thường gặp:

| Marker PEM | Đối tượng |
| --- | --- |
| `BEGIN PUBLIC KEY` | SPKI public key, thường dùng được với `X509EncodedKeySpec` sau khi decode |
| `BEGIN PRIVATE KEY` | PKCS#8 private key **chưa mã hóa** |
| `BEGIN ENCRYPTED PRIVATE KEY` | Private key có lớp mã hóa; cần giải mã bằng cơ chế thích hợp trước |
| `BEGIN CERTIFICATE` | Chứng chỉ X.509 đầy đủ, không phải một SPKI riêng |
| `BEGIN OPENSSH PRIVATE KEY` | Định dạng khóa OpenSSH, không mặc nhiên là PKCS#8 |

PEM là **văn bản**, không phải bytes DER. Nếu chương trình đọc một file PEM bằng `Files.readString(...)`, nó phải xác định đúng marker, tách phần Base64, decode ra DER, rồi mới dùng `X509EncodedKeySpec`/`PKCS8EncodedKeySpec` hoặc API parser phù hợp.

Đoạn minh họa tạo PEM cho **public key**, đặt trong method sau khi đã có `spkiDer`:

```java
import java.util.Base64;

// Ví dụ sử dụng trong method, không phải file Java độc lập.
String body = Base64.getMimeEncoder(64, new byte[] {'\n'})
        .encodeToString(spkiDer);

String pem = "-----BEGIN PUBLIC KEY-----\n"
        + body + "\n-----END PUBLIC KEY-----\n";
```

Khi nhập, **không** truyền các byte UTF-8 của toàn bộ `pem` vào `new X509EncodedKeySpec(...)`; cần decode Base64 để trở về **SPKI DER**. Đối với hệ thống có nhiều biến thể PEM/encrypted key, nên dùng parser được duy trì thay vì viết parser thủ công tùy tiện.

### 7.1. PKCS#8 chưa mã hóa không bảo vệ bí mật

Một file PEM `BEGIN PRIVATE KEY` chứa Base64 của PKCS#8 DER **không có nghĩa dữ liệu riêng được mã hóa**. Bất kỳ người nào đọc được file có thể khôi phục khóa nếu định dạng và thuật toán được hỗ trợ.

Không nên lưu private key ở source code, log, screenshot, telemetry hoặc tài liệu kiểm thử thật. Sử dụng keystore/vault/KMS/HSM theo chính sách; nếu private key không xuất được từ HSM, hãy dùng nó trực tiếp qua provider để ký thay vì cố xuất PKCS#8.

## 8. Raw key không phải SPKI/PKCS#8

Hai dạng nhầm lẫn thường gặp:

**Nhầm lẫn 1 — public key Ed25519 32 byte:**

Theo RFC 8032, public key Ed25519 có biểu diễn raw dài 32 byte, còn Ed448 là 57 byte. Nhưng **SPKI DER dài hơn**, do có AlgorithmIdentifier, ASN.1 SEQUENCE và BIT STRING. Nếu một API nói trả về “32-byte public key”, không kết luận bytes đó đã là X.509 SPKI.

**Nhầm lẫn 2 — private seed là PKCS#8:**

Raw seed/private-key bytes là **nội dung bí mật của thuật toán**; PKCS#8 là cấu trúc mang dữ liệu đó kèm AlgorithmIdentifier và các trường chuẩn. Truyền raw seed vào `PKCS8EncodedKeySpec` không làm nó tự được bọc đúng ASN.1.

Không tự đoán loại khóa dựa trên `encoded.length`, không thêm/xóa vài byte prefix để vượt lỗi `InvalidKeySpecException`. Nếu phải giao tiếp với raw-key API, hãy dùng `KeySpec`/library hỗ trợ định dạng raw một cách tường minh, đồng thời kiểm tra đúng curve và chính sách bảo mật.

## 9. Khóa có thể không export: `getEncoded() == null`

Trong Java, `Key.getEncoded()` được phép trả `null` nếu khóa không hỗ trợ dạng encoding. Trường hợp thường gặp là khóa được quản lý bởi thiết bị bảo mật hoặc provider có chính sách **non-extractable**.

Đối với private key như vậy:

- Không coi `null` là “đường cong lỗi” hoặc “private key rỗng”.
- Không in, không serialize đối tượng key bằng `toString()` để tìm raw bytes.
- Dùng `Signature.initSign(privateKey)` thông qua provider hỗ trợ thay vì cố xuất PKCS#8.
- Public key có thể được xuất riêng theo khả năng của provider để bên kia xác minh chữ ký.

Mọi ví dụ dùng `getEncoded()` cần **kiểm tra null** nếu làm việc với nhiều provider. Bài demo đã dừng rõ ràng trước khi tạo `EncodedKeySpec` nếu không thể export.

## 10. Nhập khóa qua KeyFactory: các lỗi cần phân loại

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `NoSuchAlgorithmException` với `KeyFactory.getInstance("Ed448")` | Provider không hỗ trợ thuật toán | Kiểm tra JDK và danh sách provider, dùng provider hợp lệ |
| `InvalidKeySpecException` khi `generatePublic` | Bytes không phải SPKI DER, sai OID hoặc cấu trúc bị hỏng | Xác nhận đầu vào là SPKI, không phải PEM text/certificate/raw point |
| `InvalidKeySpecException` khi `generatePrivate` | Bytes không phải PKCS#8 DER chưa mã hóa, sai curve hoặc cấu trúc | Kiểm tra PKCS#8/EncryptedPrivateKeyInfo/OpenSSH/raw key |
| `getEncoded() == null` | Khóa không cho xuất hoặc không có encoding | Tôn trọng provider policy, dùng key trực tiếp |
| `Signature.initSign` / `initVerify` lỗi khóa | Không đúng thuật toán/curve hoặc provider không chấp nhận key | Xác nhận Ed25519/Ed448 và key type |
| `Signature.verify(signature) == false` | Thông điệp, chữ ký hoặc public key không tương ứng | So sánh đúng message bytes và bảo đảm public key được tin cậy |
| Nhập SPKI thành công nhưng tưởng có danh tính chứng chỉ | SPKI không có subject/issuer/chain | Cần certificate/registry/pinning được xác thực riêng |

**Ví dụ sai** (chỉ là minh họa API):

```java
KeyFactory.getInstance("X.509"); // "X.509" là format, không phải thuật toán
```

**Ví dụ đúng** (đặt bên trong method với biến `spkiDer` và xử lý ngoại lệ):

```java
KeyFactory factory = KeyFactory.getInstance("Ed25519");
PublicKey publicKey = factory.generatePublic(new X509EncodedKeySpec(spkiDer));
```

`KeyFactory` có thể hỗ trợ tên chung `"EdDSA"` tùy provider, nhưng cách dùng `"Ed25519"` hoặc `"Ed448"` phù hợp hơn khi bạn đã xác định rõ curve.

## 11. Bảo mật và khả năng tương thích khi trao đổi khóa

Khi đưa SPKI/PKCS#8 vào ứng dụng thực tế:

1. **Biết loại dữ liệu trước khi parse.** Một chứng chỉ X.509 và một SPKI riêng đều có ASN.1, nhưng parser/mục đích khác nhau.
2. **Tôn trọng OID.** Ed25519 `1.3.101.112`, Ed448 `1.3.101.113`; theo RFC 8410, AlgorithmIdentifier phải không có parameters.
3. **Không trộn EdDSA với XDH.** Ed25519/Ed448 dùng cho chữ ký; X25519/X448 dùng cho thỏa thuận khóa.
4. **Bảo vệ private material.** PKCS#8 export được là dữ liệu nhạy cảm. Base64 không mã hóa; keystore, HSM hoặc vault cần chính sách bảo vệ thích hợp.
5. **Chỉ tin public key từ nguồn được xác thực.** Chữ ký đúng với một public key không tự chứng minh danh tính bên ký.
6. **Kiểm tra bytes trước khi xây KeySpec.** DER, PEM, raw point/seed và encrypted PKCS#8 không được xử lý như cùng một dạng.
7. **Kiểm tra provider ở môi trường chạy.** Một số JDK có Ed25519 nhưng Ed448 hoặc export policy có thể khác. Tránh dựa vào chi tiết implementation nội bộ.
8. **Dùng API chuẩn.** `getEncoded()`, `KeyFactory`, `X509EncodedKeySpec` và `PKCS8EncodedKeySpec` giúp tránh phải tự thao tác ASN.1/OID thủ công.

Một key pair có thể ký/xác minh chính xác sau round-trip nhưng vẫn **không an toàn** nếu private key đã bị lộ, private bytes được lưu không bảo vệ hoặc public key chưa được xác thực nguồn.

## 12. Tóm tắt và checklist nhanh

| Muốn làm gì? | Dùng gì? |
| --- | --- |
| Sinh Ed25519/Ed448 key pair | `KeyPairGenerator.getInstance("Ed25519")` / `"Ed448"` |
| Xuất public key (khi provider cho phép) | `pair.getPublic().getEncoded()` → **X.509 SPKI DER** |
| Xuất private key (khi provider cho phép) | `pair.getPrivate().getEncoded()` → **PKCS#8 DER** |
| Nhập public key | `KeyFactory.generatePublic(new X509EncodedKeySpec(der))` |
| Nhập private key chưa mã hóa | `KeyFactory.generatePrivate(new PKCS8EncodedKeySpec(der))` |
| Chuyển DER sang PEM | Base64 + marker đúng định dạng; không làm dữ liệu bí mật an toàn hơn |
| Có certificate thay vì SPKI | Dùng `CertificateFactory`, sau đó lấy public key từ certificate đã được xác thực |
| Có private key bị mã hóa | Sử dụng giải mã/bảo vệ khóa được hỗ trợ; không nạp trực tiếp vào `PKCS8EncodedKeySpec` |
| Khóa không export | Dùng provider/keystore/HSM để vận hành trực tiếp, không yêu cầu DER private key |

**Ghi nhớ quan trọng:** X.509 SPKI biểu diễn **public key**; PKCS#8 biểu diễn **private key**. Cả hai thường là **DER của ASN.1 có AlgorithmIdentifier**, không phải raw key bytes. Các API mã hóa và nhập khóa EdEC ở Java 15+ vẫn còn hợp lệ trong Java hiện đại.

## 13. Tài liệu tham khảo còn hiệu lực

- [RFC 8410 — Algorithm Identifiers for Ed25519, Ed448, X25519, X448](https://www.rfc-editor.org/rfc/rfc8410.html): OID, AlgorithmIdentifier, định dạng SPKI/private key, yêu cầu *parameters absent*.
- [RFC 8032 — Edwards-Curve Digital Signature Algorithm](https://www.rfc-editor.org/rfc/rfc8032): biểu diễn khóa và chữ ký Ed25519/Ed448.
- [OpenJDK JEP 339 — Edwards-Curve Digital Signature Algorithm (Java 15)](https://openjdk.org/jeps/339): mốc hỗ trợ EdDSA chính thức.
- [Oracle Java SE 27 — JCA Reference Guide](https://docs.oracle.com/en/java/javase/27/security/java-cryptography-architecture-jca-reference-guide.html): `KeyFactory`, KeySpecs, format `X.509` và `PKCS#8`.
- [Oracle Java SE 27 — KeyFactory](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/KeyFactory.html): `generatePublic`/`generatePrivate`.
- [Oracle Java SE 27 — X509EncodedKeySpec](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/spec/X509EncodedKeySpec.html): cách dùng SPKI public key.
- [Oracle Java SE 27 — PKCS8EncodedKeySpec](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/spec/PKCS8EncodedKeySpec.html): cách dùng private-key DER.
- [Oracle Java SE 27 — Security Providers](https://docs.oracle.com/en/java/javase/27/security/oracle-providers.html): Ed25519/Ed448 và implementation JCA tích hợp.

Bài học chỉ sử dụng Java API chính thức, còn được hỗ trợ hiện nay; không dựa vào cơ chế legacy, feature preview đã hết hiệu lực hoặc các cách tự chế DER không an toàn.