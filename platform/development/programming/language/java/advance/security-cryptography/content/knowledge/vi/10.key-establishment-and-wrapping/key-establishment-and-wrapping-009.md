# 10.9. Quan hệ giữa cơ chế nguyên thủy và một giao thức hoàn chỉnh có xác thực

Một **cơ chế mật mã nguyên thủy** (*cryptographic primitive*) thực hiện một chức năng có phạm vi cụ thể: Diffie–Hellman tạo bí mật chung, KEM đóng gói bí mật cho người nhận, chữ ký số xác minh dữ liệu do bên giữ private key ký, HKDF dẫn xuất các khóa, AEAD mã hóa có xác thực, còn key wrapping bảo vệ khóa khi vận chuyển hoặc lưu trữ. **Một giao thức bảo mật hoàn chỉnh** phải xác định cách các cơ chế đó phối hợp với danh tính, tin cậy public key, trạng thái bắt tay, phiên bản, tham số, bản ghi, vòng đời khóa, chống phát lại và xử lý lỗi.

Đây là bài 10.9 trong chủ đề **“10. Thỏa thuận và bọc khóa”** của Java Advanced – Security & Cryptography. Hai câu hỏi xuyên suốt là:

1. *“Hai phía có cùng một byte secret”* có chứng minh họ đang nói chuyện đúng người không?
2. *“Đã ký, bọc khóa và mã hóa bằng thuật toán an toàn”* có tự tạo nên một giao thức an toàn không?

Câu trả lời cho cả hai câu hỏi đều là **không**, nếu còn thiếu ràng buộc danh tính, bối cảnh, transcript, kiểm tra khóa và trạng thái. Bài này giải thích vì sao, kèm hai chương trình Java 21 chạy được và sơ đồ tư duy để đánh giá giao thức.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt chức năng của **X25519/ECDH, KEM, key wrapping, Ed25519/Signature, HKDF, HMAC và AES-GCM**.
- Trình bày một luồng **man-in-the-middle (MITM)** nơi Diffie–Hellman chạy đúng thuật toán nhưng client trao secret với attacker.
- Hiểu cách một handshake xác thực cần **trusted identity key**, vai trò client/server, thuật toán đã thương lượng, ephemeral public key, nonce, **transcript binding**, key confirmation và kiểm tra phiên.
- Giải thích *forward secrecy*, replay protection, unknown-key-share, downgrade, key/algorithm confusion, nonce reuse, và authentication/authorization khác nhau thế nào.
- Chạy Java 21 với `KeyAgreement("X25519")`, `Signature("Ed25519")`, `Mac("HmacSHA256")` và `Cipher("AES/GCM/NoPadding")`; đọc kết quả và nhận diện chính xác giới hạn của demo.
- Xác định khi nào nên dùng **TLS 1.3, JSSE, HPKE, một giao thức đã chuẩn hóa** thay vì tự ghép primitives thành protocol mới.

## 1. Bản đồ: primitive trả lời câu hỏi nào?

| Thành phần | Ví dụ Java 21 / chuẩn | Nó cung cấp | Nó **không tự cung cấp** |
| --- | --- | --- | --- |
| Thỏa thuận khóa (key agreement) | `KeyAgreement.getInstance("X25519")`; ECDH | Hai bên có cặp khóa phù hợp tính ra một **shared secret** | Danh tính của đầu bên kia, transcript đã thương lượng, chống MITM |
| KEM (key encapsulation) | Khái niệm KEM, `javax.crypto.KEM` (API từ Java 21, phụ thuộc provider/algorithm) | Encapsulate tạo ciphertext + secret; decapsulate khôi phục secret với khóa tương ứng | Mặc định xác thực người gửi, bảo vệ toàn bộ transcript, replay/authorization |
| Bọc khóa (key wrapping) | `Cipher.WRAP_MODE/UNWRAP_MODE` với scheme được hỗ trợ; AES-KW hoặc RSA-OAEP dùng đúng mục đích | Bảo vệ một khóa được vận chuyển hoặc lưu | Xác nhận ai đề xuất chính sách, key thuộc phiên/recipient nào, toàn bộ tính đúng đắn giao thức |
| Chữ ký số | `Signature.getInstance("Ed25519")`, `RSASSA-PSS` | Một public key xác minh được một thông điệp đã được ký bằng private key tương ứng | Tin cậy rằng public key thực sự thuộc Alice/Bob; freshness nếu không ký và kiểm tra ngữ cảnh |
| MAC/HMAC | `Mac.getInstance("HmacSHA256")` | Kiểm tra integrity và nguồn gốc theo bí mật chung | Phân biệt hai người cùng biết khóa, tính mới, bí mật nội dung |
| KDF/HKDF | HKDF-Extract/Expand, HMAC-SHA256 | Chuyển input secret thành các khóa riêng theo **label/context** | Tự xác thực bên gửi hoặc sửa lỗi một shared secret đã lộ |
| AEAD | `Cipher.getInstance("AES/GCM/NoPadding")` | Bảo vệ nội dung và AAD theo secret key, IV và tag | Danh tính người gửi nếu key chưa được xác thực, chống phát lại nguyên bản mã |
| Random nonce/sequence | `SecureRandom`, bộ đếm bản ghi | Dữ liệu duy nhất/đánh số theo chính sách | Chống phát lại nếu không được bảo vệ và không có kiểm tra trạng thái |

**Điều kiện cần khác điều kiện đủ:** mã hóa có xác thực có thể chứng minh message dùng đúng **traffic key**, nhưng nếu attacker đã lừa bạn thiết lập traffic key với mình, tag AEAD hoàn toàn hợp lệ mà **peer sai**.

### 1.1 Ba lớp rất dễ bị gộp nhầm

- **Bí mật đã đồng thuận (secret agreement):** `K_A == K_B` chỉ khi hai bên tham gia đúng cuộc trao đổi khóa. Chưa có phép kiểm danh tính.
- **Xác thực peer (peer/entity authentication):** xác định đúng người sở hữu key đã được tin cậy. Signature có thể chứng minh quyền sử dụng private key **nếu public key đã được gắn với danh tính**; muốn biết peer thực sự hiện diện còn cần các bước về freshness/possession/liveness theo giao thức.
- **Xác thực message (message authentication):** dữ liệu/ciphertext không bị sửa và được tạo bởi bên nắm khóa MAC/AEAD. Đây không phải quyền thực hiện giao dịch (*authorization*) và không đồng nghĩa request chưa từng xuất hiện.

Một giao thức tốt kiểm tra **đúng peer, đúng message, đúng phiên, đúng phiên bản, đúng thời điểm và đúng quyền** trước khi gây ra tác động nghiệp vụ.

## 2. Các thành phần của một giao thức trao đổi khóa có xác thực

Một handshake thực tế có thể cần các lớp sau; không nhất thiết được triển khai bằng đúng thứ tự code ở một thư viện cụ thể.

1. **Vai trò và mục tiêu:** ai là client/server, cần xác thực một chiều hay hai chiều, cần confidentiality, forward secrecy, replay protection đến đâu?
2. **Chính sách và thương lượng:** version, nhóm key agreement/KEM, signature algorithms, AEAD, KDF, allowed extensions. Thỏa thuận phải được bảo vệ chống sửa/downgrade.
3. **Định danh và trust anchor:** chứng thư X.509 + truststore, key fingerprint được pin, hoặc public key đáng tin lấy từ registry. Phải ràng buộc danh tính với khóa đang xác minh.
4. **Ephemeral key share / encapsulation:** tạo một session secret mới theo thuật toán phù hợp. Có thể dùng (EC)DHE/X25519, KEM hoặc kết hợp theo protocol.
5. **Authentication và transcript integrity:** ký/MAC đúng transcript, bao gồm role, phiên bản, lựa chọn thuật toán, danh tính, key shares và các metadata có ý nghĩa.
6. **Key derivation + separation:** dùng KDF được thiết kế cho key material để sinh **traffic key, IV/base nonce, finished/key-confirmation key**, với label riêng cho từng hướng/bước.
7. **Key confirmation:** xác minh hai phía đang sở hữu secret/phát triển đúng key trên **cùng transcript**, thường qua Finished MAC hoặc authenticated record; chỉ cho sử dụng data khi state machine cho phép.
8. **Record protection:** AEAD với nonce/sequence không trùng dưới cùng key, AAD đầy đủ, giới hạn record, anti-replay theo thiết kế.
9. **Vòng đời phiên:** timeout, rekey, đóng phiên, khôi phục kết nối, xử lý mất gói, xác định lỗi và kiểm soát tài nguyên.
10. **Application policy:** principal, authorization, idempotency, chống phát lại lệnh nghiệp vụ; không tự cho phép giao dịch chỉ vì TLS/handshake thành công.

### 2.1 Vì sao “chạy từng API đều thành công” chưa đủ?

Giả sử một ứng dụng gọi:

```text
X25519 agreement: success
HKDF: success
AES/GCM decryption: success
```

Các lệnh này nói rằng *toán học và key có thể tương thích*, **không chứng minh** server đang nói chuyện là server mục tiêu. Nếu key share của peer bị attacker thay từ đầu, client có thể tạo secret với attacker; attacker cũng giải mã và tạo tag AES-GCM hợp lệ. Đây là lỗ hổng **giao thức**, không phải lỗi thuật toán X25519 hay AES-GCM.

## 3. Tấn công MITM khi chỉ dùng Diffie–Hellman

Alice muốn trao đổi khóa với Bob; Mallory có thể chặn, thay public key trên đường truyền.

```text
 Alice                    Mallory                       Bob
   |                         |                           |
   | --- ephemeral pk_A ---->|                           |
   |                         |---- fake pk_M2 ---------->|
   |<-- fake pk_M1 ----------|                           |
   |                         |<-------- ephemeral pk_B ---|
   |                         |                           |
   | K_A = DH(sk_A, pk_M1)   |                           |
   |                         | K_MA = DH(sk_M1, pk_A)     |
   |                         | K_MB = DH(sk_M2, pk_B)     |
   |                         |                  K_B = DH(sk_B, pk_M2)
   |                         |                           |
 K_A == K_MA                   true           K_MB == K_B
```

Alice và Bob đều có thể tin “đã bắt tay bằng X25519”. Thực tế Mallory biết **hai secret độc lập**; nếu các phía dùng chúng để mã hóa, Mallory có thể giải mã và mã hóa lại giữa hai kênh. Không cần phá mật mã, chỉ cần thay public key chưa được xác thực.

### 3.1 Demo Java 21: thuật toán đúng nhưng peer sai

Tạo file **`UnauthenticatedDhDemo.java`**:

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import javax.crypto.KeyAgreement;

public class UnauthenticatedDhDemo {
    static byte[] agree(PrivateKey mine, PublicKey peer) throws Exception {
        KeyAgreement ka = KeyAgreement.getInstance("X25519");
        ka.init(mine);
        ka.doPhase(peer, true);
        return ka.generateSecret();
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator g = KeyPairGenerator.getInstance("X25519");
        KeyPair alice = g.generateKeyPair();
        KeyPair bob = g.generateKeyPair();

        // Mallory thay public key riêng khi nói chuyện với mỗi đầu.
        KeyPair malloryToAlice = g.generateKeyPair();
        KeyPair malloryToBob = g.generateKeyPair();

        byte[] aliceSecret = agree(alice.getPrivate(),
                                   malloryToAlice.getPublic());
        byte[] malloryAlice = agree(malloryToAlice.getPrivate(),
                                    alice.getPublic());
        byte[] bobSecret = agree(bob.getPrivate(),
                                 malloryToBob.getPublic());
        byte[] malloryBob = agree(malloryToBob.getPrivate(),
                                  bob.getPublic());

        System.out.println("Alice shares with Mallory: " +
                MessageDigest.isEqual(aliceSecret, malloryAlice));
        System.out.println("Bob shares with Mallory: " +
                MessageDigest.isEqual(bobSecret, malloryBob));
    }
}
```

Biên dịch/chạy với JDK 21:

```text
javac --release 21 -encoding UTF-8 UnauthenticatedDhDemo.java
java UnauthenticatedDhDemo
```

Stdout:

```text
Alice shares with Mallory: true
Bob shares with Mallory: true
```

**Giải thích:** X25519 không sai: mỗi phía đã chia sẻ secret với **đúng public key mà nó nhận**. Sai lầm nằm ở chỗ Alice/Bob **không biết public key nhận được thuộc ai**. Code không triển khai TCP hay sửa gói trên mạng; nó mô phỏng việc attacker thay key ngay tại ranh giới nhận. Thử `MessageDigest.isEqual` chỉ kiểm tra hai byte array giống nhau, không kiểm danh tính. Demo không quản lý bộ nhớ secret để giữ ví dụ ngắn; production cần chính sách lifecycle key/secret nghiêm ngặt.

## 4. Xác thực exchange: tin đúng khóa trước khi tin vào chữ ký

Một cách giáo dục để ngăn thay key là mỗi phía có một **identity signing key** đã được phân phối tin cậy trước đó, và ký dữ liệu bắt tay bao gồm ephemeral public key.

```text
Alice có skA_sign, pkA_sign đã được Bob tin cậy
Bob   có skB_sign, pkB_sign đã được Alice tin cậy

ClientOffer = version, suite, role=client, id=Alice, nonceA, ephemeralPubA
sigA = Sign(skA_sign, Encode(ClientOffer))

ServerOffer = version, suite, role=server, id=Bob, nonceB, ephemeralPubB
sigB = Sign(skB_sign, Encode(ServerOffer))

Alice xác minh sigB với pkB_sign ĐÁNG TIN và expected id=Bob
Bob   xác minh sigA với pkA_sign ĐÁNG TIN và expected id=Alice
Cả hai xác nhận một transcript có thứ tự và bind shared secret vào transcript
```

**Nếu Mallory thay ephemeral public key mà giữ signature cũ, `verify` thất bại.** Mallory cũng không thể tự ký một offer mới dưới danh tính Bob nếu không có private key của Bob và Bob’s public key tin cậy được Alice kiểm đúng.

### 4.1 Xác thực khóa khác xác thực danh tính

Một public key được gửi kèm chữ ký tự tạo bởi key đó **chưa đủ**: kẻ tấn công có thể tạo cặp khóa của mình, tự ký và tự nhận là Bob. Client phải có **trust anchor** như certificate chain đúng policy/hostname, certificate pin hợp lệ, hoặc key registry đáng tin. Kiểm tra `Signature.verify() == true` chỉ chứng minh *private key tương ứng với public key đã đưa vào bộ kiểm* tạo ra chữ ký, **không chứng minh khóa thuộc Bob nếu chưa xác thực nguồn**.

**Dữ liệu cần được ký/bind:** protocol version, role, identity hoặc subject, key/algorithm identifiers, ephemeral key share, nonce, lựa chọn thuật toán, mục tiêu/audience. Nếu chỉ ký public key mà không ký **vai trò và phiên bản**, attacker có thể gây *role confusion*, *downgrade* hoặc phát lại dữ liệu giữa những giao thức gần giống.

### 4.2 Vì sao ràng buộc transcript?

**Transcript** là toàn bộ chuỗi handshake messages theo thứ tự và encoding đã định, gồm các trường an ninh có ý nghĩa. Một transcript hash như `SHA-256(Encode(clientOffer) || Encode(serverOffer) || ...)` được đưa vào key schedule hoặc chữ ký/MAC giúp hai phía phát hiện nếu chúng không nhất trí:

- ai là client/server và danh tính mong đợi;
- đã thương lượng thuật toán, version, extension nào;
- đã nhận những ephemeral public keys, nonces và context nào;
- session này dành cho **dịch vụ, tenant, ứng dụng, tài nguyên** nào (theo protocol);
- có thông điệp bị thêm, bỏ, sắp xếp lại hoặc tráo ngữ cảnh hay không.

Không nên ghép text tùy ý: `"A" + "BC"` và `"AB" + "C"` cho kết quả trùng. Hãy dùng length-prefix, encoding nhị phân đã công bố, hoặc canonical serialization được kiểm thử. Ở giao thức chuẩn, **transcript construction là một phần đặc tả**, không tự chọn tùy tiện.

### 4.3 HKDF dùng shared secret trong đúng bối cảnh

Với X25519, `generateSecret()` cung cấp byte secret (input key material – IKM). Thường dùng HKDF:

```text
PRK = HKDF-Extract(salt, X25519_secret)
K_c2s = HKDF-Expand(PRK, label(client-to-server) || context, 32)
K_s2c = HKDF-Expand(PRK, label(server-to-client) || context, 32)
K_finished = HKDF-Expand(PRK, label(key-confirmation) || context, 32)
```

HKDF chuẩn hóa trong [RFC 5869](https://www.rfc-editor.org/rfc/rfc5869). `salt` và `info/context` được dùng đúng mục đích theo thiết kế; **không dùng bytes shared secret trực tiếp làm khóa AES chỉ vì có đúng độ dài**, cũng không lấy SHA-256 ngẫu nhiên không có phân tách mục đích để tạo mọi loại key. Labels/context của từng hướng giúp tránh dùng cùng key cho các kênh hoặc nhiệm vụ khác nhau.

Dùng transcript hash làm input công khai trong key schedule giúp **key binding** với cuộc bắt tay. Đừng nhầm nó với kiểm tra chữ ký: nếu không có identity authentication, một attacker đang tham gia exchange vẫn có thể tính cùng secret và transcript với endpoint. **HKDF không thay thế chữ ký hoặc một phương thức peer authentication chuẩn.**

## 5. Bài thực hành Java 21: minh họa *các* lớp phối hợp

Chương trình tiếp theo dùng:

- **Ed25519 identity key pairs** được tạo trước và giả định public keys đã được trao tin cậy ngoài băng (demo giữ cùng process để dễ kiểm tra).
- **X25519 ephemeral key pairs** dùng để tạo shared secret tạm thời. Bên nhận xác minh chữ ký trên offer, role/id, suite/nonce trước khi đồng ý sử dụng key share.
- **Length-prefix encoding** của các trường handshake để tránh nhập nhằng; `SHA-256` transcript trong một thứ tự cố định.
- **HKDF-HMAC-SHA256** ở mức **một khối Expand 32 byte** cho **một khóa AES-256 duy nhất hướng client→server**, đủ cho một tin nhắn demo.
- **AES-GCM** với IV/nonce ngẫu nhiên 12 byte mới và transcript hash làm AAD. Thay AAD khiến tag kiểm tra thất bại.

Đây là **thí nghiệm minh họa các mối nối giữa primitives**. Chưa phải giao thức để triển khai production: thiếu network framing/parser, certificate-chain verification, finished/key-confirmation **hai chiều**, replay cache, session state, sequence/counter cho nhiều record, quản lý thời gian/rotate/rekey, xử lý đồng thời, secret erasure bảo đảm toàn diện, state machine chống downgrade và nhiều tiêu chí chuẩn khác. Để xây dựng kênh thực tế, dùng TLS 1.3/JSSE hoặc protocol được chuẩn hóa, đánh giá.

Tạo file **`AuthenticatedChannelDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class AuthenticatedChannelDemo {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String SUITE =
            "demo-v1:X25519:Ed25519:HKDF-SHA256:AES-256-GCM";

    record Offer(String role, String identity, byte[] nonce,
                 byte[] publicKey, byte[] signature) {}

    static void put(DataOutputStream out, byte[] bytes) throws Exception {
        out.writeInt(bytes.length);
        out.write(bytes);
    }
    static void put(DataOutputStream out, String string) throws Exception {
        put(out, string.getBytes(StandardCharsets.UTF_8));
    }

    static byte[] offerBytes(Offer offer) throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(buffer);
        put(out, SUITE);
        put(out, offer.role());
        put(out, offer.identity());
        put(out, offer.nonce());
        put(out, offer.publicKey());
        out.flush();
        return buffer.toByteArray();
    }

    static Offer createOffer(String role, String identity,
                             PublicKey ephemeral, PrivateKey signingKey)
            throws Exception {
        byte[] nonce = new byte[32];
        RANDOM.nextBytes(nonce);
        Offer unsigned = new Offer(role, identity, nonce,
                                   ephemeral.getEncoded(), new byte[0]);
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(signingKey);
        signer.update(offerBytes(unsigned));
        return new Offer(role, identity, nonce,
                         unsigned.publicKey(), signer.sign());
    }

    static boolean verifyOffer(Offer offer, String requiredRole,
                               String requiredIdentity, PublicKey trustedKey)
            throws Exception {
        if (!requiredRole.equals(offer.role())
                || !requiredIdentity.equals(offer.identity())
                || offer.nonce().length != 32) {
            return false;
        }
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(trustedKey);
        verifier.update(offerBytes(offer));
        return verifier.verify(offer.signature());
    }

    static byte[] transcriptHash(Offer client, Offer server)
            throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(buffer);
        put(out, "handshake-transcript-v1");
        put(out, offerBytes(client));
        put(out, client.signature());
        put(out, offerBytes(server));
        put(out, server.signature());
        return MessageDigest.getInstance("SHA-256")
                .digest(buffer.toByteArray());
    }

    static byte[] agree(PrivateKey mine, byte[] peerPublicKey)
            throws Exception {
        PublicKey other = KeyFactory.getInstance("X25519")
                .generatePublic(new X509EncodedKeySpec(peerPublicKey));
        KeyAgreement agreement = KeyAgreement.getInstance("X25519");
        agreement.init(mine);
        agreement.doPhase(other, true);
        return agreement.generateSecret();
    }

    // HKDF-Extract, then one-block HKDF-Expand for a 32-byte AES key.
    static byte[] channelKey(byte[] shared, byte[] context)
            throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(context, "HmacSHA256"));
        byte[] prk = mac.doFinal(shared);
        try {
            mac.init(new SecretKeySpec(prk, "HmacSHA256"));
            mac.update("client-to-server AES key v1".getBytes(
                    StandardCharsets.UTF_8));
            mac.update((byte) 1);
            return mac.doFinal();
        } finally {
            Arrays.fill(prk, (byte) 0);
        }
    }

    static byte[] seal(byte[] key, byte[] aad, byte[] iv, byte[] plain)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(key, "AES"),
                    new GCMParameterSpec(128, iv));
        cipher.updateAAD(aad);
        return cipher.doFinal(plain);
    }

    static byte[] open(byte[] key, byte[] aad, byte[] iv, byte[] encrypted)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(key, "AES"),
                    new GCMParameterSpec(128, iv));
        cipher.updateAAD(aad);
        return cipher.doFinal(encrypted);
    }

    public static void main(String[] args) throws Exception {
        // The trusted identity public keys were provisioned beforehand.
        KeyPairGenerator identityGenerator =
                KeyPairGenerator.getInstance("Ed25519");
        KeyPair clientIdentity = identityGenerator.generateKeyPair();
        KeyPair serverIdentity = identityGenerator.generateKeyPair();

        KeyPairGenerator ephemeralGenerator =
                KeyPairGenerator.getInstance("X25519");
        KeyPair clientEphemeral = ephemeralGenerator.generateKeyPair();
        KeyPair serverEphemeral = ephemeralGenerator.generateKeyPair();

        Offer client = createOffer("client", "Alice",
                clientEphemeral.getPublic(), clientIdentity.getPrivate());
        Offer server = createOffer("server", "Bob",
                serverEphemeral.getPublic(), serverIdentity.getPrivate());

        boolean clientAuthenticated = verifyOffer(client, "client", "Alice",
                clientIdentity.getPublic());
        boolean serverAuthenticated = verifyOffer(server, "server", "Bob",
                serverIdentity.getPublic());
        System.out.println("trusted client offer: " + clientAuthenticated);
        System.out.println("trusted server offer: " + serverAuthenticated);

        byte[] replaced = client.publicKey().clone();
        replaced[replaced.length - 1] ^= 1;
        Offer tampered = new Offer(client.role(), client.identity(),
                client.nonce(), replaced, client.signature());
        System.out.println("substituted key accepted: " +
                verifyOffer(tampered, "client", "Alice",
                            clientIdentity.getPublic()));

        if (!clientAuthenticated || !serverAuthenticated) {
            throw new SecurityException("Untrusted handshake");
        }

        byte[] context = transcriptHash(client, server);
        byte[] leftShared = agree(clientEphemeral.getPrivate(),
                                  server.publicKey());
        byte[] rightShared = agree(serverEphemeral.getPrivate(),
                                   client.publicKey());
        byte[] leftKey = channelKey(leftShared, context);
        byte[] rightKey = channelKey(rightShared, context);
        System.out.println("derived keys match: " +
                MessageDigest.isEqual(leftKey, rightKey));

        byte[] iv = new byte[12];
        RANDOM.nextBytes(iv);
        byte[] plaintext = "hello Bob".getBytes(StandardCharsets.UTF_8);
        byte[] ciphertext = seal(leftKey, context, iv, plaintext);
        byte[] opened = open(rightKey, context, iv, ciphertext);
        System.out.println("authenticated message: " +
                new String(opened, StandardCharsets.UTF_8));

        byte[] wrongContext = context.clone();
        wrongContext[0] ^= 1;
        boolean rejected = false;
        try {
            open(rightKey, wrongContext, iv, ciphertext);
        } catch (AEADBadTagException expected) {
            rejected = true;
        }
        System.out.println("changed transcript rejected: " + rejected);

        Arrays.fill(leftShared, (byte) 0);
        Arrays.fill(rightShared, (byte) 0);
        Arrays.fill(leftKey, (byte) 0);
        Arrays.fill(rightKey, (byte) 0);
    }
}
```

Biên dịch và chạy với **JDK 21** (hoặc JDK mới hơn có hỗ trợ `--release 21`):

```text
javac -version
javac --release 21 -encoding UTF-8 AuthenticatedChannelDemo.java
java AuthenticatedChannelDemo
```

Stdout mong đợi (các key và nonce được sinh ngẫu nhiên, không in ra):

```text
trusted client offer: true
trusted server offer: true
substituted key accepted: false
derived keys match: true
authenticated message: hello Bob
changed transcript rejected: true
```

### 5.1 Phân tích từng kết quả

- **Trusted offers:** hai bên giả định đã có **đúng identity public keys** của nhau từ kênh đáng tin; signatures kiểm tra chính xác các bytes offer có role/id/suite/nonce/key share.
- **Substituted key rejected:** đổi một byte public key nhưng giữ signature cũ khiến phép xác minh thất bại; attacker không thể tùy tiện thay exchange key mà không có signing private key.
- **Derived keys match:** `KeyAgreement` tạo shared secret tương thích; HKDF-Extract dùng transcript hash làm public salt, HKDF-Expand một block gồm `info || 0x01` để tạo 32 byte c2s key. Đây là cách dùng **một block của RFC 5869**, không phải implementation HKDF tổng quát cho nhiều block/độ dài.
- **Authenticated message:** AES-GCM dùng **cùng derived key, IV và AAD (transcript hash)** ở hai phía để kiểm tra tag và mở plaintext. Nếu chỉ đo lường kết quả này mà bỏ trust of identity, MITM vẫn có thể tạo kênh hợp lệ với chính attacker.
- **Changed transcript rejected:** đổi AAD nhưng giữ ciphertext/tag làm `AEADBadTagException`. Điều đó minh họa dữ liệu bối cảnh đã được xác thực ở tầng record; nó **không thay** việc xác minh signature/peer trust.

**Giới hạn quan trọng:** demo không chứng minh có một *handshake Finished* qua lại. Kết quả `derived keys match: true` được so trong cùng process, không phải giao thức key confirmation trên mạng. Một hệ thống thật cần mỗi bên gửi và xác minh bằng chứng possession of derived handshake key theo đúng state machine, trước khi tin phiên đã hoàn tất.

### 5.2 Chi tiết liên quan Java và encoding

- `KeyPairGenerator.getInstance("X25519")` và `KeyAgreement.getInstance("X25519")` thực hiện key agreement; `Ed25519` thuộc nhóm ký số, dùng `Signature`. Không đổi `Ed25519` thành `X25519` rồi dùng để ký.
- `ephemeral.getEncoded()` trong ví dụ trả X.509/SubjectPublicKeyInfo encoding của public key; `KeyFactory` phục hồi public key từ `X509EncodedKeySpec`. Đây là **định dạng khóa**, không phải chứng thư X.509 đã được tin cậy.
- `DataOutputStream.writeInt(length)` giúp phân biệt ranh giới các trường. Production phải đặt giới hạn tối đa độ dài, parser chống dữ liệu lỗi, canonical encoding, kiểm tra thuật toán/key type và xử lý mạng an toàn.
- `Signature.verify()` kiểm tra signature với **public key đã biết trước**. Nếu thay trusted public key bằng key do request đưa lên chưa kiểm tra, bài học về MITM quay lại.
- `new SecretKeySpec(context, "HmacSHA256")` dùng transcript hash công khai làm HKDF-Extract salt; secret thật vẫn là `shared`. Với salt không bí mật, HKDF không dựa vào việc che giấu transcript.
- Demo sinh một IV 12 byte cho **một** bản tin. Hệ thống nhiều record cần nonce/counter duy nhất theo key, key/nonce per direction, giới hạn lượng dữ liệu và rotation. Tuyệt đối tránh dùng lại IV AES-GCM với cùng key.
- `Arrays.fill` dọn những mảng byte do ứng dụng sở hữu ở cuối demo. Java provider/JVM có thể tạo bản sao trong bộ nhớ; đây không phải cam kết xóa mọi dấu vết của secret.

## 6. KEM, bọc khóa và thỏa thuận khóa đứng ở đâu trong giao thức?

“Thỏa thuận khóa” và “bọc khóa” đều giúp các bên có key material, nhưng **cấu trúc và giả định khác nhau**.

| Cơ chế | Người gửi thực hiện | Người nhận thực hiện | Thu được |
| --- | --- | --- | --- |
| X25519/ECDH | Dùng private key của mình và public key peer để tính secret | Làm tương tự theo vai trò đối xứng | Shared secret nếu các public keys đúng cặp |
| KEM | `Encapsulate(pk_receiver)` sinh ciphertext KEM và secret | `Decapsulate(sk_receiver, kemCiphertext)` lấy lại secret | Cùng shared secret; chưa tự xác thực sender |
| RSA-OAEP key transport | Mã hóa/wrap một secret hoặc key phiên bằng public key người nhận | Giải mã/unwrap bằng private key người nhận | Key material truyền đến người nhận |
| AES-KW (symmetric key wrap) | Wrap một key bằng **key-encryption key** đã chia sẻ | Unwrap bằng cùng KEK | Key được bảo vệ khi lưu/chuyển, nhưng chính KEK vẫn phải có nguồn đáng tin |
| HKDF | Từ shared secret, transcript/context và labels dẫn xuất các traffic keys | Tính tương ứng với input/context giống nhau | Key phân biệt theo chức năng và hướng |

### 6.1 KEM không tự xác thực danh tính người gửi

Một KEM public-key base mode hướng vào khóa của Bob có thể giữ bí mật encapsulated secret với Bob; **bất kỳ ai** có public key Bob phù hợp cũng có thể encapsulate để gửi Bob. Nếu ứng dụng cần biết sender là Alice, phải có authentication/mode được thiết kế đúng, xác thực public key Bob, transcript/associated data và quản lý giao thức.

**Java 21:** có API `javax.crypto.KEM` (được đưa vào từ Java 21), nhưng loại KEM và provider được hỗ trợ phải được xác minh theo JDK/runtime. Không nhầm sự hiện diện của **lớp KEM** với việc một thuật toán KEM cụ thể **được cài đặt và sẵn dùng**. Đọc tài liệu Java 21 và provider trước khi chọn tên thuật toán.

### 6.2 Key wrapping giải quyết bước vận chuyển/lưu khóa

`Cipher.WRAP_MODE`/`UNWRAP_MODE` là một cách dùng API ở Java; thuật toán wrap cụ thể quyết định định dạng ciphertext, tính toàn vẹn và ràng buộc key. Ví dụ:

```text
Sender: sessionKey = SecureRandom(...)
        wrapped = Wrap(KEK_or_pkRecipient, sessionKey)
        send wrapped + algorithmId + associated metadata

Receiver: sessionKey = Unwrap(keyRecipient, wrapped)
          use sessionKey for records under agreed policy
```

Đây là **pseudocode**, không phải lời mời tự thiết kế định dạng wrap. “Unwrap trả về một SecretKey” không chứng minh sender được phép gửi, key dành cho phiên/ứng dụng này, thuật toán không bị hạ cấp hoặc key chưa từng được replay. Bảo vệ metadata và identity bằng protocol binding hoặc container chuẩn.

Phân biệt **RSA-OAEP bọc secret**, **AES Key Wrap bọc key bằng KEK**, và **AES-GCM mã hóa dữ liệu**: mỗi primitive có giới hạn input, requirement nonce/IV và cách kiểm tra riêng. Đừng dùng raw RSA, đừng tự ghép IV/key/ciphertext không có format được định nghĩa, và đừng dùng bytes secret từ key exchange ở nhiều mục đích mà không qua KDF/key separation.

### 6.3 Vì sao cần hybrid encryption cho dữ liệu lớn?

RSA-OAEP/KEM thường chỉ dùng để truyền hoặc thiết lập **key material**. Một mô hình hybrid:

```text
Shared key or KEM secret → HKDF(context, labels) → traffic key
                                                    |
Plaintext ---------------------------------------> AEAD encrypt
                                                    |
send: key encapsulation/wrapped key + nonce + ciphertext + tag
```

AEAD có thể mã hóa lượng dữ liệu lớn theo giới hạn scheme/nonce/key và policy. Nhưng **hybrid encryption tự nó chưa chắc có sender authentication, replay protection và context binding**. Ví dụ HPKE (RFC 9180) quy định các mode và KDF/AEAD; base mode không xác thực danh tính sender, authenticated mode có giả định khóa và mức bảo vệ riêng. Đọc profile/giao thức để biết phải kiểm tra danh tính và phép gán quyền như thế nào.

## 7. Key confirmation: cùng secret chưa chứng minh cùng một phiên

Để một bên kết luận đối phương **sở hữu khóa vừa dẫn xuất** và chấp nhận đúng transcript, giao thức thường dùng một bước MAC trên transcript hoặc một authenticated handshake record. Ví dụ khái niệm:

```text
clientFinished = HMAC(K_finished_c, transcriptHash)
serverFinished = HMAC(K_finished_s, transcriptHash)

client xác minh serverFinished với key phía server
server xác minh clientFinished với key phía client
chỉ khi hợp lệ mới chuyển state → ESTABLISHED
```

Đây là **sơ đồ**, không phải bản sao chính xác của TLS. Quan trọng là hai hướng phải có labels/keys khác nhau, transcript đúng ranh giới state, và fail-closed khi MAC mismatch. Không dùng “server giải mã được một message bất kỳ” như bằng chứng danh tính nếu traffic key chưa được xác thực từ trước.

### 7.1 TLS 1.3 thực hiện những lớp gì?

Theo [RFC 8446](https://www.rfc-editor.org/rfc/rfc8446), TLS 1.3 có khung giao thức rõ cho phiên bản, key exchange, certificate-based hoặc PSK authentication, transcript hash, HKDF key schedule và **Finished**. Khi xác thực bằng certificate, `CertificateVerify` ký nội dung ràng buộc với transcript; `Finished` MAC nội dung transcript theo khóa bắt tay. Key/nonce và record AEAD được quản lý theo state và direction; lỗi authentication chấm dứt handshake.

**Không đồng nhất demo Java với TLS 1.3.** Một protocol đạt chuẩn còn xử lý certificate path/hostname, algorithms/suites, resumption/PSK, 0-RTT replay caveats, alerts, key update, framing, handshake ordering và nhiều yêu cầu kiểm thử. Nếu chương trình Java cần kết nối TLS, hãy ưu tiên **JSSE** (`SSLContext`, `SSLSocket`/`SSLEngine`, HTTPS client/server) với cấu hình xác thực/tin cậy đúng thay vì xây một TLS giản lược bằng `KeyAgreement` + `Cipher`.

### 7.2 TLS server authentication và client authentication

HTTPS thường xác thực **server** qua certificate/hostname, còn **client** có thể được xác thực ở tầng ứng dụng (OAuth/session/token) hoặc bằng mutual TLS tùy hệ thống. Một handshake “xác thực” không có nghĩa bắt buộc hai đầu đều dùng certificate.

Trong thiết kế, ghi rõ **ai tin ai** và **xác thực chiều nào**. Nếu Bob không cần xác thực Alice bằng certificate, protocol phải quy định cơ chế client identity khác và cách gắn nó với channel/transaction. Đừng tự gán rằng có TLS là mọi request từ Alice đã được phép chuyển tiền.

## 8. Những thuộc tính không thể suy ra từ một primitive

### 8.1 Forward secrecy

Nếu sử dụng ephemeral (EC)DH và xóa bí mật phiên đúng cách, việc private key danh tính bị lộ **về sau** có thể không làm lộ secret của các phiên đã kết thúc (*forward secrecy*, với điều kiện threat model và thiết kế đúng). Trái lại, key transport RSA lưu traffic secret được mã hóa dưới một RSA private key lâu dài có thể khiến các ciphertext cũ bị giải nếu private key đó bị lộ trong tương lai.

**Không tự tuyên bố forward secrecy** chỉ vì tên thuật toán là X25519. Phải xác minh ephemeral key mới cho phiên, không tái sử dụng trái thiết kế, secret được xóa đúng lúc, KDF và protocol binding, và rằng metadata/log/backup không lưu lại secret phiên.

### 8.2 Chống replay và freshness

Signature, MAC và AEAD vẫn hợp lệ với message/ciphertext cũ được gửi lại nguyên vẹn. Nếu server nhận một yêu cầu “thanh toán 100” hai lần, có thể thực thi nghiệp vụ hai lần mặc dù tag hoàn toàn hợp lệ. Giao thức cần nonce/sequence number, timestamp/expiration, **replay state** hoặc chống phát lại thích hợp; tầng nghiệp vụ vẫn cần **idempotency key** cho retry.

Với giao thức stream, sequence number và key epoch thường đi cùng record protection. Với API độc lập, signed nonce + store có TTL hợp lý/atomic insert có thể cần thiết. Đừng tự dùng timestamp mà không kiểm tra trùng request trong cùng cửa sổ.

### 8.3 Unknown-key-share / identity misbinding

Trong *unknown-key-share* (UKS), hai bên có thể tính cùng secret nhưng ít nhất một bên **hiểu sai danh tính của người bên kia**. Đây không đơn thuần là byte secret bị lộ; lỗi do message/identity/context không được bind rõ. Bảo đảm rằng key schedule, signatures/MAC và xác minh public key đều ràng buộc với **role, local peer identity, intended recipient, phiên bản và context phù hợp**.

### 8.4 Downgrade và algorithm confusion

Nếu attacker có thể sửa trường “supported versions” hoặc “selected suite” mà các trường đó không được transcript-authenticated, hai bên có thể bị hạ xuống một thuật toán yếu hơn hoặc bất đồng thuật toán. Luôn có **allowlist** và chính sách tối thiểu; kiểm tra negotiation transcript, không đọc thuật toán do request tự khai rồi dùng tùy ý.

Không dùng cùng key cho nhiều schemes hoặc roles không có phân tách miền; không đổi hướng client→server thành server→client dưới cùng key/counter. Các hàm `Signature`/`Cipher` có thể nhận tham số hợp lệ riêng lẻ nhưng một **cấu hình giao thức** vẫn sai.

### 8.5 AEAD nonce và bản ghi

AES-GCM cần IV/nonce **không bị tái sử dụng với cùng khóa**. Nếu record direction dùng một key chung cho nhiều thông điệp mà hai node cùng chọn nonce trùng, confidentiality/integrity có thể bị phá. Đặc tả phải nêu cách tính nonce từ sequence/epoch, key update, giới hạn lượng record, cơ chế tránh overlap khi concurrent workers và hành vi khi counter cạn.

`AAD` dùng để xác thực metadata không cần mã hóa như version, stream ID, sequence, header. Cả encrypt/decrypt phải đưa **chính xác cùng bytes AAD** vào phép kiểm; metadata nào bị thay mà không nằm trong AAD/tag có thể gây routing/context confusion.

### 8.6 Lỗi, parse và tài nguyên

Không để attacker ép server cấp phát mảng khổng lồ, thực hiện hàng loạt phép ký/giải mã đắt tiền, hoặc rò rỉ khác biệt lỗi cho oracle. Bắt giới hạn kích thước record/trường/chain, timeouts, số handshake đồng thời và rate limit. Trong code Java, xử lý `GeneralSecurityException` có phân loại nội bộ nhưng không phản hồi chi tiết khóa, padding, tag hay certificate cho người gọi bên ngoài.

Nếu bắt tay thất bại ở bất cứ bước authentication, **không khởi tạo session thành công** và không thực hiện side effects. Lỗi phải kết thúc/rollback trạng thái theo quy tắc protocol.

## 9. Kiến trúc thực tế: phân tách primitive, handshake và ứng dụng

Một mô hình các lớp:

```text
Trusted identity / certificate / key registry
                |
                v
ClientHello / ServerHello --version, role, suite, key shares, nonces-->
                |
                v
Handshake transcript + signature / PSK authentication / Finished MAC
                |
                v
X25519 or KEM secret ----- HKDF(context/role/direction) ----+
                                                            |
                         +----------------------------------+
                         |
                    traffic keys + base nonces
                         |
                         v
             AEAD protected records + sequence/epoch
                         |
                         v
      Application identity + authorization + replay/idempotency
```

| Lớp | Điều ứng dụng cần kiểm tra | Lỗi nếu bỏ qua |
| --- | --- | --- |
| Trust/identity | Public key/certificate thực sự của peer mong đợi | MITM dùng khóa giả rồi vẫn ký hợp lệ |
| Handshake negotiation | Version, suite, roles và policy trong transcript đã xác thực | Downgrade, role confusion |
| Key establishment | Shared secret đúng peer, ephemeral và KDF tách mục đích | Key substitution, key reuse, không có forward secrecy kỳ vọng |
| Key confirmation | Cả hai phía kiểm tra kết quả handshake/secret | Chấp nhận phiên chưa hoàn tất hoặc khác transcript |
| Record AEAD | Nonce không trùng, đúng key/direction/AAD/sequence | Lộ dữ liệu, sửa record hoặc phát lại |
| Application | Identity, quyền, request ID, idempotency, audit | Kênh an toàn nhưng cho phép giao dịch sai |

### 9.1 Giao thức bảo mật và nghiệp vụ không cùng phạm vi

Ví dụ một client dùng TLS 1.3 đến server hợp lệ, kênh đã được mã hóa và certificate đúng. Vẫn cần kiểm tra user có được phép thao tác `POST /transfer` hay không; user ID có thể đến từ access token/session, không tự suy ra từ việc kết nối TLS thành công. Một request hợp lệ được retry qua kết nối TLS **mới** cũng có thể làm trùng nghiệp vụ nếu thiếu idempotency.

Đó là lý do review kiến trúc cần câu hỏi: “Giao thức nào bảo vệ **bytes trên kênh**, cơ chế nào xác định **principal**, và thành phần nào quyết định **quyền và tính duy nhất của transaction**?”

## 10. Lựa chọn giải pháp theo mục đích

| Nhu cầu | Lựa chọn thường phù hợp | Điều vẫn phải xác minh |
| --- | --- | --- |
| HTTPS giữa Java service và server | TLS 1.3 qua JSSE/HTTPS stack được cập nhật | Hostname verification, truststore, ALPN/versions/suite policy, client auth nếu cần |
| Java service nội bộ mTLS | TLS 1.3 + certificate client/server | Trust anchors, danh tính workload, policy key rotation/revocation, authorization |
| Mã hóa dữ liệu gửi cho recipient, không duy trì kết nối | Chuẩn hybrid encryption / HPKE profile phù hợp | Recipient public key đáng tin, sender authentication mode, context/AAD, replay |
| Bọc một data-encryption key trong hệ thống KMS | KMS/HSM wrap/unwrap hoặc AES-KW theo chuẩn | Key ID, quyền unwrap, tenant/context binding, rotation, metadata integrity |
| Thiết kế một protocol tùy biến | Bắt đầu từ đặc tả đã review/chuẩn hóa và threat model | State machine, crypto review, vectors, fuzzing, interop, rollback/replay/error paths |
| Chỉ cần học cơ chế | Ví dụ Java 21 trong bài | Chỉ kết luận giới hạn mà demo thật sự kiểm chứng |

**Quy tắc thực dụng:** nếu cần kênh bảo mật thật, sử dụng protocol và thư viện đã được triển khai, kiểm thử, cập nhật. Học các primitives giúp bạn **cấu hình đúng, nhận ra sai kiến trúc và đọc đặc tả**, không có nghĩa bạn nên tự viết handshake thay TLS.

## 11. Checklist kiểm tra một protocol có xác thực

| Thử nghiệm / câu hỏi review | Hành vi phải thấy |
| --- | --- |
| Thay ephemeral public key khi giữ signature cũ | Peer authentication thất bại trước khi gửi traffic |
| Thay public key identity bằng key của attacker | Trust/certificate/pinning từ chối |
| Thay client/server role hoặc peer ID | Signature/transcript authentication thất bại |
| Hạ version, thay cipher suite, bỏ extension cần thiết | Transcript mismatch hoặc policy reject |
| Dùng cùng shared secret dưới hai ngữ cảnh khác | Key derivation có labels/context thích hợp, không trùng key ngoài ý muốn |
| Một bên nhận transcript khác bên kia | Finished/key confirmation không hợp lệ |
| Gửi message record với AAD sai | AEAD tag reject; không chuyển plaintext cho ứng dụng |
| Replay một bản ghi/mệnh lệnh | Sequence/replay/idempotency state chặn hiệu ứng trùng theo chính sách |
| Reset nonce/counter khi reconnect/rotate | Epoch và key schedule ngăn nonce reuse |
| Lộ lâu dài signing private key sau phiên đã đóng | Đánh giá forward secrecy của phiên trước; phải có ephemeral secret lifecycle đúng |
| Gửi input rất lớn / keyShare sai loại / ciphertext lỗi | Parse giới hạn, fail-closed, không tạo oracle hoặc DoS dễ khai thác |
| Khóa certificate dùng sai mục đích hoặc hết hạn | Trust/policy/usage validation reject |
| Server đã xác thực nhưng client thiếu quyền | Application authorization từ chối thao tác |

### 11.1 Các sai lầm phổ biến

1. **“Hai shared secret bằng nhau = đã xác thực peer.”** Sai: DH chỉ biết key math; MITM có thể tạo hai shared secrets riêng.
2. **“Đã mã hóa AES-GCM là không bị MITM.”** Sai nếu session key được thiết lập với attacker; AEAD tag chỉ có ý nghĩa theo key đã tin.
3. **“KEM hoặc RSA-OAEP chứng minh sender.”** Sai với base public-key recipient encryption/encapsulation: ai có recipient public key đều gửi được.
4. **“Đã ký ephemeral key là đủ.”** Chưa đủ nếu public signing key không đáng tin, không bind đúng role/negotiation/identity, hoặc chưa hoàn tất key confirmation.
5. **“HKDF tự xác thực danh tính.”** Sai: KDF nhận key material và context, không biết public key thuộc ai.
6. **“Dùng cùng một traffic key cho mọi hướng vì đã có nonce.”** Dễ sai về separation/nonce collision; giao thức cần phân tách key và counter rõ.
7. **“Wrapped key đã an toàn là packet hoàn chỉnh.”** Metadata, key ID, quyền unwrap, nonce/record và chống phát lại vẫn cần được bảo vệ.
8. **“Chữ ký/AEAD hợp lệ nghĩa là gói mới.”** Replay nguyên gói không thay đổi bytes/tag.
9. **“X.509EncodedKeySpec là certificate được CA ký.”** Sai: đó là định dạng encode public key, không chứng minh danh tính.
10. **“Một chương trình lab mô phỏng 2 endpoint trong cùng JVM đủ chứng minh protocol production.”** Sai: demo thiếu state, network adversary, trust lifecycle và kiểm thử liên thông.

## 12. Bài tập củng cố

1. **Phân tích MITM:** vẽ lại đường đi của `pk_A`, `pk_B` và hai public keys Mallory. Giải thích vì sao Alice và Bob đều có thể gọi `KeyAgreement.generateSecret()` thành công dù không chia sẻ secret với nhau.
2. **Chữ ký:** chạy `UnauthenticatedDhDemo` rồi `AuthenticatedChannelDemo`. Cho biết ở bước nào một key share bị thay bị từ chối, và public key nào phải được tin trước khi kiểm chữ ký.
3. **Transcript:** nếu client ký `pkA` mà bỏ `suite`, attacker có thể khai thác sự thiếu ràng buộc nào? Nếu đổi AAD thành một byte khác, AES-GCM biểu hiện ra sao?
4. **HKDF:** giải thích khác biệt giữa `shared`, `PRK` và `traffic key`; vì sao cần hai labels `client-to-server` và `server-to-client`? Vì sao implementation one-block trong demo chưa phải HKDF tổng quát?
5. **Key wrapping:** mô tả một DEK được bọc bằng RSA-OAEP, AES-KW hoặc KMS key. Nêu chính xác nơi thực hiện authorization, xác minh recipient và bảo vệ metadata.
6. **Key confirmation:** thiết kế *bằng lời* một finished exchange hai chiều có MAC trên transcript, không viết protocol production. Nếu một bên không kiểm MAC phía còn lại thì thuộc tính nào còn thiếu?
7. **Replay:** một thanh toán đã xác thực được gửi lại y hệt qua TLS mới. Vì sao TLS đúng certificate không đủ để tránh charge hai lần? Nêu replay cache/idempotency cần thiết.
8. **Forward secrecy:** so sánh ephemeral X25519 và key transport chỉ dựa private key giải mã dài hạn; điều kiện nào phải đúng để một khóa bị lộ về sau không tiết lộ dữ liệu cũ?
9. **Threat model:** viết danh sách attacker có thể sửa/cắt/delay/reorder những trường nào trong handshake và record; ánh xạ từng sửa đổi tới bước xác minh phát hiện.
10. **Quyết định thiết kế:** dịch vụ Java cần TLS client/server và quyền theo tenant. Nêu vai trò `SSLContext`/truststore, certificate identity, application authorization và cách rotate key mà không mất trạng thái giao dịch.

**Tiêu chí hoàn thành:** từ một sơ đồ giao thức, bạn có thể chỉ ra đâu là primitive tạo secret/bọc khóa, đâu là xác thực danh tính, đâu là ràng buộc transcript và KDF, đâu là record protection/key confirmation, và cơ chế nào chịu trách nhiệm replay/authorization. Nếu một lớp bị bỏ đi, bạn phải mô tả được **điều gì vẫn đúng về toán học nhưng trở nên không an toàn ở cấp giao thức**.

## Tài liệu tham khảo

- [Java SE 21 — `KeyAgreement`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KeyAgreement.html): khởi tạo và tạo shared secret.
- [Java SE 21 — `Signature`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Signature.html): ký và xác minh với Ed25519/RSA-PSS.
- [Java SE 21 — `Cipher`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html): AEAD, `ENCRYPT_MODE`/`DECRYPT_MODE` và key wrapping `WRAP_MODE`/`UNWRAP_MODE`.
- [Java SE 21 — `javax.crypto.KEM`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html): khái niệm encapsulate/decapsulate và phạm vi API.
- [Java SE 21 — Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html): tên X25519, Ed25519, HmacSHA256 và các transformations.
- [RFC 7748](https://www.rfc-editor.org/rfc/rfc7748): Elliptic Curves for Security, X25519/X448.
- [RFC 5869](https://www.rfc-editor.org/rfc/rfc5869): HKDF-Extract/Expand và labels/context.
- [RFC 8446](https://www.rfc-editor.org/rfc/rfc8446): TLS 1.3 key schedule, CertificateVerify, Finished và transcript binding.
- [RFC 9180](https://www.rfc-editor.org/rfc/rfc9180): Hybrid Public Key Encryption (HPKE), KEM/KDF/AEAD và các chế độ xác thực.
- [Java 21 Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): TLS trong Java, cấu hình trust, xác thực peer.
