# Replay trong key establishment: Chống phát lại khi thiết lập khóa phiên

> **Chương:** Key establishment  
> **Đề bài:** Replay trong key establishment  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — quản lý vòng đời khóa từ tạo, cấp phát, lưu trữ, sử dụng, xoay vòng tới thu hồi và hủy, kết nối mật mã đối xứng/bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, IAM và audit.

## 1. Vì sao một handshake hợp lệ ngày hôm qua có thể nguy hiểm hôm nay?

Hãy tưởng tượng **Billing Service** cần thiết lập khóa phiên để trao đổi dữ liệu với **Ledger Service**. Hai bên trao đổi dữ liệu bắt tay (handshake) rồi tạo khóa dùng cho mã hóa và xác thực.

Một kẻ tấn công có thể nghe lén mạng và lưu lại bản sao các gói. Họ không cần biết private key, DEK hay session key. Nếu server chỉ kiểm tra một chữ ký cũ trên câu cố định "Tôi là Billing Service", kẻ tấn công có thể phát lại thông điệp ấy để giả vờ đang bắt tay một lần nữa.

~~~text
Phiên cũ:
    Client -> Server: identity, chữ ký hợp lệ trên thông điệp cố định
    Server -> Client: xác thực thành công

Phiên mới do attacker kích hoạt:
    Attacker -> Server: chính identity và chữ ký cũ
    Server          : có thể chấp nhận nhầm nếu không kiểm tra tính mới
~~~

**Replay attack (tấn công phát lại)** là hành vi gửi lại thông điệp hoặc chuỗi thông điệp trước đây để phía nhận xử lý như yêu cầu mới. Đặc biệt, thông điệp bị phát lại có thể vẫn **nguyên vẹn và có chữ ký/MAC đúng**.

**Key establishment (thiết lập khóa)** gồm key agreement, key transport và những cơ chế KEM-based; mục tiêu là cho các bên được phép có vật liệu khóa để phục vụ một phiên hoặc một mục đích. **Chống replay** phải được thiết kế ở cấp **giao thức và trạng thái phiên**, không chỉ ở phép toán mật mã lõi.

### Mục tiêu

Sau bài này, bạn cần:

1. Hiểu khác biệt giữa **integrity, authentication, freshness, key confirmation** và chống replay.
2. Mô tả các kiểu replay trong authenticated ECDH, key transport, KEM và TLS 1.3.
3. Giải thích vai trò client/server nonce, challenge, ephemeral key, transcript binding, identity binding, HKDF và Finished MAC.
4. Phân biệt **replay handshake** với **replay ciphertext/HTTP request ứng dụng**.
5. Hiểu vì sao TLS 1.3 **0-RTT early data** đòi hỏi cân nhắc anti-replay riêng.
6. Đọc và thử nghiệm ví dụ Java 17 sử dụng X25519, Ed25519 và HMAC/HKDF.
7. Gắn chống replay với quản lý khóa, KMS/HSM, IAM, rotation và audit.

---

## 2. Phân biệt những bảo đảm an ninh trong handshake

| Thuộc tính | Câu hỏi cần trả lời | Kỹ thuật hay dùng | Điều chưa được bảo đảm |
|---|---|---|---|
| **Integrity** | Byte thông điệp bị thay đổi có được phát hiện không? | Chữ ký số, MAC, AEAD tag | Bản tin cũ nguyên vẹn vẫn có thể được gửi lại |
| **Entity authentication** | Có xác thực được peer gắn với danh tính mong đợi không? | Chứng thư, chữ ký, MAC, workload identity | Bằng chứng có thể không mới |
| **Freshness** | Bằng chứng có thực sự được tạo cho phiên hiện tại không? | Challenge/nonce mới, session context | Quyền nghiệp vụ chưa tự được xác định |
| **Liveness** | Bên kia có đang tham gia tương tác ngay lúc này không? | Challenge–response gắn phiên | Không có nghĩa được phép làm mọi thao tác |
| **Key agreement** | Hai bên có cùng vật liệu khóa đã dẫn xuất không? | (EC)DH, KEM và KDF | Chưa chắc biết đúng danh tính peer |
| **Key confirmation** | Peer có thể chứng minh đang nắm đúng khóa phiên không? | Finished MAC/record được xác thực | Không tự thay thế anti-replay nghiệp vụ |
| **Authorization** | Peer có quyền gọi API hoặc truy cập dữ liệu không? | IAM, ABAC/RBAC, policy ứng dụng | Không tự chống phát lại request |

Một signature hợp lệ chỉ chứng minh một thông điệp đã được ký bởi bên có khả năng sử dụng signing key tương ứng, theo giả định thuật toán và public key đã tin cậy. **Không thể nhảy từ Signature.verify = true sang kết luận “đây là phiên mới”.**

### 2.1. Freshness, liveness và chống replay không phải một

- **Freshness**: chứng cứ gắn với yếu tố được sinh cho phiên hiện tại, chẳng hạn nonce do phía xác minh mới phát hành.
- **Liveness**: có bằng chứng phía kia tham gia tương tác bây giờ, thay vì chỉ trình ra recording có sẵn.
- **Anti-replay**: phía nhận có chính sách xử lý lại các bằng chứng/record đã nhận hoặc các hành động đã thực hiện.

Tùy giao thức, freshness tốt thường giúp chống replay handshake, nhưng vẫn cần xem **trạng thái server, session lifecycle và tác động ứng dụng**.

### 2.2. Không được dựa vào chữ ký trên câu cố định

Thiết kế yếu:

~~~text
Sig = Sign(clientPrivateKey, "I am client-A")
Server: Verify(clientPublicKey, "I am client-A", Sig)
~~~

Attacker có thể phát lại chữ ký nguyên vẹn.

Thiết kế hợp lý hơn:

~~~text
Server sinh serverNonce mới.
Client ký:
    protocolVersion || roles || clientId || serverId ||
    clientNonce || serverNonce || ephemeralPublicKeys || suite
Server kiểm tra chữ ký và serverNonce đúng phiên đang chờ.
~~~

Không phải chỉ cần thêm một trường **nonce** là xong; nonce phải thực sự được sinh/kiểm tra/tiêu thụ đúng quy tắc.

---

## 3. Replay xuất hiện ở bước nào?

### 3.1. Phát lại ClientHello

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Attacker
    participant S as Server
    C->>S: ClientHello (Nc, ephemeral public key)
    Note over A: Ghi lại ClientHello
    Note over S: Phiên cũ kết thúc
    A->>S: Replay cùng ClientHello
    S-->>A: Có thể phản hồi hoặc cấp state tạm
~~~

**Điều cần tách biệt:** replay được ClientHello không đồng nghĩa hoàn thành authentication. Trong một handshake dùng server challenge/ephemeral mới và Finished đúng cách, attacker thường không thể hoàn thành bằng chứng của client chỉ từ recording cũ.

Tuy nhiên, message đầu tiên được phát lại vẫn có thể gây **tốn CPU, bộ nhớ, lookup chứng thư hoặc HSM operations**, tạo nguy cơ DoS/resource exhaustion. Server có thể cần giới hạn tải, timeout, retry cookies hoặc biện pháp được giao thức hỗ trợ.

### 3.2. Phát lại client signature/MAC cũ

Nếu server không ràng buộc bằng chứng với challenge hiện tại, chữ ký/MAC cũ có thể được chấp nhận. Một cách chống điển hình là yêu cầu client ký **cả server nonce mới** và transcript của phiên.

~~~text
T_old chứa serverNonce = Ns_old.
T_new chứa serverNonce = Ns_new.

Sig_old = Sign(SK_client, T_old)
Verify(PK_client, T_new, Sig_old) = false (nếu T_new khác và thuật toán đúng)
~~~

Phía nhận không được lấy nonce từ bản tin client rồi coi đó là challenge mình đã phát hành. Phải so với **nonce đang chờ trong state tin cậy**.

### 3.3. Phát lại cả handshake cũ

Nếu VM/pod khôi phục snapshot và vô tình sử dụng lại **server nonce, ephemeral private key hoặc session state**, một replay có thể trở nên nguy hiểm hơn. Lưu giữ state và khôi phục an toàn là phần của chống replay.

### 3.4. Key transport: phát lại encrypted DEK

~~~text
Sender:
    DEK = CSPRNG()
    wrappedDEK = RSA-OAEP(recipientPublicKey, DEK)

Attacker:
    ghi lại wrappedDEK
    gửi lại wrappedDEK cho recipient
~~~

RSA-OAEP bảo vệ bí mật DEK khi truyền. Nó **không lưu trạng thái “đã được nhận”**. Recipient có thể mở lại cùng DEK nếu còn private key tương ứng.

Điều nguy hiểm tùy giao thức: có thể chỉ là xử lý lặp file, hoặc tệ hơn là coi DEK cũ là khóa phiên mới. Cần bind sender/recipient, operation ID, nonce, version và quyền; ghi nhận trạng thái xử lý khi nghiệp vụ yêu cầu.

### 3.5. KEM: phát lại encapsulation ciphertext

Một KEM có giao diện khái niệm:

~~~text
(encapsulationCiphertext, sharedSecret) = Encapsulate(pkRecipient)
sharedSecret2 = Decapsulate(skRecipient, encapsulationCiphertext)
~~~

Với cùng encapsulation ciphertext và recipient key phù hợp, bản thân **KEM primitive không tự biết lần decapsulate nào là lần đầu tiên**. Cơ chế thiết lập khóa cấp giao thức phải bổ sung freshness, xác thực, KDF context, key confirmation và replay policy.

### 3.6. Replay ciphertext sau handshake

AEAD tag trên một record hợp lệ vẫn có thể xác minh hợp lệ khi attacker gửi lại nguyên record đó. Replay **không đòi hỏi một lần mã hóa mới**.

Do đó:

- **Không lặp nonce AES-GCM dưới cùng DEK khi encrypt** là quy tắc bảo vệ an toàn phép mã hóa.
- **Không chấp nhận lại record đã xử lý** là quy tắc của phía decrypt/protocol/application state.

Hai quy tắc đều quan trọng nhưng **khác nhau**.

---

## 4. Replay và những lỗi giao thức liên quan

| Dạng lỗi | Đặc điểm | Vì sao liên quan |
|---|---|---|
| **Replay** | Gửi lại message/transcript cũ | Proof có thể nguyên vẹn nhưng không mới |
| **Reflection** | Đẩy challenge/response theo chiều ngược lại | Giao thức thiếu role/direction separation |
| **MITM** | Đứng giữa, thay key share hoặc ngữ cảnh | Chỉ ECDH không tự xác thực peer |
| **Unknown key-share** | Hai phía hiểu sai danh tính peer dù có một secret chung | Thiếu identity binding |
| **Downgrade** | Ép negotiation về phiên bản/suite yếu | Thiếu authenticated suite negotiation |
| **Rollback** | Khôi phục phiên bản, counter hoặc state cũ | Có thể tái chấp nhận proof đã dùng |
| **Relay** | Chuyển tiếp thông điệp tươi theo thời gian thực | Freshness không ngăn mọi relay |
| **Key compromise** | Bí mật xác thực hoặc phiên bị lộ | Không thể giải quyết chỉ bằng nonce |

Đừng gom tất cả dưới một nhãn "replay". Khác nguyên nhân nghĩa là **khác biện pháp phòng ngừa**.

---

## 5. Nguyên tắc phòng chống replay khi thiết lập khóa

### 5.1. Nonce từ hai phía

Một mẫu mutual handshake có:

- **Nc:** client nonce ngẫu nhiên mới.
- **Ns:** server nonce mới; client phải chứng minh đã thấy Ns.
- **ec / es:** public key ephemeral của client/server.
- **clientId/serverId:** định danh được ánh xạ tới trust registry/chứng thư.
- **suite:** thuật toán và phiên bản đã thương lượng.

Một client nonce đơn độc **không đủ cho mọi mô hình**, đặc biệt server hoàn toàn stateless và không nhớ nonce đã dùng. Server challenge tạo sau khi nhận ClientHello thường tăng khả năng chứng minh client đang tham gia vào phiên thực sự mới.

### 5.2. Đóng gói transcript không nhập nhằng

Một transcript ở mức khái niệm:

~~~text
protocolId
protocolVersion
clientRole, clientIdentity
serverRole, serverIdentity
algorithmSuite
clientNonce, serverNonce
clientEphemeralPublicKey, serverEphemeralPublicKey
keyPurpose, audience
~~~

Phải mã hóa byte chính xác theo chuẩn hoặc định dạng **length-prefix**. Đừng chỉ nối các chuỗi vì các cặp trường khác nhau có thể tạo ra cùng chuỗi tổng hợp.

**Chữ ký/MAC xác thực transcript**, không chỉ một vài trường tùy chọn. Nếu transcript bỏ qua server identity hoặc suite, attacker có thể khai thác misbinding/downgrade trong một số protocol.

### 5.3. Phân tách vai trò và hướng

Khi dùng HMAC/Finished hoặc dẫn xuất traffic keys, cần nhãn phân biệt:

~~~text
client-auth/v1
server-auth/v1
client-finished/v1
server-finished/v1
traffic/client-to-server
traffic/server-to-client
~~~

Nếu hai phía dùng cùng format proof và cùng key cho cả hai vai trò, một số giao thức yếu có thể bị **reflection**. Domain separation ngăn dùng nhầm message hợp lệ ở ngữ cảnh khác.

### 5.4. Ràng buộc transcript vào KDF

Từ X25519 hoặc KEM thu được shared secret. Khóa làm việc cần được dẫn xuất qua key schedule rõ ràng:

~~~text
sharedSecret = X25519(...) hoặc KEM shared secret
transcriptHash = SHA-256(canonicalTranscript)
PRK = HKDF-Extract(salt/context, sharedSecret)
clientFinishedKey = HKDF-Expand(PRK, "client-finished" || transcriptHash)
serverFinishedKey = HKDF-Expand(PRK, "server-finished" || transcriptHash)
~~~

**HKDF không tự xác thực danh tính**. Transcript cần được ràng buộc vào bằng chứng xác thực; KDF với nhãn phù hợp giúp tách phiên và mục đích.

### 5.5. Key confirmation

Hai phía có thể xác nhận đang giữ đúng khóa phiên:

~~~text
FinishedC = HMAC(clientFinishedKey, transcriptHash)
FinishedS = HMAC(serverFinishedKey, transcriptHash)
~~~

Server chỉ chấp nhận **FinishedC** tính trên transcript hiện tại và dưới khóa của hướng client. Client kiểm tra **FinishedS** theo hướng server. Điều này chứng minh peer có khả năng sử dụng session secret tương ứng, trong giả định giao thức đúng.

### 5.6. Trạng thái đã dùng và replay cache

Khi hoàn thành hoặc chấp nhận một proof:

- Khóa cặp identity/session/nonce hoặc transcript hash vào một **used-proof registry** nếu thiết kế đòi hỏi.
- Dùng **atomic insert**, không tách check-exists và insert.
- Đặt TTL/cửa sổ gắn với thời hạn chấp nhận proof.
- Nếu có nhiều pod, trạng thái phải nhất quán theo nhu cầu.
- Bảo vệ state khi restart, restore và failover.

Replay cache RAM trong một tiến trình **không đủ** cho một cluster nhiều pod. Cache cũ bị rollback cũng có thể dẫn đến chấp nhận proof cũ.

---

## 6. Sơ đồ handshake chống replay ở mức khái niệm

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    Note over C: Sinh Nc, X25519 ephemeral C
    C->>S: ClientHello(Nc, epkC, clientId, suite)
    Note over S: Sinh Ns, X25519 ephemeral S
    Note over S: T = context + IDs + roles + suite + Nc + Ns + epkC + epkS
    Note over S: SignS = Sign(skS, T)
    S->>C: ServerHello(Ns, epkS, SignS)
    Note over C: Verify SignS bằng trusted public key của S
    Note over C: X25519 -> sharedSecret, HKDF -> finished keys
    Note over C: SignC = Sign(skC, T)
    C->>S: SignC, FinishedC
    Note over S: Verify SignC, derive secret, Verify FinishedC
    Note over S: Check session nonce/state và quyền
    S->>C: FinishedS
    Note over C: Verify FinishedS; đánh dấu phiên sẵn sàng
~~~

Trong sơ đồ, chữ ký ràng buộc private signing key của một danh tính với transcript, còn **Finished** ràng buộc peer với shared secret đã dẫn xuất cho **đúng phiên**.

**Cảnh báo:** đây là sơ đồ giảng dạy, không phải giao thức tự thiết kế được khuyến nghị triển khai. Giao thức thật cần có định dạng message chuẩn, state machine, xử lý các public key không hợp lệ, timeout, certificate validation, downgrade protection, key erasure và phân tích bảo mật. Ưu tiên TLS 1.3/mTLS hoặc giao thức thiết lập khóa tiêu chuẩn đã được kiểm chứng.

---

## 7. Java 17: X25519, Ed25519, HKDF và kiểm tra Finished cũ

Đoạn mã sau là **demo chạy trong một JVM**. Nó cho thấy nguyên tắc:

1. Client và server có signing identities Ed25519 đã được tin cậy từ bên ngoài (trong demo tạo tại chỗ).
2. Mỗi session có **Nc/Ns và hai cặp X25519 ephemeral mới**.
3. Hai bên xác minh chữ ký Ed25519 trên một transcript có identity/roles.
4. Hai bên tính X25519 secret, chạy HKDF-Extract/Expand để dẫn xuất khóa Finished phân tách hướng.
5. Finished cũ được đem so với proof mong đợi của phiên mới và phải bị từ chối.
6. Một registry đơn tiến trình đánh dấu session ID đã xử lý.

Thực tế, các thành phần đang chạy trên máy khác nhau và chỉ nắm private key của chính mình. Đoạn mã này **không có transport, PKI, authorization, persistence hoặc key lifecycle production**.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.util.Arrays;
import java.util.Base64;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class ReplayHandshakeDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final String CLIENT_ID = "billing-service";
    private static final String SERVER_ID = "ledger-service";

    private record SessionProof(byte[] finished, byte[] transcriptHash) {
        private SessionProof {
            finished = finished.clone();
            transcriptHash = transcriptHash.clone();
        }
        @Override public byte[] finished() { return finished.clone(); }
        @Override public byte[] transcriptHash() {
            return transcriptHash.clone();
        }
    }

    private static final class ReplayRegistry {
        // Demo: chỉ dùng trong một process, chưa có TTL/cluster.
        private final Set<String> accepted = ConcurrentHashMap.newKeySet();

        boolean accept(byte[] sessionId) {
            String id = Base64.getUrlEncoder()
                    .withoutPadding().encodeToString(sessionId);
            return accepted.add(id);
        }
    }

    private ReplayHandshakeDemo() {}

    static KeyPair newKeys(String algorithm)
            throws GeneralSecurityException {
        return KeyPairGenerator.getInstance(algorithm).generateKeyPair();
    }

    static byte[] newNonce() {
        byte[] b = new byte[16];
        RNG.nextBytes(b);
        return b;
    }

    static void put(DataOutputStream out, byte[] field)
            throws IOException {
        out.writeInt(field.length);
        out.write(field);
    }

    static void put(DataOutputStream out, String field)
            throws IOException {
        put(out, field.getBytes(StandardCharsets.UTF_8));
    }

    static byte[] transcript(
            byte[] nc, byte[] ns,
            PublicKey clientEphemeral, PublicKey serverEphemeral)
            throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(b);
        put(out, "key-establishment/X25519-Ed25519/v1");
        put(out, "role/client");
        put(out, CLIENT_ID);
        put(out, "role/server");
        put(out, SERVER_ID);
        put(out, "suite/X25519+Ed25519+HKDF-SHA256");
        put(out, nc);
        put(out, ns);
        put(out, clientEphemeral.getEncoded());
        put(out, serverEphemeral.getEncoded());
        out.flush();
        return b.toByteArray();
    }

    static byte[] sign(PrivateKey key, byte[] message)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("Ed25519");
        s.initSign(key);
        s.update(message);
        return s.sign();
    }

    static boolean verify(
            PublicKey trustedKey, byte[] message, byte[] sig)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("Ed25519");
        s.initVerify(trustedKey);
        s.update(message);
        return s.verify(sig);
    }

    static byte[] x25519(PrivateKey own, PublicKey peer)
            throws GeneralSecurityException {
        KeyAgreement ka = KeyAgreement.getInstance("X25519");
        ka.init(own);
        ka.doPhase(peer, true);
        return ka.generateSecret();
    }

    static byte[] sha256(byte[] data)
            throws GeneralSecurityException {
        return MessageDigest.getInstance("SHA-256").digest(data);
    }

    static byte[] hmac(byte[] key, byte[] data)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        return mac.doFinal(data);
    }

    // Một block HKDF-Expand: đầu ra 32 byte, HMAC-SHA-256.
    static byte[] deriveFinishedKey(
            byte[] shared, byte[] tHash, String role)
            throws GeneralSecurityException, IOException {
        byte[] prk = hmac(tHash, shared); // HKDF-Extract
        try {
            ByteArrayOutputStream b = new ByteArrayOutputStream();
            DataOutputStream out = new DataOutputStream(b);
            put(out, "finished-key/v1");
            put(out, role);
            put(out, tHash);
            out.flush();

            byte[] info = b.toByteArray();
            byte[] expandInput = Arrays.copyOf(info, info.length + 1);
            expandInput[expandInput.length - 1] = (byte) 1;
            return hmac(prk, expandInput); // HKDF-Expand, L=32
        } finally {
            Arrays.fill(prk, (byte) 0);
        }
    }

    static byte[] makeFinished(
            byte[] key, byte[] tHash, String role)
            throws GeneralSecurityException, IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(b);
        put(out, "finished-proof/v1");
        put(out, role);
        put(out, tHash);
        out.flush();
        return hmac(key, b.toByteArray());
    }

    static SessionProof handshake(
            KeyPair clientIdentity,
            KeyPair serverIdentity,
            byte[] oldFinishedToReplay)
            throws GeneralSecurityException, IOException {

        byte[] nc = newNonce();
        byte[] ns = newNonce();
        KeyPair ce = newKeys("X25519");
        KeyPair se = newKeys("X25519");

        byte[] t = transcript(nc, ns, ce.getPublic(), se.getPublic());

        // Public keys xác minh đã tin cậy từ registry giả lập.
        byte[] sSig = sign(serverIdentity.getPrivate(), t);
        if (!verify(serverIdentity.getPublic(), t, sSig)) {
            throw new GeneralSecurityException("Invalid server signature");
        }

        byte[] cSig = sign(clientIdentity.getPrivate(), t);
        if (!verify(clientIdentity.getPublic(), t, cSig)) {
            throw new GeneralSecurityException("Invalid client signature");
        }

        byte[] secretC = x25519(ce.getPrivate(), se.getPublic());
        byte[] secretS = x25519(se.getPrivate(), ce.getPublic());

        byte[] keyC = null;
        byte[] keySForC = null;
        byte[] keyS = null;
        byte[] keyCForS = null;

        try {
            byte[] tHash = sha256(t);
            keyC = deriveFinishedKey(secretC, tHash, "client");
            keySForC = deriveFinishedKey(secretS, tHash, "client");
            keyS = deriveFinishedKey(secretS, tHash, "server");
            keyCForS = deriveFinishedKey(secretC, tHash, "server");

            byte[] finishedC = makeFinished(keyC, tHash, "client");
            byte[] expectedC =
                    makeFinished(keySForC, tHash, "client");

            if (!MessageDigest.isEqual(finishedC, expectedC)) {
                throw new GeneralSecurityException(
                        "Client key confirmation failed");
            }

            if (oldFinishedToReplay != null) {
                System.out.println("Old Finished accepted in new session: "
                        + MessageDigest.isEqual(
                                oldFinishedToReplay, expectedC));
            }

            byte[] finishedS = makeFinished(keyS, tHash, "server");
            byte[] expectedS =
                    makeFinished(keyCForS, tHash, "server");
            if (!MessageDigest.isEqual(finishedS, expectedS)) {
                throw new GeneralSecurityException(
                        "Server key confirmation failed");
            }

            System.out.println(
                    "Signatures and mutual Finished verified");
            return new SessionProof(finishedC, tHash);
        } finally {
            Arrays.fill(secretC, (byte) 0);
            Arrays.fill(secretS, (byte) 0);
            if (keyC != null) Arrays.fill(keyC, (byte) 0);
            if (keySForC != null) Arrays.fill(keySForC, (byte) 0);
            if (keyS != null) Arrays.fill(keyS, (byte) 0);
            if (keyCForS != null) Arrays.fill(keyCForS, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        KeyPair client = newKeys("Ed25519");
        KeyPair server = newKeys("Ed25519");

        SessionProof oldSession = handshake(client, server, null);
        SessionProof newSession =
                handshake(client, server, oldSession.finished());

        ReplayRegistry registry = new ReplayRegistry();
        System.out.println("First accepted: "
                + registry.accept(oldSession.transcriptHash()));
        System.out.println("Same session replay accepted: "
                + registry.accept(oldSession.transcriptHash()));
        System.out.println("New session accepted: "
                + registry.accept(newSession.transcriptHash()));
    }
}
~~~

### 7.1. Kết quả dự kiến

~~~text
Signatures and mutual Finished verified
Old Finished accepted in new session: false
Signatures and mutual Finished verified
First accepted: true
Same session replay accepted: false
New session accepted: true
~~~

Đây là **kết quả dự kiến**, không phải khẳng định đoạn mã đã được biên dịch/chạy trên mọi JVM. Cần kiểm tra trên JDK/provider thực tế.

**Giải thích:**

- Mỗi phiên sinh nonce và ephemeral X25519 mới nên transcript hash và khóa Finished được dẫn xuất khác.
- Client/server chữ ký cho transcript tương ứng, không cho câu cố định.
- Tag Finished từ phiên trước không khớp với khóa xác nhận phiên mới.
- Replay registry minh họa phép **claim một lần** dựa trên transcript hash trong một process.

### 7.2. Giới hạn và điều phải làm trong production

- Demo giữ cả private keys hai bên trong JVM; giao thức thật tách process và thực hiện chứng thư/trust validation.
- Không xử lý đầy đủ public key không hợp lệ, zero/shared-secret edge cases, certificate revocation, downgrade, PSK hoặc KEM.
- Không có network protocol/state machine/timeouts, nên **không dùng ví dụ để tự phát minh handshake**.
- Không có replay store chia sẻ giữa pod, TTL, persistence, crash recovery hay anti-rollback.
- Không có traffic encryption và authorization; Finished keys **không được dùng trực tiếp làm AES-GCM DEK**.
- Không có quản lý quyền KMS/HSM, audit hoặc chống resource exhaustion.
- Việc xóa mảng qua Arrays.fill chỉ là best effort; provider có thể giữ bản sao secret ở nơi khác.
- Định danh CLIENT_ID/SERVER_ID là hằng cho demo; trong hệ thống thật phải xác minh public key được gắn với đúng principal/tenant.

Với sản phẩm thực tế, ưu tiên **TLS 1.3/mTLS hoặc giao thức authenticated key establishment được chuẩn hóa**, cùng thư viện đã được đánh giá, hơn là sao chép code demo làm protocol production.

---

## 8. TLS 1.3: Chống phát lại handshake và giới hạn 0-RTT

### 8.1. Handshake TLS 1.3 thông thường

TLS 1.3 ràng buộc key schedule và Finished vào transcript handshake. Các key shares, phiên bản, thuật toán và thông điệp xác thực được bảo vệ theo thiết kế protocol; một Finished từ phiên khác không thể tùy tiện dùng làm Finished của phiên mới.

Nhưng không nên kết luận từ đó rằng:

- **Mọi ClientHello cũ** đều bị chặn ở byte đầu tiên (attacker vẫn có thể gửi để gây tải).
- **Mọi thao tác ứng dụng** trong kết nối TLS đều tự có idempotency.
- Bất kỳ client certificate hợp lệ nào cũng được phép gọi mọi API.
- Việc sử dụng TLS tự ngăn lệnh thanh toán bị client hợp lệ gửi lặp.

TLS quản lý **bảo mật kênh và các thuộc tính handshake**; ứng dụng vẫn phải kiểm tra principal/permission/action và trạng thái nghiệp vụ.

### 8.2. Vì sao TLS 1.3 0-RTT là ngoại lệ đáng chú ý?

Khi dùng session resumption, TLS 1.3 có thể cho gửi **early data (0-RTT)** trước khi hoàn thành handshake theo cách thông thường. Early data có **rủi ro replay** và các biện pháp anti-replay của TLS không tạo bảo đảm tuyệt đối như việc ứng dụng ghi nhận một thao tác đã xử lý.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Attacker
    participant S as Server
    Note over C: Có resumption PSK/ticket hợp lệ
    C->>S: ClientHello và 0-RTT POST /capture
    Note over A: Ghi lại early data
    Note over S: Có thể xử lý sớm theo policy
    A->>S: Replay ClientHello và early data
    Note over S: Không có anti-replay ứng dụng có thể xử lý lặp
~~~

**Khuyến nghị ứng dụng:**

- Không cho phép 0-RTT đối với chuyển tiền, thu phí, tạo hoặc hủy giao dịch có tác động nếu chưa bảo vệ replay đầy đủ.
- Ưu tiên chỉ dùng early data cho các request đọc/không có side effect theo policy; kể cả request đọc vẫn cần xem ảnh hưởng tới quota, log và cache.
- Sử dụng cơ chế anti-replay chính thức của TLS stack và phân tích giới hạn multi-node.
- Với hành động có side effect, dùng **idempotency key** và kiểm tra transaction state **ở phía server**.

TLS 1.3 đã hoàn tất vẫn không tự làm cho một HTTP POST thành đúng một lần, vì client hợp lệ có thể tự gửi lại hoặc hệ thống retry do mất response.

---

## 9. KEM, HPKE, ECDH và key transport: Khác biệt replay

| Cơ chế | Có thể bị replay ở đâu? | Kiểm soát thêm |
|---|---|---|
| **Unauthenticated ECDH** | Attacker dùng lại public key hoặc MITM; không có identity trust | Authenticated transcript, identity/role binding, key confirmation |
| **Authenticated ephemeral ECDH** | ClientHello cũ, stale proof nếu state/nonce sai, replay application data | Challenge mới, signature trên transcript, Finished, sequence |
| **RSA-OAEP key transport** | Encrypted DEK cũ có thể được gửi lại | Sender auth, recipient binding, operation ID, policy đã xử lý |
| **KEM-based exchange** | Encapsulation ciphertext cũ có thể được decapsulate lại | Fresh context/KDF, peer auth, replay state |
| **HPKE** | Valid ciphertext/message có thể được dùng lại theo application protocol | Mode phù hợp, operation/state và chống replay ngoài primitive |
| **TLS 1.3 0-RTT** | Early data trong resumption có nguy cơ replay | TLS anti-replay measures cộng kiểm soát idempotency |

### 9.1. Forward secrecy không đồng nghĩa anti-replay

**Forward secrecy** trong giao thức ephemeral được xác thực bảo vệ bí mật khóa phiên lịch sử trong một mô hình lộ long-term key nhất định. Nó **không tự bảo đảm mọi packet cũ bị từ chối**.

Một protocol có forward secrecy vẫn có thể có replay request nếu thiếu sequence/operation state. Ngược lại, một hệ thống key transport có replay cache tốt không tự đạt forward secrecy đối với ciphertext lịch sử.

### 9.2. Nonce khác nhau ở những lớp khác nhau

- **Handshake nonce:** dùng để tạo freshness/bind phiên.
- **AES-GCM IV/nonce:** yêu cầu không dùng trùng dưới cùng key khi encrypt.
- **Request nonce:** dùng ghi nhận request đã xử lý, phối hợp TTL/replay cache.
- **Business operation ID:** bảo vệ ngữ nghĩa nghiệp vụ khi retry hoặc gửi lặp.

Không thay thế một cơ chế bằng cơ chế khác chỉ vì chúng đều có tên "nonce" hoặc "ID".

---

## 10. Timestamp, sequence number, replay cache và idempotency

| Biện pháp | Vai trò chính | Sai lầm thường gặp |
|---|---|---|
| Server challenge | Chứng minh response thuộc phiên mới | Server không nhớ challenge đang chờ |
| Random nonce | Phân biệt sự kiện, giảm khả năng lặp ngoài ý muốn | Chỉ do sender tự chọn rồi phát lại vô hạn |
| Timestamp | Giới hạn thời gian chấp nhận | Replay vẫn xảy ra trong cửa sổ |
| Sequence number | Kiểm tra thứ tự/đã nhận của record | Counter bị reset khi restart/rollback |
| Replay cache | Đánh dấu proof/session/request đã xử lý | Cache mỗi pod hoặc check-then-insert không atomic |
| Idempotency ledger | Chặn lặp side effect | Lưu ID nhưng không ràng buộc principal và payload |
| Key version | Chọn đúng key theo vòng đời | Cho rằng đổi key ID tự chứng minh proof mới |

### 10.1. Một replay window cho datagram

~~~text
Session S, chiều Client -> Server
Highest received sequence = 105
Window cho phép [42..105]

seq=105: đã nhận -> từ chối bản sao
seq=104: chưa nhận -> có thể chấp nhận gói đến muộn
seq=20: quá cũ -> từ chối
seq=106: mới -> cập nhật highest và bitmap
~~~

Khi dùng giao thức hỗ trợ gói đến sai thứ tự, replay window có thể cần bitmap/sliding window, phân tách rõ từng phiên, chiều và key. Cần bảo vệ state khi failover. Không áp máy móc mô hình datagram lên TLS/TCP record layer vì các chuẩn đã có cơ chế riêng.

### 10.2. Replay cache phải có tính nguyên tử

Thiết kế sai:

~~~text
if (!store.exists(sessionId)) {
    processHandshake();
    store.put(sessionId);
}
~~~

Hai pod đồng thời có thể cùng thấy "chưa có" rồi cùng thực hiện.

Thiết kế tốt hơn:

~~~text
accepted = atomicPutIfAbsent(principal + sessionId, TTL)
if (!accepted) rejectReplay()
else continueAccordingToStateMachine()
~~~

Nhưng thời điểm **claim** cũng phải đúng. Không nên cho attacker chiếm trước những nonce/challenge hợp lệ bằng message chưa qua xác thực; cần xác minh bằng chứng cần thiết và kiểm soát DoS trước khi đánh dấu trạng thái.

### 10.3. Idempotency là trách nhiệm ứng dụng

Một request thanh toán được ký đúng và gửi trong phiên TLS hợp lệ có thể bị gửi lại do network retry. Ứng dụng phải duy trì:

~~~text
(principal, operationId) -> payloadDigest, status, result
~~~

Nếu cùng operation ID và cùng payload được gửi lại, có thể trả kết quả đã lưu. Nếu cùng ID nhưng nội dung khác, phải coi là conflict. Side effect và claim ID nên được đồng bộ bằng transaction/state machine phù hợp để tránh xử lý trùng khi crash.

---

## 11. Vai trò của KMS/HSM và vòng đời khóa

KMS/HSM giúp bảo vệ **private signing key, KEK** và có thể sinh DEK; nhưng nó **không tự biết handshake nào mới** hoặc request ứng dụng nào đã xử lý.

~~~mermaid
flowchart TD
    App["Application handshake"] --> Auth["Identity/role validation"]
    Auth --> KMS["KMS/HSM Sign hoặc Decrypt theo policy"]
    KMS --> Proof["Signature hoặc vật liệu khóa được phép"]
    Proof --> T["Transcript và key confirmation"]
    T --> State["Session/replay state"]
    State --> Gate["Authorization nghiệp vụ"]
    Gate --> Data["AEAD/DEK và giao dịch"]
    KMS --> Audit["Audit key operations"]
~~~

### 11.1. Kiểm soát theo vòng đời

| Giai đoạn | Rủi ro replay | Yêu cầu |
|---|---|---|
| **Sinh khóa** | RNG yếu làm lặp nonce/ephemeral keys | CSPRNG/HSM đáng tin, không clone state |
| **Cấp phát** | Sai key-to-identity mapping | PKI/trust registry, IAM và quyền theo mục đích |
| **Thiết lập phiên** | Chấp nhận proof cũ | Fresh challenge, transcript, Finished, state |
| **Sử dụng** | Replay ciphertext/request sau handshake | Sequence, nonce tracking, idempotency |
| **Rotation** | Key version cũ còn chấp nhận proof cũ | Policy hiệu lực, proof expiry, key version |
| **Thu hồi** | Session/traffic key cũ vẫn sống | Session invalidation, cache TTL, revoke policy |
| **Hủy** | Snapshot/backup khôi phục state đã tiêu thụ | Anti-rollback và recovery plan |

### 11.2. Disable KMS key có đủ để chống replay không?

Không. Nếu khóa ký dài hạn bị disable, một **session đã thiết lập trước** có thể vẫn giữ traffic keys và tiếp tục truyền dữ liệu cho đến khi bị đóng theo chính sách. Nếu raw private key bị lộ, attacker có thể tiếp tục tạo chữ ký bên ngoài KMS.

Ứng cứu cần xem cả **credential/key rotation, session revocation, replay cache, application tokens, IAM và audit**.

### 11.3. DEK/KEK và envelope encryption là lớp khác

Trong envelope encryption:

~~~text
KMS KEK -> wrap/unwrap DEK
DEK     -> AES-GCM mã hóa dữ liệu
Handshake traffic key -> bảo vệ dữ liệu trên kênh phiên
~~~

Đây là các khóa có **mục đích và vòng đời khác nhau**. Không dùng DEK lưu trữ làm traffic key hoặc Finished key; không kết luận rewrap một DEK đã ngăn phát lại phiên TLS hay HTTP.

Nếu attacker khôi phục một bản wrapped DEK/ciphertext cũ, **AEAD tag vẫn có thể hợp lệ**. Chống rollback bản ghi đòi hỏi version hoặc checkpoint đáng tin ngoài vùng có thể bị thay thế.

---

## 12. Các lỗi triển khai dễ gặp

| Sai lầm | Hậu quả | Cách phòng |
|---|---|---|
| Ký message cố định không có challenge | Chữ ký cũ dùng lại được | Ký transcript có nonce/phiên |
| Chỉ đưa client nonce vào proof | Server stateless có thể chấp nhận proof cũ | Server challenge hoặc used-nonce state |
| Không bind identities và roles | UKS/reflection/nhầm peer | Xác thực đầy đủ transcript |
| Không bind thuật toán/phiên bản | Có thể tạo cơ hội downgrade | Signed negotiation và allowlist |
| Không bind ephemeral key shares | Key substitution/MITM | Đưa key shares vào transcript |
| Không tách Finished keys hai chiều | Reflection/cross-protocol confusion | HKDF domain separation |
| Chỉ verify chữ ký, bỏ key confirmation cần thiết | Không chứng minh peer biết shared secret đúng | Finished MAC theo session |
| Dùng timestamp đơn độc | Replay trong khoảng chấp nhận | Nonce replay cache/idempotency |
| Tin AES-GCM IV chống replay | Record cũ vẫn decrypt được | Sequence/used-ID ledger |
| Replay cache ở từng pod | Đi qua pod khác để gửi lại | Shared atomic store hoặc thiết kế tương đương |
| Xóa cache khi restart mà không epoch/version | Bản tin cũ có thể được chấp nhận lại | Persistence và anti-rollback |
| Dùng lại ephemeral private keys sau VM snapshot | Nguy cơ lặp shared secret/nonce | Reseed, fresh state, theo chuẩn |
| Public key lấy từ packet không tin cậy | Attacker tự ký và tự xác nhận | PKI/trust registry |
| Signing key HSM có quyền quá rộng | Attacker chiếm workload để tạo proof hợp lệ mới | IAM, approval và audit |
| Bật 0-RTT cho payment POST | Request early data có thể bị replay | Tắt 0-RTT hoặc anti-replay ứng dụng |
| Không xử lý concurrent idempotency | Hai request song song đều thực hiện nghiệp vụ | Transaction/conditional claim |
| Rotate signing key nhưng vẫn nhận proof không hết hạn | Cửa sổ replay vẫn tồn tại | Expiry, nonce state, phiên bản và revoke |

---

## 13. Case study: Payment Service gọi Ledger Service

### 13.1. Bối cảnh

Một doanh nghiệp có nhiều pod Java 17. **Payment Service** khởi tạo các thao tác **Capture**, **Refund**; **Ledger Service** xử lý ghi sổ. Các bên dùng TLS 1.3/mTLS và KMS/HSM để bảo vệ signing keys, KEK và DEK dữ liệu.

Yêu cầu:

- Chỉ workload có chứng thư/identity được phép mới bắt tay thành công.
- Không dùng transcript/Finished cũ để nhận session mới.
- Một lệnh **Capture** chỉ được tạo side effect một lần dù client retry.
- Không làm mất chống replay khi pod restart, load balancing hoặc failover.
- Có audit nhưng không lộ session secret/DEK.

### 13.2. Thiết kế theo lớp

**Lớp kết nối:** TLS 1.3/mTLS chuẩn; xác minh chain/tên dịch vụ/workload identity; cân nhắc chính sách 0-RTT phù hợp.

**Lớp ứng dụng:** ánh xạ danh tính mTLS thành principal và quyền từng tenant/merchant/operation.

**Lớp idempotency:** duy trì bản ghi **(principal, operationId, payloadDigest, status, result)** bằng transaction hoặc conditional write. Với cùng ID và payload khác phải trả conflict.

**Lớp dữ liệu:** AES-GCM với DEK được quản lý đúng; wrapped DEK do KMS bảo vệ; quyền đọc dữ liệu và audit tách biệt.

**Lớp vận hành:** metric handshake/Finished failures, replay attempts, stale proof, operation duplicates; giám sát KMS và sự kiện rotate/revoke.

~~~mermaid
sequenceDiagram
    participant P as Payment
    participant L as Ledger
    participant DB as Operation Store
    participant K as KMS
    P->>L: mTLS/TLS 1.3 + Capture(opId, data)
    Note over L: Verify principal, tenant và authorization
    L->>DB: Atomic claim principal + opId + payload hash
    alt Đã xử lý cùng payload
        DB-->>L: Stored result
        L-->>P: Trả kết quả idempotent
    else Cùng ID, khác payload
        DB-->>L: Conflict
        L-->>P: Từ chối
    else Thao tác mới
        DB-->>L: Claimed
        L->>K: Dùng key dữ liệu theo IAM nếu cần
        L->>DB: Commit transaction + result
        L-->>P: Kết quả giao dịch
    end
~~~

Việc claim và commit side effect phải có **quy trình retry, recovery, trạng thái trung gian và transaction** phù hợp; không để crash sau claim khiến giao dịch mắc kẹt vô hạn hay bị chạy lại mà không biết.

### 13.3. Kiểm thử bắt buộc

| Kịch bản | Điều phải quan sát |
|---|---|
| Replay ClientHello cũ | Không tự tạo authentication thành công với proof cũ |
| Replay signature/Finished của phiên trước | Không hợp lệ dưới transcript/key mới |
| Hai pod nhận cùng Capture đồng thời | Chỉ một side effect theo transaction |
| Cùng operationId, payload khác | Từ chối conflict |
| Replay ciphertext AEAD cũ | Sequence/operation state từ chối nếu giao thức yêu cầu |
| Restore VM/pod | Không lặp RNG state hoặc khôi phục quyền nhận proof cũ |
| TLS 0-RTT cho POST có tác động | Không xử lý sớm thiếu idempotency/anti-replay |
| KMS bị lỗi | Không fallback sang key mặc định hay bypass xác thực |
| Khóa signing bị thu hồi | New sessions bị xử lý theo policy; rà sessions cũ |
| Đồng hồ lệch | Thời hạn proof được kiểm soát, không mở cửa sổ quá rộng |

### 13.4. Audit nên lưu gì?

~~~text
time, principal, peerService, protocolVersion, cipherSuite,
sessionIdHash, keyVersion, handshakeDecision, replayDecision,
operationId, payloadDigest, idempotencyResult, traceId
~~~

Không log raw secret, X25519 private/shared secret, traffic keys, HMAC keys, DEK, bearer token hoặc dữ liệu tài chính nhạy cảm. Session ID/hash phải được xử lý theo chính sách logging và quyền riêng tư.

---

## 14. Runbook khi phát hiện replay hoặc lỗi freshness

### 14.1. Phát hiện và khoanh vùng

Các dấu hiệu:

- Nhiều transcript hash hoặc session IDs lặp từ nguồn không mong đợi.
- Finished verification failures tăng cao theo service/region.
- Replay cache liên tục nhận duplicate hoặc bị reset khi scale-out.
- Tỷ lệ request trùng operation ID vượt dự kiến.
- Lưu lượng TLS 0-RTT bất thường trên endpoint có side effect.
- VM restore hoặc DR event trùng với việc xuất hiện session/nonce cũ.
- KMS/HSM Sign/Decrypt calls bất thường.

Phải phân biệt **attempt**, **authentication thành công** và **business impact**. Không quy mọi handshake retry hợp lệ thành tấn công.

### 14.2. Hành động ứng cứu

1. Xác định protocol, endpoint, key IDs, phiên bản, môi trường và khoảng thời gian.
2. Bảo toàn log/traces/chứng cứ cần thiết mà không ghi raw key.
3. Kiểm tra challenge/session state và cache TTL, atomic operations, replication.
4. Tạm giới hạn endpoint hoặc tắt 0-RTT cho thao tác nhạy cảm khi cần.
5. Kiểm tra operation ledger để phát hiện side effect bị chạy lặp.
6. Nếu có dấu hiệu lộ private key hoặc yếu entropy, thay khóa/credential, đóng phiên và đánh giá dữ liệu chịu ảnh hưởng.
7. Khắc phục nonce/ephemeral lifecycle, rollback và multi-region consistency.
8. Bổ sung kiểm thử concurrent replay, restart/restore, clock skew và KMS outage.

**Đừng xóa sạch replay cache giữa sự cố mà không có chiến lược khác:** xóa trạng thái used-nonce có thể làm proof cũ trở lại hợp lệ nếu thời hạn chấp nhận chưa hết. Có thể cần đổi epoch/key và vô hiệu hóa những proof cũ.

---

## 15. Checklist production

### Cryptographic protocol

- [ ] Dùng TLS 1.3/mTLS hoặc giao thức thiết lập khóa chuẩn với thư viện đáng tin.
- [ ] Không coi ECDH, RSA-OAEP hay KEM riêng lẻ là giao thức authentication/replay hoàn chỉnh.
- [ ] Có client/server freshness phù hợp và server kiểm tra challenge hiện hành.
- [ ] Bind identities, roles, suite, protocol version, ephemeral key shares và key purpose vào transcript.
- [ ] Chữ ký/MAC được xác minh bằng đúng key-to-principal mapping đáng tin.
- [ ] Dùng HKDF/key schedule có labels tách chiều, tách mục đích.
- [ ] Có key confirmation/Finished phù hợp.
- [ ] Không lặp ephemeral secret hoặc nonce sai khi clone/snapshot/restart.

### Replay state và ứng dụng

- [ ] Challenge/session state có expiry, tiêu thụ/claim đúng quy tắc.
- [ ] Replay cache dùng atomic writes và chia sẻ theo phạm vi cần thiết.
- [ ] TTL và capacity có giới hạn; chống DoS và failover.
- [ ] State chống rollback được bảo vệ khi khôi phục.
- [ ] Sequence/window được quản lý đúng chiều và đúng session nếu record protocol cần.
- [ ] Phân biệt replay handshake với replay dữ liệu ứng dụng.
- [ ] Idempotency cho thao tác có side effect và transaction xử lý retry.
- [ ] TLS 0-RTT được vô hiệu hóa hoặc có kiểm soát replay phù hợp cho API nhạy cảm.
- [ ] Có authorization theo principal/tenant/operation sau khi xác thực.

### Key management và vận hành

- [ ] KMS/HSM/IAM phân quyền Sign, Decrypt, GenerateDataKey theo workload.
- [ ] Không dùng chung DEK lưu trữ với traffic/Finished keys.
- [ ] Rotation/revocation xem xét cả session đang sống và bằng chứng cũ.
- [ ] Có audit các lần auth fail, replay reject, cache reset và IAM changes.
- [ ] Test đồng thời nhiều pod, restart, snapshot, network retry, clock skew.
- [ ] Có runbook ứng cứu nếu key/nonce bị lộ, HSM không sẵn sàng hoặc duplicate side effect.
- [ ] Không log private key, traffic secrets, KMS raw key hay plaintext nhạy cảm.

---

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao một chữ ký số hợp lệ vẫn có thể bị replay?

**Gợi ý:** chữ ký chỉ chứng thực những byte nó đã ký. Nếu không chứa challenge phiên hiện tại, attacker có thể gửi lại byte và chữ ký cũ.

**Câu 2.** Một ClientHello cũ bị phát lại có nghĩa attacker đã xác thực thành công không?

**Gợi ý:** không nhất thiết. Server có thể gửi challenge mới, đòi hỏi proof/Finished của phiên mới; tuy vậy vẫn có chi phí DoS.

**Câu 3.** Nonce nào của một lần bắt tay giúp server chứng minh client đang phản hồi đúng phiên mới?

**Gợi ý:** server nonce/challenge do server vừa tạo và đã được ràng buộc vào chứng cứ xác thực của client.

**Câu 4.** Nếu chỉ ký hai public keys X25519 mà bỏ identity/role/suite, có vấn đề gì?

**Gợi ý:** có thể nhầm danh tính hoặc role và gặp UKS/reflection/downgrade tùy protocol. Transcript cần đủ context được xác thực.

**Câu 5.** Key confirmation dùng để làm gì?

**Gợi ý:** chứng minh peer có khả năng sử dụng shared secret/key phiên tương ứng, thường bằng Finished MAC trên transcript.

**Câu 6.** Replaying một KEM encapsulation ciphertext có tự bị KEM primitive phát hiện không?

**Gợi ý:** không tự động. Cần freshness/replay state ở giao thức và ứng dụng.

**Câu 7.** Nonce AES-GCM không lặp khi encrypt có tự ngăn replay nguyên ciphertext cũ không?

**Gợi ý:** không. Ciphertext cũ vẫn có thể giải mã hợp lệ; cần sequence/used-ID state.

**Câu 8.** Tại sao TLS 1.3 0-RTT không thích hợp mặc định cho POST chuyển tiền?

**Gợi ý:** early data có thể bị phát lại, dẫn tới side effect lặp nếu ứng dụng thiếu idempotency.

**Câu 9.** Replay cache trong RAM từng pod có đủ khi load balancer gửi hai bản sao sang hai pod khác nhau?

**Gợi ý:** không. Cần shared atomic state hoặc cơ chế tương đương được phân tích đúng.

**Câu 10.** Forward secrecy có đồng nghĩa chống replay không?

**Gợi ý:** không. Nó bảo vệ bí mật phiên lịch sử trong mô hình lộ key nhất định, khác với điều kiện chấp nhận bản tin.

**Câu 11.** Rotate private signing key ở KMS có xóa nguy cơ replay request nghiệp vụ cũ không?

**Gợi ý:** không tự động. Session/credentials cũ, proof window và idempotency state vẫn phải quản lý.

**Câu 12.** Khi phát hiện hai request cùng operation ID được xử lý trùng, phải xem xét những lớp nào?

**Gợi ý:** credential/authentication, handshake/0-RTT, request signing, atomic idempotency ledger, transaction và failover.

---

## 17. Kết luận

**Replay trong key establishment** xảy ra khi thông điệp hoặc chứng cứ của một lần thiết lập khóa trước đó bị xử lý như bằng chứng của phiên mới. Một chữ ký hoặc MAC **đúng về mặt mật mã** có thể vẫn không đủ nếu giao thức không kiểm tra **freshness và ràng buộc phiên**.

Thiết kế an toàn cần kết hợp **challenge/nonces mới, authenticated transcript, identity/role binding, KDF tách mục đích, key confirmation, replay state** và xử lý đúng vòng đời khóa. **TLS 1.3/mTLS** là lựa chọn thực tế cho nhiều dịch vụ, nhưng không thay thế **idempotency và authorization** của ứng dụng; đặc biệt phải thận trọng với **0-RTT early data**.

KMS/HSM giúp bảo vệ private keys, KEK/DEK và audit thao tác mật mã, nhưng không tự theo dõi mọi handshake đã dùng hoặc thao tác nghiệp vụ đã thực hiện. Chống replay chỉ hoàn chỉnh khi phối hợp **mật mã, trạng thái, quyền truy cập, vòng đời khóa và vận hành**.

### Tài liệu tham khảo

- **RFC 8446** — *The Transport Layer Security (TLS) Protocol Version 1.3*: transcript, Finished, key schedule, 0-RTT và replay limitations.
- **RFC 8470** — *Using Early Data in HTTP*: hướng dẫn và giới hạn xử lý early data.
- **RFC 9180** — *Hybrid Public Key Encryption (HPKE)*: KEM, KDF, AEAD và mode.
- **RFC 5869** — *HMAC-based Extract-and-Expand Key Derivation Function (HKDF)*.
- **NIST SP 800-56A Rev. 3** — *Pair-Wise Key-Establishment Schemes Using Discrete Logarithm Cryptography*.
- **NIST SP 800-56B Rev. 2** — *Pair-Wise Key-Establishment Schemes Using Integer Factorization Cryptography*.
- **NIST SP 800-57 Part 1** — *Recommendation for Key Management*: vòng đời và chính sách khóa.
- **OWASP Transport Layer Security Cheat Sheet**, **OWASP Key Management Cheat Sheet**.
