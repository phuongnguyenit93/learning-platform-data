# Thực hành: Trao đổi khóa và mã hóa xác thực trong giao thức thử nghiệm (Java 11)

> **Mục đích:** Hiểu và tự chạy một phiên giao tiếp thử nghiệm gồm trao đổi khóa phiên, xác thực máy chủ, mã hóa có kiểm tra toàn vẹn và phát hiện phát lại. Ví dụ chạy **trong một tiến trình**, mô phỏng hai đầu client/server và dữ liệu truyền qua mạng. Đây là bài thực hành về các khối mật mã; **không triển khai giao thức tự thiết kế lên hệ thống thật**. Với truyền thông mạng thực tế, ưu tiên **TLS 1.3 thông qua JSSE/SSLEngine/SSLSocket** và cơ chế xác thực danh tính đã được kiểm chứng.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Tạo cặp khóa **X25519 tạm thời** ở mỗi phía và tính cùng một bí mật ECDH mà không truyền private key.
2. Giải thích vì sao trao đổi khóa Diffie–Hellman **không tự xác thực đối tác**, và cách chữ ký **ECDSA P-256 với SHA-256** gắn danh tính máy chủ vào toàn bộ handshake.
3. Dùng **HKDF-HMAC-SHA-256** để tách bí mật chung thành khóa/IV độc lập cho hai chiều.
4. Mã hóa, giải mã bằng **AES-256-GCM** với nonce 96 bit, tag xác thực 128 bit và AAD.
5. Tự kiểm tra tình huống handshake bị sửa, bản mã/tag bị sửa và bản tin bị phát lại; phân biệt được phạm vi bảo vệ của bản demo với những gì TLS 1.3 thực hiện.

**Điều kiện chạy:** JDK 11 hoặc mới hơn với nhà cung cấp JCA hỗ trợ X25519, EC/ECDSA và AES-GCM (các JDK thông dụng có sẵn). Mã chỉ dùng Java SE, không cần thư viện bên ngoài. Có thể biên dịch trên JDK mới bằng `javac --release 11`.

## 2. Mô hình và yêu cầu an toàn

Hai bên là **Client** và **Server**. Kẻ tấn công giả định có thể quan sát, sửa, chèn và phát lại dữ liệu trên đường truyền. Bài thực hành cần đạt:

| Yêu cầu | Cách thực hiện trong demo | Giới hạn |
| --- | --- | --- |
| Bí mật khóa phiên | X25519 tạm thời mỗi kết nối; private key không truyền | Phụ thuộc vào chất lượng khóa ngẫu nhiên và bảo vệ private key |
| Xác thực máy chủ | Server ký handshake bằng khóa danh tính ECDSA; client kiểm tra bằng public key đã tin cậy trước đó | **Chưa xác thực client**; pinning được mô phỏng trong cùng tiến trình |
| Phân lập khóa | HKDF sinh khóa và IV riêng cho chiều C2S/S2C | Khóa chỉ có hiệu lực trong phiên demo |
| Bí mật và toàn vẹn bản tin | AES-GCM kèm AAD; tag sai thì giải mã thất bại | Không che độ dài bản tin và metadata truyền thông |
| Chống phát lại trong một phiên | Bộ đếm tuần tự 64 bit trên từng chiều; chỉ chấp nhận đúng số thứ tự dự kiến | Chỉ hỗ trợ bản tin **đúng thứ tự**; mất/đảo thứ tự sẽ bị từ chối |
| Giới hạn sử dụng khóa | Tối đa 1.000.000 bản tin mỗi chiều trong demo | Hết giới hạn phải đóng phiên hoặc thương lượng **khóa phiên mới**; demo chưa xây rekey |

**Thuật ngữ:** C2S = client → server; S2C = server → client. **AEAD** (Authenticated Encryption with Associated Data) bảo vệ nội dung và xác thực cả dữ liệu phụ AAD, dù AAD không được mã hóa. **Transcript** là các byte handshake được hai bên xây dựng theo cùng một quy tắc. **Ephemeral** nghĩa là khóa trao đổi mới cho mỗi phiên; không dùng lại lâu dài.

## 3. Thiết kế giao thức thử nghiệm `demo-v1`

### 3.1. Handshake (mô phỏng)

```text
CLIENT                                           SERVER
Tạo ephemeral X25519 (C_priv, C_pub)
C_pub (X.509/SPKI encoded)  --------------------->
                                   Tạo ephemeral X25519 (S_priv, S_pub)
                                   Transcript = encode(suite, serverName,
                                                       C_pub, S_pub)
                                   sig = ECDSA_sign(serverIdentityPriv,
                                                    Transcript)
                     <------------- S_pub + sig
Tái tạo đúng Transcript từ C_pub, S_pub
Kiểm tra sig bằng serverIdentityPub ĐÃ PIN
Chỉ tiếp tục nếu verify == true
K_C = X25519(C_priv, S_pub)        K_S = X25519(S_priv, C_pub)
K_C == K_S
HKDF(transcriptHash, K_C)          HKDF(transcriptHash, K_S)
C2S: key + IV; S2C: key + IV      C2S: key + IV; S2C: key + IV
          <==== Bản tin mã hóa AEAD từng chiều ====>
```

- **ClientHello** mang public key tạm thời C_pub; **ServerHello** mang S_pub và chữ ký. Public key không phải bí mật. Private key C_priv/S_priv phải giữ tại từng đầu và hủy sau khi kết thúc phiên theo cơ chế quản lý khóa của ứng dụng.
- Transcript chứa theo thứ tự: **tên bộ thuật toán/phiên bản**, **danh tính server mong đợi**, **C_pub**, **S_pub**. Từng trường được mã hóa bằng `length (4 byte, big-endian) || value` để tránh mơ hồ khi ghép.
- Server ký **toàn bộ transcript** (không chỉ ký S_pub); client xác minh với **public key danh tính server được cấp phát/pin trước qua kênh tin cậy**. Nếu một trường bị sửa, chữ ký không còn hợp lệ. Cả danh tính server, phiên bản và lựa chọn thuật toán đều nằm trong dữ liệu được ký để tránh tráo đổi ngữ cảnh.
- **Khóa danh tính ECDSA** (dùng để ký) là một vai trò độc lập với **khóa trao đổi X25519 tạm thời** (dùng tạo bí mật chung). Không dùng private key ký làm private key ECDH.
- Để demo tự chạy, chương trình tạo khóa danh tính và truyền trực tiếp public key vào biến `pinnedServerKey` **trước** khi mô phỏng handshake. Trong hệ thống thật, client phải nhận khóa tin cậy qua cấu hình được xác thực, PKI/chứng chỉ hoặc một cơ chế pinning có vòng đời xoay khóa an toàn; không được tin public key do chính đối tác chưa xác thực gửi kèm chữ ký.
- Demo cung cấp **xác thực một chiều (server authentication)**. Muốn xác thực client, cần bước xác thực client riêng được gắn chặt vào transcript/khóa phiên (hoặc sử dụng mTLS/TLS có xác thực client).

### 3.2. Dẫn xuất khóa theo RFC 5869

Gọi `T = SHA-256(transcript)` và `Z = X25519(privateLocal, publicPeer)`:

```text
PRK = HKDF-Extract(salt = T, IKM = Z)
K_c2s  = HKDF-Expand(PRK, info = suite || "|c2s key", 32 byte)
K_s2c  = HKDF-Expand(PRK, info = suite || "|s2c key", 32 byte)
IV_c2s = HKDF-Expand(PRK, info = suite || "|c2s iv", 12 byte)
IV_s2c = HKDF-Expand(PRK, info = suite || "|s2c iv", 12 byte)
```

Trong đó `HKDF-Extract` dùng `HmacSHA256` và `Expand` theo dạng `T(i) = HMAC(PRK, T(i-1) || info || byte(i))`. **Không dùng trực tiếp Z làm khóa AES**, không sử dụng một khóa cho cả hai chiều, không lấy chuỗi mật khẩu/chuỗi mã hóa hex làm AES key. `salt` và `info` là ngữ cảnh công khai; chỉ Z và PRK phải được giữ bí mật.

### 3.3. Khung dữ liệu AEAD

```text
FRAME = sequence (8 byte, big-endian) || ciphertext || GCM_tag (16 byte)
AAD   = SHA-256(transcript) || direction ("C2S"/"S2C") || sequence
nonce = IV_direction XOR (0x00000000 || sequence_64_be)
AES-256-GCM(key_direction, nonce, plaintext, AAD) -> ciphertext + tag
```

- `sequence` bắt đầu từ 0 và tăng sau khi mã hóa/giải mã **thành công**. Hai chiều có bộ đếm, khóa và IV **riêng**. Trong cùng một khóa, **không bao giờ được lặp nonce**; việc tái sử dụng (key, nonce) làm hỏng bảo đảm an toàn của GCM.
- IV cơ sở dài 12 byte được HKDF sinh mới cho **mỗi phiên**; phép XOR với bộ đếm 64 bit tạo nonce khác nhau cho từng bản tin, miễn là khóa/IV và số thứ tự không bị tái sử dụng.
- AAD gắn thông điệp vào **đúng phiên, đúng hướng và đúng thứ tự**. Số thứ tự truyền rõ, nhưng không được sửa lén vì tag xác thực cả AAD; receiver còn kiểm tra thứ tự trước khi giải mã.
- GCM tự cung cấp tag toàn vẹn: **không cần thêm HMAC trên bản mã** trong mô hình này. Khi `doFinal` báo `AEADBadTagException`, **loại bỏ toàn bộ plaintext**, không dùng dữ liệu chưa xác thực.
- Bài thực hành giới hạn plaintext 16 KiB/record và 1.000.000 record/khóa để minh họa quản lý vòng đời khóa; vượt ngưỡng phải thương lượng lại hoặc ngắt kết nối, **không reset counter dưới cùng khóa**.

## 4. Java SE 11: chương trình hoàn chỉnh

Lưu nguyên đoạn mã sau thành **`ExperimentalProtocolDemo.java`**. Toàn bộ hai đầu giao tiếp, chức năng ký/xác minh, HKDF và lớp đóng gói AEAD được đặt trong một tệp để có thể tự biên dịch chạy. Giao tiếp qua byte array là mô phỏng lớp mạng; **chưa có socket, chứng chỉ, parser khung mạng, timeout hoặc bắt tay hoàn tất của TLS**.

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.spec.ECGenParameterSpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class ExperimentalProtocolDemo {
    private static final String SUITE =
            "demo-v1|X25519|HKDF-SHA256|AES-256-GCM|ECDSA-P256-SHA256";
    private static final String SERVER_NAME = "server.demo.test";
    private static final int MAX_PLAINTEXT = 16 * 1024;
    private static final long MAX_RECORDS = 1_000_000L;
    private static final int TAG_BITS = 128;

    public static void main(String[] args) throws Exception {
        // Chỉ demo: ở hệ thống thật, client phải biết trước public key đáng tin cậy.
        KeyPairGenerator signingGenerator = KeyPairGenerator.getInstance("EC");
        signingGenerator.initialize(new ECGenParameterSpec("secp256r1"));
        KeyPair serverIdentity = signingGenerator.generateKeyPair();
        PublicKey pinnedServerKey = serverIdentity.getPublic();

        KeyPair clientEphemeral = ephemeralX25519();
        KeyPair serverEphemeral = ephemeralX25519();

        // Mô phỏng truyền public key dạng X.509/SPKI qua kênh chưa tin cậy.
        byte[] clientHello = clientEphemeral.getPublic().getEncoded();
        byte[] serverHello = serverEphemeral.getPublic().getEncoded();
        PublicKey clientSeenByServer = decodeX25519(clientHello);
        PublicKey serverSeenByClient = decodeX25519(serverHello);

        byte[] serverTranscript =
                transcript(clientSeenByServer, serverEphemeral.getPublic());
        byte[] clientTranscript =
                transcript(clientEphemeral.getPublic(), serverSeenByClient);

        byte[] serverSignature = sign(serverIdentity.getPrivate(), serverTranscript);
        if (!verify(pinnedServerKey, clientTranscript, serverSignature)) {
            throw new SecurityException("Handshake khong duoc xac thuc");
        }
        System.out.println("Chu ky may chu: hop le");

        byte[] modifiedTranscript = clientTranscript.clone();
        modifiedTranscript[0] ^= 1;
        System.out.println("Sua handshake bi tu choi: "
                + !verify(pinnedServerKey, modifiedTranscript, serverSignature));

        byte[] clientHash = MessageDigest.getInstance("SHA-256")
                .digest(clientTranscript);
        byte[] serverHash = MessageDigest.getInstance("SHA-256")
                .digest(serverTranscript);

        KeyMaterial clientKeys = derive(
                clientEphemeral.getPrivate(), serverSeenByClient, clientHash);
        KeyMaterial serverKeys = derive(
                serverEphemeral.getPrivate(), clientSeenByServer, serverHash);

        boolean keysMatch = MessageDigest.isEqual(
                clientKeys.c2sKey.getEncoded(), serverKeys.c2sKey.getEncoded())
                && MessageDigest.isEqual(
                        clientKeys.s2cKey.getEncoded(), serverKeys.s2cKey.getEncoded());
        System.out.println("Khoa hai chieu khop: " + keysMatch);

        RecordLayer client = new RecordLayer(clientKeys, true, clientHash);
        RecordLayer server = new RecordLayer(serverKeys, false, serverHash);

        System.out.println("Server nhan: "
                + server.open(client.seal("Xin chao tu client")));
        System.out.println("Client nhan: "
                + client.open(server.seal("Server da nhan")));

        byte[] genuine = client.seal("Noi dung xac thuc");
        byte[] tampered = genuine.clone();
        tampered[tampered.length - 1] ^= 1;
        try {
            server.open(tampered);
            throw new AssertionError("Khong duoc chap nhan ban ma bi sua");
        } catch (AEADBadTagException expected) {
            System.out.println("Sua ban ma: bi tu choi");
        }

        System.out.println("Server nhan tiep: " + server.open(genuine));
        try {
            server.open(genuine);
            throw new AssertionError("Khong duoc chap nhan phat lai");
        } catch (SecurityException expected) {
            System.out.println("Phat lai: bi tu choi");
        }
    }

    private static KeyPair ephemeralX25519() throws GeneralSecurityException {
        return KeyPairGenerator.getInstance("X25519").generateKeyPair();
    }

    private static PublicKey decodeX25519(byte[] encoded)
            throws GeneralSecurityException {
        return KeyFactory.getInstance("X25519")
                .generatePublic(new X509EncodedKeySpec(encoded));
    }

    private static byte[] transcript(PublicKey client, PublicKey server)
            throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(buffer);
        field(out, SUITE.getBytes(StandardCharsets.UTF_8));
        field(out, SERVER_NAME.getBytes(StandardCharsets.UTF_8));
        field(out, client.getEncoded());
        field(out, server.getEncoded());
        out.flush();
        return buffer.toByteArray();
    }

    private static void field(DataOutputStream out, byte[] value)
            throws Exception {
        out.writeInt(value.length);
        out.write(value);
    }

    private static byte[] sign(PrivateKey privateKey, byte[] message)
            throws GeneralSecurityException {
        Signature signer = Signature.getInstance("SHA256withECDSA");
        signer.initSign(privateKey);
        signer.update(message);
        return signer.sign();
    }

    private static boolean verify(PublicKey publicKey, byte[] message,
                                  byte[] signature)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance("SHA256withECDSA");
        verifier.initVerify(publicKey);
        verifier.update(message);
        return verifier.verify(signature);
    }

    private static KeyMaterial derive(PrivateKey ownPrivate,
                                      PublicKey peerPublic,
                                      byte[] transcriptHash)
            throws GeneralSecurityException {
        KeyAgreement agreement = KeyAgreement.getInstance("X25519");
        agreement.init(ownPrivate);
        agreement.doPhase(peerPublic, true);
        byte[] sharedSecret = agreement.generateSecret();

        // HKDF-Extract(salt=hash transcript, IKM=secret X25519).
        byte[] prk = hmac(transcriptHash, sharedSecret);
        try {
            return new KeyMaterial(
                    new SecretKeySpec(expand(prk, "c2s key", 32), "AES"),
                    new SecretKeySpec(expand(prk, "s2c key", 32), "AES"),
                    expand(prk, "c2s iv", 12),
                    expand(prk, "s2c iv", 12));
        } finally {
            Arrays.fill(sharedSecret, (byte) 0);
            Arrays.fill(prk, (byte) 0);
        }
    }

    private static byte[] expand(byte[] prk, String label, int length)
            throws GeneralSecurityException {
        if (length < 1 || length > 255 * 32) {
            throw new IllegalArgumentException("Do dai HKDF khong hop le");
        }
        byte[] info = (SUITE + "|" + label)
                .getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        byte[] previous = new byte[0];
        for (int counter = 1; buffer.size() < length; counter++) {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(prk, "HmacSHA256"));
            mac.update(previous);
            mac.update(info);
            mac.update((byte) counter);
            previous = mac.doFinal();
            buffer.write(previous, 0, previous.length);
        }
        return Arrays.copyOf(buffer.toByteArray(), length);
    }

    private static byte[] hmac(byte[] key, byte[] message)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        return mac.doFinal(message);
    }

    private static byte[] nonce(byte[] iv, long sequence) {
        byte[] result = iv.clone();
        for (int i = 0; i < 8; i++) {
            result[11 - i] ^= (byte) (sequence >>> (8 * i));
        }
        return result;
    }

    private static byte[] aad(byte[] transcriptHash,
                              String direction,
                              long sequence) {
        return ByteBuffer.allocate(transcriptHash.length + 3 + 8)
                .put(transcriptHash)
                .put(direction.getBytes(StandardCharsets.US_ASCII))
                .putLong(sequence)
                .array();
    }

    private static final class KeyMaterial {
        final SecretKey c2sKey;
        final SecretKey s2cKey;
        final byte[] c2sIv;
        final byte[] s2cIv;

        KeyMaterial(SecretKey c2sKey, SecretKey s2cKey,
                    byte[] c2sIv, byte[] s2cIv) {
            this.c2sKey = c2sKey;
            this.s2cKey = s2cKey;
            this.c2sIv = c2sIv;
            this.s2cIv = s2cIv;
        }
    }

    private static final class RecordLayer {
        private final SecretKey sendKey;
        private final SecretKey receiveKey;
        private final byte[] sendIv;
        private final byte[] receiveIv;
        private final byte[] transcriptHash;
        private final String sendDirection;
        private final String receiveDirection;
        private long sendSequence;
        private long receiveSequence;

        RecordLayer(KeyMaterial keys, boolean isClient, byte[] hash) {
            sendKey = isClient ? keys.c2sKey : keys.s2cKey;
            receiveKey = isClient ? keys.s2cKey : keys.c2sKey;
            sendIv = isClient ? keys.c2sIv : keys.s2cIv;
            receiveIv = isClient ? keys.s2cIv : keys.c2sIv;
            transcriptHash = hash.clone();
            sendDirection = isClient ? "C2S" : "S2C";
            receiveDirection = isClient ? "S2C" : "C2S";
        }

        byte[] seal(String message) throws GeneralSecurityException {
            byte[] plain = message.getBytes(StandardCharsets.UTF_8);
            if (plain.length > MAX_PLAINTEXT) {
                throw new IllegalArgumentException("Ban tin qua dai");
            }
            if (sendSequence >= MAX_RECORDS) {
                throw new SecurityException("Can doi khoa phien moi");
            }
            long sequence = sendSequence;
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, sendKey,
                    new GCMParameterSpec(TAG_BITS, nonce(sendIv, sequence)));
            cipher.updateAAD(aad(transcriptHash, sendDirection, sequence));
            byte[] ciphertext = cipher.doFinal(plain);
            sendSequence++;
            return ByteBuffer.allocate(8 + ciphertext.length)
                    .putLong(sequence).put(ciphertext).array();
        }

        String open(byte[] frame) throws GeneralSecurityException {
            if (frame.length < 8 + 16
                    || frame.length > 8 + MAX_PLAINTEXT + 16) {
                throw new IllegalArgumentException("Khung khong hop le");
            }
            ByteBuffer encoded = ByteBuffer.wrap(frame);
            long sequence = encoded.getLong();
            if (receiveSequence >= MAX_RECORDS
                    || sequence != receiveSequence) {
                throw new SecurityException("Sai so thu tu hoac phat lai");
            }
            byte[] ciphertext = new byte[encoded.remaining()];
            encoded.get(ciphertext);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, receiveKey,
                    new GCMParameterSpec(TAG_BITS, nonce(receiveIv, sequence)));
            cipher.updateAAD(aad(transcriptHash, receiveDirection, sequence));
            byte[] plain = cipher.doFinal(ciphertext);
            receiveSequence++;
            return new String(plain, StandardCharsets.UTF_8);
        }
    }
}
```

### Biên dịch và chạy

```bash
javac --release 11 ExperimentalProtocolDemo.java
java ExperimentalProtocolDemo
```

**Stdout mẫu (các dòng chính xác của chương trình, không chứa khóa hoặc bản mã ngẫu nhiên):**

```text
Chu ky may chu: hop le
Sua handshake bi tu choi: true
Khoa hai chieu khop: true
Server nhan: Xin chao tu client
Client nhan: Server da nhan
Sua ban ma: bi tu choi
Server nhan tiep: Noi dung xac thuc
Phat lai: bi tu choi
```

Chữ ký ECDSA và khóa phiên có thể thay đổi qua từng lần chạy, nhưng các dòng trạng thái bên trên **không đổi** nếu môi trường Java hỗ trợ các thuật toán đã chọn. Trong ví dụ, thông điệp dùng tiếng Việt **không dấu** để stdout dễ kiểm chứng; phần diễn giải vẫn dùng tiếng Việt có dấu.

## 5. Đọc mã và giải thích kết quả

**Bước 1 — Sinh khóa và vận chuyển public key.** `ephemeralX25519()` tạo cặp khóa riêng cho mỗi phía. `getEncoded()` lấy public key dạng X.509 SubjectPublicKeyInfo; phía nhận khôi phục bằng `KeyFactory.getInstance("X25519")` và `X509EncodedKeySpec`. Private key không có mặt trong byte truyền đi. Bản demo có thể dùng cùng tiến trình vì mục tiêu là kiểm chứng API mật mã và phân biệt dữ liệu công khai/bí mật.

**Bước 2 — Xác thực handshake.** `transcript(...)` cố định thứ tự, độ dài từng trường và bộ thuật toán; server ký bằng `SHA256withECDSA`; client xác minh **trước khi chấp nhận khóa phiên**. Việc đảo một bit trong transcript cho `verify == false`, vì vậy dòng `Sua handshake bi tu choi: true` chứng minh tính ràng buộc chữ ký. Điều kiện thiết yếu là `pinnedServerKey` phải được tin từ **trước**, không được lấy từ kẻ tấn công.

**Bước 3 — Hai phía nhận cùng bí mật nhưng giữ khóa riêng.** `KeyAgreement("X25519")` gọi `init(private)`, `doPhase(peerPublic, true)`, `generateSecret()`; tính chất ECDH bảo đảm Z tại hai phía trùng nhau. Mỗi phía tự chạy HKDF trên Z với cùng transcript hash. Kiểm tra `K_c2s` và `K_s2c` trùng nhau giúp chứng minh tính đúng đắn của key schedule trong demo; **không log chính key/private key** trong hệ thống thật.

**Bước 4 — Hai chiều dùng khóa khác nhau.** `RecordLayer(..., isClient=true)` dùng `K_c2s` để gửi và `K_s2c` để nhận; server đảo lại. Nhờ thế mỗi chiều có nonce space độc lập, và nhãn `C2S`/`S2C` trong AAD ngăn nhầm lẫn hướng.

**Bước 5 — Mã hóa và kiểm tra tag.** `seal` tạo nonce, gọi `AES/GCM/NoPadding` với `GCMParameterSpec(128, nonce)`, nạp AAD **trước** `doFinal`, rồi đóng khung theo thứ tự. `open` phân tích sequence, kiểm tra bằng số thứ tự mong đợi, dựng lại nonce/AAD và chỉ trả plaintext sau khi tag hợp lệ. Byte cuối của frame bị đổi làm GCM từ chối, tạo dòng `Sua ban ma: bi tu choi`.

**Bước 6 — Chặn phát lại.** Sau khi `open(genuine)` thành công, `receiveSequence` tăng. Lần `open(genuine)` thứ hai mang sequence cũ và bị từ chối. Đây là **bảo vệ phát lại trong một phiên theo mô hình in-order**: ứng dụng chạy trên luồng không đảm bảo thứ tự sẽ cần thiết kế chống phát lại khác (cửa sổ sequence, quản lý mất gói, timeout) và đánh giá an toàn độc lập.

**Bước 7 — Xử lý lỗi dứt khoát.** Nếu chữ ký sai, chương trình dừng bằng `SecurityException` trước khi tạo RecordLayer. Nếu tag sai, `AEADBadTagException` xảy ra trước khi tăng số thứ tự nhận; bản tin hợp lệ với cùng số thứ tự sau đó vẫn có thể giải mã. Trên một giao thức mạng hoàn chỉnh, quy tắc xử lý lỗi, đóng kết nối và chính sách retry phải được thiết kế nhất quán để tránh việc một peer cố ý làm lệch trạng thái hai bên.

## 6. Bài kiểm chứng bổ sung để tự thực hành

1. **Kiểm tra MITM trên public key:** thay một byte trong `serverHello` trước khi client tạo `clientTranscript`. Nếu byte vẫn tạo thành một public key hợp lệ nhưng khác, transcript của client đổi và chữ ký sẽ không hợp lệ; nếu khóa mã hóa không giải được hoặc dữ liệu không thể parse, cũng phải từ chối. Điểm học: **ECDH đơn lẻ không ngăn MITM**, phải xác thực transcript/đối tác.
2. **Kiểm tra thay đổi frame:** đổi một byte của ciphertext hoặc tag trong `tampered`. Kết quả kỳ vọng: `AEADBadTagException`. Đổi 8 byte sequence ở đầu frame thì bị chặn bởi kiểm tra thứ tự hoặc tag AAD.
3. **Kiểm tra chống dùng lại nonce:** thử mã hóa hai thông điệp bằng **cùng một đối tượng RecordLayer**: sequence sẽ tăng và nonce khác. Không tự đặt lại `sendSequence` về 0 dưới cùng key/IV; với GCM, đó là lỗi mật mã nghiêm trọng.
4. **Kiểm tra hai chiều:** đổi nhãn hướng `C2S` thành `S2C` ở bên gửi hoặc nhận. Tag sẽ không hợp lệ; key schedule và AAD phải thống nhất giữa hai phía.
5. **Kiểm tra giới hạn:** gửi plaintext dài hơn 16.384 byte; chương trình từ chối trước khi mã hóa. Thiết kế thật cần kiểm soát cả kích thước frame, tài nguyên cấp phát và lưu lượng.

**Tiêu chí hoàn thành:** lệnh `javac --release 11` biên dịch thành công; `java ExperimentalProtocolDemo` cho 8 dòng stdout nêu trên; bạn giải thích được vai trò khác nhau của khóa danh tính, khóa ephemeral, HKDF, AES-GCM, IV/nonce, AAD, sequence và giới hạn của xác thực một chiều.

## 7. Lỗi thường gặp và hướng xử lý

| Dấu hiệu | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `NoSuchAlgorithmException: X25519` | JDK/provider không hỗ trợ X25519 | Dùng bản phân phối JDK 11+ có SunEC/nhà cung cấp thích hợp; kiểm tra `java -version` và danh sách provider |
| `InvalidKeyException` trong key agreement hoặc signature | Trộn khóa EC/ECDSA với khóa X25519, hoặc public key bị hỏng | Dùng `KeyFactory("X25519")` cho public key ECDH; `EC` + P-256 cho chữ ký; xác định đúng vai trò |
| `AEADBadTagException` | Sai key, nonce, AAD, ciphertext/tag, transcript, direction hoặc frame | So sánh cấu hình hai phía; xác thực handshake trước; không xuất plaintext chưa xác minh |
| Client và server có key khác nhau | Hai phía mã hóa transcript khác, hoán vị C_pub/S_pub hoặc dùng sai private/public | Dùng cùng thứ tự và mã hóa trường có độ dài; chỉ log hash/transcript công khai khi cần debug |
| Chấp nhận chữ ký nhưng vẫn bị giả mạo server | Client tự tin khóa ký do phía chưa được xác thực cung cấp | Cấp phát/pin trust anchor trước qua kênh tin cậy; thiết kế cơ chế xoay khóa |
| Trùng nonce, đếm lại từ 0 | Reuse key/IV khi restart hoặc reconnect; chia sẻ counter sai | Khóa và IV **mới mỗi phiên**, state một chiều độc lập; giới hạn số record và không reset |
| Packet hợp lệ bị từ chối vì sequence | Demo chỉ chấp nhận thứ tự liên tục | Đây là ràng buộc bài lab; thực tế cần tầng truyền tin đáng tin cậy hoặc cơ chế replay window phù hợp |

**Điểm bảo mật cần giữ trong mọi triển khai:**

- Không tự xây protocol để thay thế TLS 1.3. Giao thức an toàn thực tế còn cần chứng chỉ/danh tính, state machine chống downgrade, alert, key confirmation đầy đủ, xác thực cả client khi cần, quản trị key rotation, parse không mơ hồ, chống DoS và kiểm thử chuyên sâu.
- GCM cung cấp tính bí mật và toàn vẹn **chỉ khi** (key, nonce) là duy nhất và tag được kiểm tra thành công; sai tag phải loại bỏ bản tin.
- Không nhúng private key hoặc khóa AES tĩnh vào source code; không in shared secret, PRK, khóa phiên hay nội dung nhạy cảm ra log. Demo cố gắng xóa mảng byte bí mật sau dẫn xuất, nhưng việc xóa object khóa do provider quản lý và bộ nhớ runtime cần chính sách vòng đời riêng.
- Không dùng khóa phiên quá lâu; giới hạn 1.000.000 bản tin trong code là rào chắn giáo dục, **không phải định mức chung áp dụng cho mọi triển khai**. Cần tính giới hạn GCM theo kích thước record, lượng dữ liệu, tần suất gửi và khuyến nghị của giao thức chuẩn.
- Bài dùng **các thành phần mật mã vẫn được áp dụng rộng rãi**: X25519, ECDSA-P256/SHA-256, HKDF-SHA-256, AES-GCM, TLS 1.3. Không đề xuất các chế độ mã hóa thiếu xác thực hay các giao thức đã bị thay thế.

## 8. Câu hỏi ôn tập

1. Vì sao người nghe lén biết C_pub/S_pub nhưng không thể tự tính bí mật chung nếu không biết private key tương ứng? Vì sao câu trả lời này **chưa đủ** để chống MITM?
2. Nếu chữ ký chỉ bao phủ S_pub nhưng không bao phủ C_pub, serverName và bộ thuật toán, những kiểu thay thế/ngữ cảnh sai nào có thể xuất hiện?
3. Vì sao phải có **hai** khóa AES riêng và **một sequence riêng cho từng chiều**? Điều gì xảy ra nếu hai bên sử dụng cùng key và nonce cho thông điệp khác nhau?
4. Vai trò khác nhau của `salt`, `IKM`, `info` trong HKDF là gì? Vì sao khóa phiên không lấy thẳng từ `generateSecret()`?
5. AAD xác thực phần nào của gói tin? Vì sao nó vẫn hữu ích dù bản thân AAD không được mã hóa?
6. Điều gì được bảo đảm khi bắt được `AEADBadTagException`? Những điều gì **không** được bảo đảm nếu server public key chưa có trust anchor?
7. Vì sao muốn sử dụng trên Internet nên chuyển sang **TLS 1.3 với Java JSSE** thay vì mở rộng giao thức thử nghiệm này thành production protocol?

## 9. Tài liệu chuẩn để đối chiếu

- [Java SE 11 — Standard Algorithm Names](https://docs.oracle.com/en/java/javase/11/docs/specs/security/standard-names.html): tên thuật toán `KeyAgreement`, `KeyPairGenerator`, `Signature`, `Cipher`, `Mac`.
- [Java SE 11 — SunEC Provider](https://docs.oracle.com/en/java/javase/11/security/oracle-providers.html): hỗ trợ X25519/XDH và ECDSA.
- [RFC 7748 — Elliptic Curves for Security](https://www.rfc-editor.org/rfc/rfc7748): định nghĩa X25519.
- [RFC 5869 — HKDF](https://www.rfc-editor.org/rfc/rfc5869): quy tắc Extract/Expand.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): mô hình trao đổi khóa, xác thực handshake và AEAD của giao thức sử dụng thực tế.

**Kết nối kiến thức với thực hành:** X25519 tạo bí mật chung; chữ ký với khóa tin cậy xác thực transcript; HKDF biến bí mật chung thành khóa dùng riêng theo ngữ cảnh; AES-GCM bảo vệ từng bản tin; sequence/AAD giúp phát hiện phát lại và sai phiên/hướng. Cần đồng thời đầy đủ các lớp này để hiểu vì sao mã hóa và xác thực là hai yêu cầu bổ sung cho nhau.
