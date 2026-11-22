# 10.3. Chu trình init, doPhase, generateSecret và kiểm tra khóa của đối tác

## 1. Vì sao cần KeyAgreement?

Khi hai bên A và B liên lạc qua một mạng có thể bị quan sát, họ cần thiết lập **cùng một bí mật chung** để từ đó dẫn xuất khóa phiên dùng cho mã hóa đối xứng hoặc bọc khóa. Nếu A và B có thể làm việc đó mà không gửi trực tiếp private key hoặc bí mật chung trên đường truyền, ta có **thỏa thuận khóa** (*key agreement*).

Trong Java/JCA/JCE, `javax.crypto.KeyAgreement` cung cấp engine cho các thuật toán như **Diffie–Hellman (DH)**, **Elliptic Curve Diffie–Hellman (ECDH)** và **X25519/X448** (thuộc họ XDH). Mô hình hai phía thường là:

- A sinh cặp `privateA/publicA`, B sinh cặp `privateB/publicB` với cùng thuật toán và tham số tương thích.
- A nhận `publicB`, dùng **privateA** để tính bí mật chung.
- B nhận `publicA`, dùng **privateB** để tính bí mật chung.
- Theo tính chất thuật toán, với khóa hợp lệ và cùng tham số, **hai phía thu được cùng giá trị** mà không cần truyền nó qua mạng.

Nhưng có ba điều không được đánh đồng:

1. **Đúng chu trình API**: `init` → `doPhase` → `generateSecret`.
2. **Khóa công khai đối tác hợp lệ về kỹ thuật**: đúng kiểu, tham số/curve, biểu diễn và các kiểm tra mật mã cần thiết.
3. **Khóa thật sự thuộc về đối tác mong muốn**: phải được **xác thực qua cơ chế tin cậy** như khóa đã pin, chứng thư được kiểm tra hoặc trao đổi khóa có xác thực.

Bước (1) và (2) **không tự bảo đảm bước (3)**. Một kẻ đứng giữa (*man-in-the-middle*, MITM) có thể thay public key trên đường truyền và tạo **hai phiên thỏa thuận khóa khác nhau** nếu hệ thống không xác thực khóa của bên kia.

**Mục tiêu bài học:** hiểu trạng thái của `KeyAgreement`, đặt đúng `lastPhase`, quản lý kết quả `generateSecret`, kiểm tra khóa của đối tác ở nhiều tầng, rồi dẫn xuất khóa đối xứng một cách an toàn thay vì coi raw shared secret là khóa AES sẵn sàng sử dụng.

## 2. Cơ chế ở cấp giao thức: bí mật chung không được gửi đi

Minh họa mô hình **hai bên**:

```text
Alice                                              Bob
-----                                              ---
(privateA, publicA)                                (privateB, publicB)
         |                                            |
         |  ----- publicA (được xác thực) ----------> |
         | <----- publicB (được xác thực) ----------- |
         |                                            |
KeyAgreement.init(privateA)               KeyAgreement.init(privateB)
doPhase(publicB, true)                     doPhase(publicA, true)
generateSecret() -> sharedA                generateSecret() -> sharedB
         |                                            |
         +------------ sharedA == sharedB -------------+
                              |
                  KDF (HKDF + ngữ cảnh)
                              |
              Khóa phiên cho AEAD / bọc khóa
```

**Public key không phải bí mật.** Tuy nhiên, public key nhận từ mạng **chưa tự đáng tin** chỉ vì parse thành công, có chuỗi Base64 đúng hoặc được `KeyAgreement.doPhase` chấp nhận.

Ở phía A, giá trị đưa vào `init` là **khóa riêng của chính A**; khóa đưa vào `doPhase` là **khóa công khai của B**. Không đưa private key của B vào `doPhase`; không gửi private key của A cho B. Hệ thống thực tế cần xác thực thông điệp chứa public keys hoặc đối chiếu chúng với một kênh đăng ký/trust đã được bảo vệ.

**Lưu ý thuật ngữ:** `KeyAgreement` thường *tính* raw shared secret; nó **không mã hóa** payload, **không tạo chữ ký số** và **không tự bọc khóa**. Sau khi xác thực trao đổi và dẫn xuất khóa phiên, ứng dụng mới có thể dùng `Cipher`/AEAD hoặc thuật toán bọc khóa phù hợp.

## 3. Vòng đời KeyAgreement trong JCA

### 3.1. Tạo engine bằng getInstance

```java
KeyAgreement ka = KeyAgreement.getInstance("X25519");
```

Cần import `javax.crypto.KeyAgreement`. Chuỗi `"X25519"` là **tên thuật toán**, không phải provider. Từ Java 17, JDK thông dụng hỗ trợ X25519, nhưng hệ thống thay provider/chính sách mật mã có thể khác; ứng dụng cần cấu hình thuật toán được phép và kiểm tra hỗ trợ.

Không dùng `"AES"` để tạo `KeyAgreement`: AES là thuật toán **mã hóa đối xứng**, không phải phép thỏa thuận khóa. Tương tự, `Ed25519` dùng để ký/xác minh, **không** được coi như khóa X25519 có thể đổi tên tùy ý.

### 3.2. init(privateKey): đặt trạng thái ban đầu

```java
ka.init(ownPrivateKey);
```

`init` chuẩn bị engine với **thông tin bí mật của bên cục bộ** và các tham số cần thiết. Với X25519, private key tương ứng với keypair X25519 đã sinh; với classic DH/ECDH cần các tham số nhóm/curve tương thích. Các overload cho phép truyền `AlgorithmParameterSpec` và/hoặc `SecureRandom` khi thuật toán/provider cần.

Lỗi cần biết:

- `InvalidKeyException` nếu đưa khóa không thích hợp: sai loại, sai thuật toán hoặc không tương thích.
- `InvalidAlgorithmParameterException` nếu sử dụng overload có tham số không phù hợp.
- Có thể phát sinh lỗi tạo engine như `NoSuchAlgorithmException` nếu thuật toán không tồn tại ở provider khả dụng.

**`init` không tự lấy public key đối tác qua mạng** và cũng không tự kiểm tra đối tác là ai. Nó đặt trạng thái của engine để xử lý giai đoạn thỏa thuận.

### 3.3. doPhase(peerPublicKey, lastPhase): xử lý từng bên tham gia

Trong thỏa thuận khóa **hai bên**, thường gọi:

```java
ka.doPhase(peerPublicKey, true);
```

- `peerPublicKey` là khóa cho giai đoạn hiện tại, thường là **public key của bên kia**.
- `lastPhase=true` cho biết **đây là giai đoạn cuối**.
- Với hai bên, gọi **một lần** và đặt `true`.
- `doPhase` trả một `Key` trung gian hoặc `null` nếu giai đoạn đó không tạo ra khóa trung gian cần dùng. Trong demo X25519 hai bên, không cần lấy giá trị trả về.

Các thuật toán đa bên có thể dùng nhiều giai đoạn, trong đó `false` được dùng trước giai đoạn cuối; nhưng **không** được tự suy đoán mọi provider/thuật toán đều hỗ trợ cấu hình nhiều bên. Với X25519/ECDH hai bên thông thường, đừng đặt `false` rồi gọi `generateSecret` như thể đã hoàn tất.

Nếu engine chưa `init`, `doPhase` có thể ném `IllegalStateException`. Khóa đối tác không phù hợp có thể gây `InvalidKeyException`. **Việc doPhase chấp nhận một public key không đồng nghĩa public key đó đã được xác thực về danh tính.**

### 3.4. generateSecret(): lấy raw shared secret

Sau khi xử lý đủ giai đoạn:

```java
byte[] rawSharedSecret = ka.generateSecret();
```

`generateSecret()` tạo **một byte[] mới** chứa bí mật chung. Đừng in ra console, gửi qua mạng, thêm vào log hoặc hardcode nó trong cấu hình. Ngay cả khi public keys công khai, bí mật chung phải được xử lý như **secret key material**.

Java 17 có các overload:

| Phương thức | Ý nghĩa |
| --- | --- |
| `generateSecret()` | Tạo `byte[]` mới chứa bí mật chung. |
| `generateSecret(byte[] target, int offset)` | Ghi secret vào buffer caller cung cấp; trả số byte đã ghi; có thể ném `ShortBufferException` nếu không đủ chỗ. |
| `generateSecret(String algorithm)` | Yêu cầu provider tạo `SecretKey` thuộc thuật toán được chỉ định; phụ thuộc việc thuật toán/provider hỗ trợ và tính tương thích của key material, có thể ném lỗi. |

**Không coi `generateSecret("AES")` là HKDF chuẩn hóa có ràng buộc phiên trên mọi provider.** Đây là overload tạo khóa theo cơ chế của engine/provider, không tự cung cấp toàn bộ salt, transcript hash, context và key separation mà một giao thức hiện đại có thể đòi hỏi. Khi thiết kế protocol mới, nên quy định **KDF rõ ràng**, ví dụ HKDF-HMAC-SHA256, theo đặc tả và thư viện được kiểm chứng.

**State sau `generateSecret`:** tài liệu `KeyAgreement` quy định engine được reset về trạng thái sau lần `init` gần nhất. Có thể gọi `doPhase`/`generateSecret` lần nữa với cùng private key, hoặc gọi `init` để thay thông tin riêng; **việc reset state không sinh một private key mới**. Nếu protocol dùng *ephemeral ECDH* để có forward secrecy, application phải thực sự sinh keypair mới theo chính sách phiên, không trông chờ reset engine tự làm vậy.

Gọi `generateSecret` khi chưa `init` hoặc khi chưa hoàn thành các `doPhase` cần thiết sẽ gây `IllegalStateException`.

### 3.5. Bảng thứ tự gọi

| Thứ tự | Hợp lệ? | Kết quả/chú ý |
| --- | --- | --- |
| `getInstance` → `init(ownPrivate)` → `doPhase(peerPublic,true)` → `generateSecret()` | **Có**, hai bên | Trả raw shared secret nếu khóa, thuật toán và các kiểm tra hợp lệ. |
| `getInstance` → `generateSecret()` | **Không** | Chưa init/chưa xử lý giai đoạn, lỗi trạng thái. |
| `init(ownPrivate)` → `generateSecret()` | **Không** | Chưa có public key đối tác; lỗi trạng thái. |
| `init(ownPrivate)` → `doPhase(peerPublic,true)` → `generateSecret()` → `generateSecret()` | **Không**, nếu thiếu giai đoạn mới | Sau lần đầu engine reset, phải nạp lại key của bên kia. |
| `init(ownPublic)` → `doPhase(peerPrivate,true)` | **Sai loại khóa** | Private key phải ở phía `init`; public key đối tác ở `doPhase`. |
| `init(ownPrivate)` → `doPhase(peerPublic,false)` → `generateSecret()` | **Không phải chu trình hai bên hoàn chỉnh** | `false` chỉ có ý nghĩa khi còn giai đoạn và thuật toán hỗ trợ. |

## 4. Kiểm tra public key đối tác: ba tầng khác nhau

**Kiểm tra public key không phải một phép kiểm đơn lẻ.** Để trả lời “đây có phải khóa đáng tin của B không?”, tách ít nhất ba tầng.

### Tầng 1 — Kiểm tra biểu diễn và input

- Dữ liệu public key có nằm trong giới hạn kích thước, format, version và encoding giao thức cho phép không?
- Nếu giao thức truyền `SubjectPublicKeyInfo` DER, dùng `X509EncodedKeySpec` với `KeyFactory` tương ứng thay vì tùy tiện parse bytes.
- Xác định **algorithm allowlist**, không để client tùy ý chọn kiểu khóa/curve từ header mà không có policy.
- Nếu đầu vào malformed, không được chấp nhận hoặc fallback sang thuật toán yếu hơn.

Java `PublicKey.getEncoded()` trong nhiều provider trả **X.509 SubjectPublicKeyInfo (SPKI)**, *không phải* một certificate X.509 đã được CA xác nhận, và *không nhất thiết là raw 32 byte X25519* của một wire protocol. `X509EncodedKeySpec` cần byte encoding dạng SPKI; nếu giao thức truyền raw X25519 public key, phải dùng cách decode đúng cấu trúc và byte order của **chính giao thức**, không bọc tùy tiện.

Tầng này chỉ trả lời “đây là một key object parse được đúng định dạng?”, **chưa** trả lời “key hợp lệ cho nhóm?” và “nó thuộc đối tác B?”.

### Tầng 2 — Kiểm tra thuật toán, tham số và giá trị khóa

**DH cổ điển:** phải tuân theo tham số nhóm `p, g` (và cấu trúc nhóm/subgroup) được duyệt, kiểm tra public value của đối tác trong miền hợp lệ và các kiểm tra subgroup khi thuật toán/nhóm yêu cầu. Đừng tự tạo nhóm số nguyên tố không rõ nguồn gốc.

**ECDH truyền thống trên curve Weierstrass** (ví dụ `secp256r1`): kiểm tra khóa đối tác đúng kiểu, **đúng curve và các tham số**, điểm không phải point at infinity, tọa độ hợp lệ, điểm nằm trên curve; với nhóm/curve có yêu cầu còn cần kiểm tra order/subgroup. Không chấp nhận arbitrary curve do bên ngoài tự chỉ định. Dùng implementation/provider có validation đúng, nhưng vẫn phải áp dụng **policy curve** ở ứng dụng; không nên chỉ so tên string `"EC"`.

**X25519:** dùng đúng tên `X25519`, loại `XECPublicKey` và tham số `NamedParameterSpec.X25519` nếu giao thức yêu cầu. Không lẫn với `X448` hay `Ed25519`. X25519 được thiết kế để xử lý biểu diễn điểm theo quy tắc riêng của RFC 7748, vì vậy **không áp dụng máy móc công thức kiểm tra điểm ECDH Weierstrass** lên public key X25519. RFC 7748 cho phép kiểm tra raw shared secret **toàn byte zero** và từ chối nếu xảy ra; ví dụ Java bên dưới có bước từ chối này. Provider có thể từ chối public key/đầu ra không hợp lệ ở `doPhase` hoặc `generateSecret`; đây là **kiểm tra hợp lệ mật mã**, không thay thế kiểm tra danh tính.

**Quan trọng:** cùng tên thuật toán hoặc cùng độ dài public key **không đủ** để chứng minh hợp lệ hoặc đáng tin. Các kiểm tra giá trị nhóm/curve cần được giao cho thư viện/provider mật mã đáng tin, theo đúng RFC/chuẩn của thuật toán; không tự bỏ qua ngoại lệ nếu provider báo lỗi.

### Tầng 3 — Xác thực khóa thuộc đúng đối tác

Ngay cả một X25519 public key hoàn toàn hợp lệ về toán học cũng có thể thuộc về **kẻ tấn công**. Cần một ràng buộc tin cậy, ví dụ:

1. **Key pinning:** ứng dụng lưu byte SPKI/fingerprint public key của đối tác từ một **quy trình đăng ký tin cậy**; lúc kết nối, so sánh đúng với khóa nhận được. Cần chiến lược rotation/thu hồi và cập nhật pin có kiểm soát.
2. **Chứng thư X.509/PKI:** kiểm tra chain đến trust anchor, danh tính/hostname/service identity, key usage, effective validity, revocation/chính sách khi cần. `certificate.getPublicKey()` đơn thuần **không thực hiện các bước tin cậy đó**.
3. **Signature trên key exchange transcript:** một identity signing key đã được xác thực ký public key tạm, nonce, danh tính vai trò và ngữ cảnh giao thức. Bên còn lại verify chữ ký **bằng key tin cậy** trước khi dùng kết quả.
4. **PSK/authenticated protocol:** tích hợp trao đổi khóa vào một giao thức đã được phân tích như TLS 1.3 (đúng cấu hình và kiểm tra chứng thư/PSK), thay vì tự chế giao thức trên raw ECDH.

**Không có kiểm tra tầng 3 thì không có peer authentication.** `KeyAgreement` một mình cung cấp khả năng tính toán bí mật chung, **không** biết đối tác tên gì, thuộc tenant nào hoặc có quyền ký hợp đồng hay không.

## 5. Demo Java 17+ chạy được: X25519 và kiểm tra khóa công khai

Bài demo tạo ba keypair: Alice, Bob và một bên thay thế khóa. Nó kiểm tra được những điểm sau:

- A và B mỗi người dùng **private key của mình**, **public key của người kia** theo chu trình `init` → `doPhase(..., true)` → `generateSecret()`.
- A và B có cùng **32 byte** raw shared secret X25519.
- Public key truyền ở dạng **SPKI encoded** được parse bằng `KeyFactory`, kiểm tra kiểu và tham số thuật toán.
- “Alice public key đáng tin” trong demo là một **pin giả lập được thiết lập ngoài đường truyền**. Public key của bên thay thế không khớp pin.
- Bob dùng public key bên thay thế sẽ tính **bí mật khác** với bí mật A–B. Điều này mô phỏng nguy cơ MITM, không phải một giao thức xác thực hoàn chỉnh.
- Nếu `generateSecret` được gọi khi chưa `doPhase`, engine từ chối do sai trạng thái.

Tạo file `KeyAgreementLifecycleDemo.java`:

```java
import java.security.GeneralSecurityException;
import java.security.InvalidKeyException;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.interfaces.XECPublicKey;
import java.security.spec.NamedParameterSpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;
import javax.crypto.KeyAgreement;

public final class KeyAgreementLifecycleDemo {
    private static PublicKey parsePeerX25519(byte[] spki)
            throws GeneralSecurityException {
        if (spki == null || spki.length == 0 || spki.length > 1024) {
            throw new InvalidKeyException("Invalid peer key encoding size");
        }
        PublicKey result = KeyFactory.getInstance("X25519")
                .generatePublic(new X509EncodedKeySpec(spki));
        if (!(result instanceof XECPublicKey xec)
                || !(xec.getParams() instanceof NamedParameterSpec params)
                || !"X25519".equals(params.getName())) {
            throw new InvalidKeyException("Unexpected peer key parameters");
        }
        return result;
    }

    private static byte[] agree(PrivateKey ownPrivate, PublicKey peerPublic)
            throws GeneralSecurityException {
        KeyAgreement agreement = KeyAgreement.getInstance("X25519");
        agreement.init(ownPrivate);
        agreement.doPhase(peerPublic, true);
        byte[] shared = agreement.generateSecret();
        int nonzero = 0;
        for (byte b : shared) nonzero |= b & 0xff;
        if (nonzero == 0) {
            Arrays.fill(shared, (byte) 0);
            throw new InvalidKeyException("Rejected all-zero shared secret");
        }
        return shared;
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        KeyPair alice = generator.generateKeyPair();
        KeyPair bob = generator.generateKeyPair();
        KeyPair attacker = generator.generateKeyPair();

        // In production this pin must be provisioned via a trusted channel.
        byte[] trustedAliceSpki = alice.getPublic().getEncoded();
        PublicKey aliceFromWire = parsePeerX25519(
                alice.getPublic().getEncoded());
        PublicKey bobFromWire = parsePeerX25519(
                bob.getPublic().getEncoded());
        PublicKey fakeAlice = parsePeerX25519(
                attacker.getPublic().getEncoded());

        System.out.println("Trusted peer pin matches: " +
                Arrays.equals(trustedAliceSpki, aliceFromWire.getEncoded()));
        System.out.println("Substituted peer passes pin: " +
                Arrays.equals(trustedAliceSpki, fakeAlice.getEncoded()));

        byte[] secretAlice = agree(alice.getPrivate(), bobFromWire);
        byte[] secretBob = agree(bob.getPrivate(), aliceFromWire);
        byte[] wrongSecretBob = agree(bob.getPrivate(), fakeAlice);
        try {
            System.out.println("X25519 secret bytes: " + secretAlice.length);
            System.out.println("Both parties agree: " +
                    MessageDigest.isEqual(secretAlice, secretBob));
            System.out.println("Wrong peer yields same secret: " +
                    MessageDigest.isEqual(secretAlice, wrongSecretBob));

            KeyAgreement unfinished = KeyAgreement.getInstance("X25519");
            unfinished.init(alice.getPrivate());
            boolean rejected = false;
            try {
                unfinished.generateSecret();
            } catch (IllegalStateException expected) {
                rejected = true;
            }
            System.out.println("No doPhase rejected: " + rejected);
        } finally {
            Arrays.fill(secretAlice, (byte) 0);
            Arrays.fill(secretBob, (byte) 0);
            Arrays.fill(wrongSecretBob, (byte) 0);
        }
    }
}
```

Biên dịch và chạy (JDK 17+ có provider X25519):

```bash
javac KeyAgreementLifecycleDemo.java
java KeyAgreementLifecycleDemo
```

Stdout được kiểm chứng:

```text
Trusted peer pin matches: true
Substituted peer passes pin: false
X25519 secret bytes: 32
Both parties agree: true
Wrong peer yields same secret: false
No doPhase rejected: true
```

### 5.1. Tại sao stdout luôn theo cấu trúc này?

Các keypair được tạo ngẫu nhiên mỗi lần chạy, do đó raw public/private/shared secret **thay đổi** và không được in. Nhưng:

- Bản sao `aliceFromWire` parse từ chính SPKI của Alice sẽ khớp với pin demo `trustedAliceSpki`.
- Public key của cặp khóa bên thay thế khác pin Alice, nên xác minh pin cho `false` (với xác suất trùng key cực nhỏ về mặt toán học, không phải công cụ kiểm thử bảo mật tuyệt đối).
- Do tính chất X25519, Alice và Bob tính cùng shared secret dài 32 byte. Khi Bob tính với public key của keypair khác, kết quả thông thường không khớp secret A–B.
- Chưa gọi `doPhase` nhưng đã gọi `generateSecret` là lỗi trạng thái theo hợp đồng API.

Dòng `MessageDigest.isEqual` chỉ dùng để **chứng minh hai byte array ở demo giống/khác nhau**. Trong ứng dụng production, không cần đem raw secrets của hai bên lên mạng để so sánh; việc đó **làm lộ bí mật phiên**. Hãy dùng phương thức xác nhận phiên có xác thực (ví dụ finished message/MAC trên transcript) theo giao thức được thiết kế và kiểm chứng.

### 5.2. Điều demo kiểm tra và không kiểm tra

Hàm `parsePeerX25519` áp dụng một **giới hạn kích thước demo 1.024 byte** (đây là policy minh họa, **không** phải ngưỡng chuẩn của RFC 7748); parse DER-SPKI bằng `KeyFactory` rồi kiểm tra `XECPublicKey` có `NamedParameterSpec` là X25519. Nó **không** xác nhận key thuộc Alice/Bob; bước pin mới minh họa trust.

Đặc biệt, `trustedAliceSpki` đang lấy trực tiếp từ keypair Alice trong cùng chương trình; điều này **không tái hiện việc provision key giữa hai máy thật**. Ngoài đời, bên nhận phải có public key đáng tin từ trước/qua trust anchor, không được tạo “pin” bằng cách lưu chính public key vừa nhận từ kết nối chưa xác thực rồi tuyên bố đã chống MITM.

Việc dùng `Arrays.equals` cho **SPKI public key** là hợp lý ở minh họa vì các byte public này không phải bí mật. Đối với raw shared secrets, demo dùng `MessageDigest.isEqual` thay vì log/display. Hai mảng raw secret do application nhận được được `Arrays.fill` khi không còn cần; việc xóa này chỉ là best-effort đối với **những byte[] cụ thể**, không chứng minh mọi bản sao trong JVM/provider đã được xóa.

### 5.3. Kiểm tra all-zero shared secret

RFC 7748 cho X25519 nói rằng có thể kiểm tra kết quả toàn zero và abort để giảm rủi ro từ một số input nhỏ bậc (*small-order*). Hàm `agree` dùng phép OR qua **toàn bộ byte** thay vì dừng ở byte đầu không zero, rồi từ chối nếu tất cả bằng zero. Nếu provider từ chối key không hợp lệ ngay trong `doPhase`/`generateSecret` thì luồng cũng phải được coi là lỗi và **không** fallback sang shared secret khác.

Kiểm tra all-zero **không phải peer authentication**: một public key X25519 hợp lệ do kẻ tấn công kiểm soát vẫn có thể tạo shared secret khác zero. Phải kết hợp với tầng trust/identity trước khi coi phiên là đáng tin.

## 6. Tấn công man-in-the-middle nếu chỉ chạy KeyAgreement

Giả sử Eve đứng giữa Alice và Bob, chặn public key và gửi key của Eve thay thế:

```text
Alice                 Eve (MITM)                      Bob
  |                        |                           |
  | ---- publicAlice ----> |                           |
  |                        | -- publicEve1 ----------> |
  | <---- publicEve2 ----- |                           |
  |                        | <-------- publicBob ----- |
  |                        |                           |
secret(Alice, Eve2)    2 secret với hai bên       secret(Bob, Eve1)
  |                        |                           |
  +----- mỗi cặp tính được shared secret hợp lệ -------+
      NHƯNG Alice và Bob KHÔNG cùng một secret với nhau
```

Eve có thể dùng khóa phiên với Alice để đọc/ghi lại thông điệp, rồi tạo thông điệp mới bảo vệ bằng khóa phiên khác với Bob, nếu protocol không xác thực trao đổi khóa và không có bảo vệ bổ sung.

**Phân biệt hai kết quả:**

- `doPhase` chạy thành công: chỉ chứng minh public key tương thích thuật toán, **không chứng minh identity**.
- `generateSecret` trả nonzero bytes: chứng minh phép thỏa thuận với một public key có thể hoàn thành, **không chứng minh đối tác muốn kết nối đã tham gia**.

**Biện pháp:** xác thực public keys và các thông điệp bắt tay bằng chứng thư/chữ ký/PSK tin cậy, kiểm tra danh tính người tham gia và **ràng buộc toàn bộ transcript** (vai trò A/B, public keys, algorithm, session ID/nonce, version và ngữ cảnh) vào việc dẫn xuất/kiểm tra khóa. Trong ứng dụng thông thường, ưu tiên **TLS 1.3 hoặc protocol đã được đánh giá** thay vì phát minh giao thức trao đổi khóa riêng.

## 7. Từ raw secret sang khóa AES, MAC hoặc khóa bọc

### 7.1. Vì sao không dùng trực tiếp raw shared secret?

Bí mật thỏa thuận là **keying material**, không phải mặc nhiên một `SecretKey` đúng quy chuẩn cho mọi mục đích. Giao thức phải:

1. Xác nhận thuật toán, tham số và input hợp lệ.
2. Xác thực các public keys/ngữ cảnh theo threat model.
3. Dùng **KDF** được đặc tả để trích xuất và dẫn xuất một hoặc nhiều khóa từ raw secret.
4. Đưa **thông tin transcript/ngữ cảnh** vào quá trình dẫn xuất: tên thuật toán, phiên bản, public keys, vai trò A/B, nonces/session ID, mục đích sử dụng.
5. Dẫn xuất **khóa riêng theo chức năng**: chẳng hạn khóa AES-GCM gửi A→B, khóa AES-GCM B→A, key confirmation MAC, hoặc khóa phục vụ bọc khóa.

Cách phổ biến là **HKDF** (`Extract` và `Expand` theo RFC 5869) trên shared secret, với salt và `info` được thỏa thuận rõ. Ví dụ ở mức khái niệm (không phải mã Java chạy trực tiếp):

```text
sharedSecret = X25519(privateLocal, publicPeer)

transcriptHash = Hash(protocolVersion || algorithms || roleIds
                   || publicAlice || publicBob || nonces || context)

PRK = HKDF-Extract(salt, sharedSecret)
clientWriteKey = HKDF-Expand(PRK, "client_write" || transcriptHash, keyLen)
serverWriteKey = HKDF-Expand(PRK, "server_write" || transcriptHash, keyLen)

Xóa raw sharedSecret / PRK tạm do ứng dụng sở hữu sau khi dùng.
```

Các chuỗi trong dấu ngoặc kép ở đây là **nhãn mục đích minh họa**, không phải format chuẩn của TLS hay bất kỳ giao thức hiện hữu nào. Trong thực tế, phải dùng encoding không mơ hồ và định nghĩa rõ `salt`/`info`, hướng khóa, version, độ dài khóa, lựa chọn AEAD và các trạng thái chống replay. Nếu chưa có giao thức được kiểm chứng, đừng tự triển khai HKDF/handshake chỉ dựa trên sơ đồ này.

Java 17 **không có API HKDF chung bắt buộc mọi provider phải cung cấp**. Có thể sử dụng thư viện mật mã được duyệt để thực hiện HKDF đúng chuẩn hoặc một giao thức chuẩn đã tích hợp sẵn. Đừng dùng `new SecretKeySpec(rawSharedSecret, "AES")` như một giải pháp mặc định cho key schedule của một giao thức mới.

### 7.2. Liên hệ với bọc khóa

Sau khi đã có **key-encryption key (KEK)** được dẫn xuất đúng ngữ cảnh từ thỏa thuận khóa, ứng dụng có thể dùng một thuật toán **key wrap** hoặc AEAD được chỉ định để bảo vệ **data-encryption key (DEK)**, rồi gửi dữ liệu đã bọc cho phía kia.

`KeyAgreement.generateSecret()` **không tự thực hiện wrap/unwrap**, không tạo ciphertext và không thay thế `Cipher`. Việc unwrap thành công phải được kết hợp với xác thực peer/key transcript và chính sách sử dụng khóa; một khóa được dẫn xuất đúng mật mã nhưng thuộc nhầm peer vẫn có thể gây lỗi an ninh nghiêm trọng.

## 8. Giữ đúng trạng thái, thời hạn khóa và phân biệt các loại key

### 8.1. Ephemeral và static private key

- **Ephemeral keypair:** sinh cho phiên/lượt handshake; sau khi xong, hạn chế tái sử dụng và dọn references/buffers theo khả năng provider. Đây là thành phần quan trọng của nhiều giao thức có forward secrecy.
- **Static keypair:** có thể phục vụ nhận dạng/thỏa thuận nhiều phiên tùy thiết kế; cần quản lý vòng đời, bảo vệ private key và đánh giá lại forward secrecy.
- **Signing key ≠ key-agreement key:** Ed25519 dùng `Signature`; X25519 dùng `KeyAgreement`. Không nên “đổi nhãn” hoặc tái dùng cùng vật liệu khóa giữa các thuật toán cho các mục đích khác nhau mà thiếu đặc tả được phân tích.

**Forward secrecy** không xuất hiện chỉ nhờ gọi `generateSecret`. Nó phụ thuộc giao thức, cách kết hợp khóa ephemeral và xác thực, việc tiêu hủy private ephemeral và những giả định về an ninh của thuật toán.

### 8.2. Không chia sẻ mutable engine qua thread

`KeyAgreement` là đối tượng trạng thái: `init` và `doPhase` thay đổi tiến trình xử lý. Đừng dùng **một instance** chung cho nhiều session đồng thời hoặc các peer khác nhau rồi coi rằng engine tự cô lập. Mỗi handshake nên có engine và key material riêng. Sau `generateSecret`, muốn chạy lượt mới phải gọi `doPhase` (và nhiều khi `init` với key mới) theo thiết kế.

### 8.3. Không log private key hoặc shared secret

Có thể log metadata không nhạy cảm (algorithm, key identifier, kết quả chấp nhận/từ chối, lỗi đã làm sạch) nhưng không log `privateKey.getEncoded()`, raw secret, session key, KDF intermediate key hoặc request payload nhạy cảm. Nếu key được export thành `byte[]`, wipe bản sao do caller sở hữu sau khi dùng; việc này vẫn **không chứng minh** provider/GC/JVM đã xóa mọi vết trong memory.

### 8.4. Kiểm tra keyId không phải xác thực

Trường `keyId` được gửi qua mạng có thể dùng để **tìm** public key trong registry tin cậy. Nhưng bản thân chuỗi `keyId` có thể do attacker đặt; chỉ chấp nhận key khi registry, trust policy, authentication và authorization cùng khớp. Cần chống nhầm tenant, nhầm mục đích ký/thỏa thuận, nhầm algorithm và tấn công downgrade.

## 9. Các lỗi Java thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `NoSuchAlgorithmException` tại `getInstance("X25519")` | Provider/JDK không hỗ trợ hoặc policy không cho phép | Chọn JDK/provider đã được kiểm tra; cấu hình danh sách thuật toán được duyệt. |
| `InvalidKeyException` tại `init` | Đưa public key thay private key, sai loại hoặc sai tham số | Chỉ đưa private key cục bộ thuộc đúng thuật toán. |
| `InvalidKeyException` tại `doPhase` | Peer key sai thuật toán/curve, input không hợp lệ hoặc provider từ chối | Kiểm tra DER/curve/type/policy và từ chối; không tắt validation. |
| `IllegalStateException` tại `doPhase` | Engine chưa init | Bắt đầu bằng `init`. |
| `IllegalStateException` tại `generateSecret` | Chưa init hoặc chưa hoàn tất giai đoạn | Hai bên dùng `doPhase(peer,true)` trước. |
| `ShortBufferException` từ `generateSecret(buffer,offset)` | Buffer caller quá nhỏ | Dùng buffer đủ cỡ hoặc `generateSecret()` tạo byte[] mới; không dùng secret nửa chừng. |
| `InvalidKeySpecException` từ `KeyFactory.generatePublic` | SPKI DER sai định dạng hoặc key không parse được | Từ chối dữ liệu malformed; không cố đoán hay bỏ qua lỗi. |
| Secret khác nhau giữa hai phía | Dùng sai public/private, peer bị thay thế, sai group hoặc keypair không khớp | Kiểm tra identity/trust của peer public key và transcript; không truyền secrets để so sánh trực tiếp. |
| Shared secret toàn zero trong X25519 | Peer public key có thể liên quan tới input bậc nhỏ hoặc bị thay thế | Từ chối shared secret và phiên; để provider thực hiện validation theo RFC. |
| Tạo AES key trực tiếp từ raw secret | Thiếu KDF, key separation và ràng buộc phiên | Dùng KDF được thiết kế theo protocol, ví dụ HKDF. |
| Handshake chạy được nhưng MITM vẫn thành công | Chỉ validate format/curve, không xác thực identity | Pin/trust certificate, signature hoặc dùng TLS có xác thực. |
| Reuse engine/private key dù mong forward secrecy | Hiểu sai việc `generateSecret` reset state | Sinh ephemeral keypair mới theo session/policy. |

**Phân biệt lỗi kỹ thuật với kết luận bảo mật:** từ chối input không hợp lệ là đúng. Nhưng nếu một public key giả hoàn toàn hợp lệ và `doPhase` không báo lỗi, kết quả đó **không** cho phép bỏ qua bước xác thực nguồn khóa.

## 10. Tình huống before–after: kiểm tra đối tác đúng cách

### Before: chỉ parse key và hoàn thành thỏa thuận

```text
Nhận bytes publicKey từ socket
-> KeyFactory.generatePublic(bytes)
-> KeyAgreement.init(myPrivate)
-> KeyAgreement.doPhase(peerPublic,true)
-> byte[] secret = generateSecret()
-> Dùng secret như khóa mã hóa
```

Vấn đề: public key có thể do attacker thay thế; thiếu xác thực danh tính, thiếu KDF, thiếu ngữ cảnh protocol và thiếu key separation. Phép thỏa thuận có thể hoàn tất với kẻ tấn công.

### After: xác minh cả cấu trúc và nguồn khóa

```text
Nhận envelope handshake có kích thước/format giới hạn
-> Kiểm tra version + algorithm allowlist
-> Parse peerPublic theo encoding được quy định
-> Kiểm tra key type, tham số, curve/group và giá trị theo chuẩn/provider
-> Xác thực peer key qua pin/truststore/chữ ký transcript/PSK
-> Xác minh role/identity/scope/tenant và chống downgrade
-> Sinh private ephemeral, KeyAgreement.init(privateLocal)
-> doPhase(authenticatedPeerPublic,true) -> generateSecret()
-> Từ chối output bất thường như all-zero X25519 (nếu provider chưa từ chối)
-> KDF ràng buộc transcript + derive session keys tách biệt
-> Key confirmation/finished message theo protocol
-> Chỉ khi handshake và policy hợp lệ mới xử lý payload
```

**Đây là lưu đồ khái niệm, không phải protocol hoàn chỉnh.** Việc xác thực các khóa và nội dung transcript có thể có thứ tự/choreography khác nhau trong TLS và các giao thức chuẩn. Ứng dụng nên dựa trên một giao thức đã có thiết kế an ninh đầy đủ, không tự ráp các bước thành giao thức tùy ý.

## 11. Câu hỏi kiểm tra và bài tập thực hành

1. Hai bên DH/ECDH cần truyền những gì để cùng tính shared secret? Vì sao không gửi private key?
2. Trong `KeyAgreement`, `init` nhận khóa nào và `doPhase` nhận khóa nào? Nếu đảo ngược, lỗi có thể xuất hiện ở đâu?
3. Với thỏa thuận khóa hai bên, tại sao `doPhase(peer,true)` thay vì `false`? Khi nào `false` có thể được dùng?
4. `generateSecret` trả dữ liệu gì? Có tự mã hóa message, xác thực peer hoặc tạo AES key với KDF hoàn chỉnh không?
5. Sau `generateSecret`, engine ở trạng thái nào? Nó có tự tạo ephemeral private key mới không?
6. Vì sao `KeyFactory.generatePublic` thành công **không chứng minh** key thuộc server mong đợi?
7. So sánh những kiểm tra cần thiết với classic DH, ECDH trên `secp256r1` và X25519; điều gì khác nhau về group/point validation?
8. Nếu Alice và Bob bị MITM đổi public keys, liệu `doPhase` có nhất thiết ném exception không? Vì sao?
9. Pin một public key bằng cách lưu ngay khóa vừa nhận trên kênh chưa tin cậy có bảo vệ được lần kết nối đầu tiên không? Cần một nguồn trust nào?
10. Tại sao nên kết hợp raw shared secret với HKDF và transcript để dẫn xuất các khóa có mục đích riêng?
11. Vì sao kiểm tra all-zero của X25519 không chứng minh khóa đến từ đúng đối tác?
12. Muốn dùng kết quả thỏa thuận cho **key wrapping**, bước nào thuộc `KeyAgreement`, bước nào thuộc KDF và `Cipher`/key-wrap algorithm?

**Bài tập A:** chạy `KeyAgreementLifecycleDemo`. Đổi public key của Bob bằng một keypair X25519 mới, kiểm tra secret Alice/Bob không còn khớp, nhưng engine có thể vẫn hoàn thành phép thỏa thuận với key mới. Giải thích vì sao chỉ kiểm tra thuật toán không đủ.

**Bài tập B:** thử gọi `generateSecret` trước `doPhase` và sau khi đã gọi `generateSecret` lần đầu mà chưa thực hiện phase mới. Quan sát `IllegalStateException` theo vòng đời của engine.

**Bài tập C:** mô phỏng registry chứa SPKI của đối tác được provision bằng kênh đáng tin; kiểm tra public key hợp lệ về format nhưng **không trùng pin** bị từ chối trước khi dùng secret. Thử dùng certificate chain có trust anchor phù hợp trong một bài lab riêng để thấy kiểm tra trust khác với `KeyFactory` parse.

**Bài tập D:** thiết kế transcript có protocol version, tên thuật toán, role A/B, public key của cả hai và session nonce. Đặc tả serialization không mơ hồ cùng quy tắc HKDF `info`; phân biệt key A→B và B→A; kiểm thử rằng đổi bất kỳ trường ngữ cảnh nào được xác thực sẽ khiến kết quả xác nhận phiên không khớp.

## 12. Tài liệu chính thức

- [KeyAgreement (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyAgreement.html): `getInstance`, `init`, `doPhase`, `generateSecret`, `lastPhase` và hành vi reset state.
- [KeyFactory (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyFactory.html): dựng public key từ `KeySpec`, kiểm tra format.
- [X509EncodedKeySpec (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/X509EncodedKeySpec.html): public key encoded theo dạng X.509 SubjectPublicKeyInfo.
- [XECPublicKey (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/interfaces/XECPublicKey.html): public key cho họ XEC/XDH, tham số curve và tọa độ.
- [NamedParameterSpec (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/NamedParameterSpec.html): tên tham số `X25519`, `X448` và các nhóm thuật toán liên quan.
- [RFC 7748 — Elliptic Curves for Security](https://www.rfc-editor.org/rfc/rfc7748): X25519/X448, Diffie–Hellman, byte representation, các trường hợp small-order và all-zero shared secret.
- [RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function](https://www.rfc-editor.org/rfc/rfc5869): HKDF-Extract, HKDF-Expand và mục đích tách khóa.
- [Java Security Standard Algorithm Names (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): tên thuật toán `X25519`, `ECDH` và các chuẩn khóa.
