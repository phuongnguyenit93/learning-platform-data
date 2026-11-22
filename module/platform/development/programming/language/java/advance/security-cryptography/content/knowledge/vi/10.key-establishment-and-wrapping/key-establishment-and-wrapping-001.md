# 10.1 Phân biệt trao đổi khóa, thỏa thuận khóa, bọc khóa và đóng gói khóa

## Mục tiêu

Khi xây dựng một ứng dụng Java dùng AES-GCM, TLS, kho khóa hoặc mã hóa tài liệu cho người nhận, bạn cần biết **bí mật được tạo ra hay đã tồn tại**, **bên nào sở hữu khóa**, **thứ gì được truyền qua mạng** và **API nào giải quyết đúng bài toán**. Bốn thuật ngữ dễ lẫn là *trao đổi khóa* (key exchange), *thỏa thuận khóa* (key agreement), *bọc khóa* (key wrapping) và *đóng gói khóa* (key encapsulation, KEM).

Bài này là **bản đồ khái niệm và lựa chọn cơ chế**: học cách nhận diện yêu cầu trước khi triển khai, hiểu đường đi của khóa và những bảo đảm còn thiếu. Các thao tác chuyên sâu được trình bày trong các bài riêng về DH/ECDH/X25519/X448, vòng đời `KeyAgreement`, HKDF, xác thực đối tác, `Cipher.WRAP_MODE`, API KEM Java 21 và thiết kế giao thức.

Sau khi đọc, bạn cần phân loại được một hệ thống theo **key có sẵn hay key mới**, **khóa đối xứng hay bất đối xứng**, **người gửi/nhận biết gì**, và **xác thực danh tính nằm ở bước nào**.

## 1. Bốn khái niệm không đồng nghĩa

| Thuật ngữ | Câu hỏi mà cơ chế giải quyết | Vật liệu bí mật | Đầu ra nổi bật | Java API điển hình |
| --- | --- | --- | --- | --- |
| **Key exchange — trao đổi khóa** | Làm thế nào hai đầu thiết lập được khóa để giao tiếp? | Tùy giao thức; có thể phối hợp nhiều primitive | Các khóa phiên và bằng chứng theo giao thức | Một chuỗi `KeyAgreement`, `KEM`, KDF, chữ ký/MAC, AEAD |
| **Key agreement — thỏa thuận khóa** | Hai bên có thể **tự tính chung một secret** từ private key của mình và public key đối tác không? | Mỗi bên có private key riêng; không gửi secret | **Raw shared secret** (thường đưa qua KDF) | `javax.crypto.KeyAgreement` |
| **Key wrapping — bọc khóa** | Làm thế nào bảo vệ **một khóa đã tồn tại** để lưu/chuyển nó? | Data Encryption Key (DEK) đã có; Key Encryption Key (KEK) hoặc khóa nhận được phép | **Wrapped key bytes**, mở ra lại key cũ | `Cipher.WRAP_MODE`, `Cipher.UNWRAP_MODE`, AESWrap/KMS |
| **Key encapsulation — đóng gói khóa/KEM** | Làm sao sender dùng public key recipient tạo **shared secret mới** để recipient khôi phục? | Recipient giữ private key; sender tạo secret mới nội bộ | **Secret + encapsulation bytes** | `javax.crypto.KEM` (**Java 21+**) |

**Key exchange** thường là tên của **mục tiêu hoặc một giao thức đầy đủ**. Nó có thể sử dụng key agreement, KEM, vận chuyển/bọc khóa hoặc nhiều thành phần cùng lúc. Không nên dịch “key exchange” thành tên riêng duy nhất của Diffie–Hellman.

**Key agreement** dùng đóng góp của *hai phía*, thí dụ X25519/ECDH. **Key wrapping** xuất phát từ *một DEK đã có* và bảo vệ nó dưới KEK. **KEM encapsulation** tạo **secret mới** và **thông điệp đóng gói** cho public key của người nhận; nó không có phương thức mặc định để nhận một DEK tùy ý làm input. Đây là điểm phân biệt quan trọng nhất khi đọc API Java.

## 2. Gọi đúng tên các loại khóa

- **DEK (Data Encryption Key):** khóa dùng để mã hóa **nội dung** của file hoặc bản ghi, ví dụ AES-256 cho AES-GCM.
- **KEK (Key Encryption Key):** khóa dùng để **wrap/unwrap DEK**; thường được quản lý bởi Key Management Service (KMS), Hardware Security Module (HSM) hoặc một hệ thống key hierarchy.
- **Public/private key pair:** cặp khóa bất đối xứng dùng cho DH, KEM, RSA transport hoặc chữ ký, tùy thuật toán. Private key phải được bảo vệ; public key **có thể công khai nhưng phải xác thực đúng chủ sở hữu** trước khi tin.
- **Raw shared secret:** kết quả của DH hoặc bí mật do KEM khôi phục; đây là **vật liệu dẫn xuất khóa**, chưa mặc nhiên là AES key cho một phiên.
- **Session/traffic key:** khóa đã được dẫn xuất cho một thuật toán, chiều truyền, phiên bản và ngữ cảnh cụ thể; ví dụ client→server AES-GCM key.

Một secret dài 32 byte **không mặc nhiên** là AES-256 key phù hợp về mặt giao thức. Cần thiết kế **KDF** như HKDF với context/labels, đồng thời xác minh nguồn key và bảo vệ việc tái sử dụng khóa/nonce. Đừng lấy raw secret hoặc một wrapped blob rồi trực tiếp biến nó thành dữ liệu gửi cho client nếu chưa hiểu tính chất của cơ chế.

## 3. Key agreement: hai bên tự tính cùng bí mật

Mô hình X25519 hai bên:

~~~text
Alice                            Mạng                             Bob
private a, public A                                               private b, public B

        A ----------------------->                                  |
        | <------------------------ B                               |
        |                                                           |
Z_A = X25519(a, B)                                     Z_B = X25519(b, A)
                  Z_A == Z_B, nếu đúng khóa và tham số
        |                                                           |
    HKDF(context)                                             HKDF(context)
        |                                                           |
          traffic key giống nhau theo từng vai trò/nhãn
~~~

Alice và Bob **không truyền Z** qua mạng. Mỗi phía chỉ gửi public key theo định dạng quy định, rồi dùng private key **của chính mình** kết hợp với public key đối tác.

Java dùng state machine:

~~~java
// Snippet trong phương thức có PrivateKey myPrivate,
// PublicKey peerPublic và xử lý GeneralSecurityException.
KeyAgreement agreement = KeyAgreement.getInstance("X25519");
agreement.init(myPrivate);
agreement.doPhase(peerPublic, true);
byte[] rawSecret = agreement.generateSecret();
~~~

- Với hai bên, `doPhase(peerPublic, true)` đánh dấu pha cuối.
- `generateSecret()` trả **secret bytes**, không tự mã hóa payload, không chứng minh peer là ai và không áp KDF theo mục đích.
- DH hữu hạn cần nhóm `p, g` tin cậy và tương thích; ECDH P-256 cần đúng curve; X25519/X448 là nhóm thuật toán/format khác, không hoán đổi bừa bãi.
- Phải kiểm tra key encoding, type/curve/group, public input theo provider/chuẩn, và **xác thực peer identity** từ trust anchor/pinning/chữ ký/giao thức.

Nếu một người ở giữa tráo public key, cả hai phía vẫn có thể tính secret **với attacker** mà API không báo lỗi. X25519 giải bài toán tính toán bí mật, **không tự giải bài toán tin cậy danh tính**.

## 4. Key transport và key wrapping: DEK được chọn trước

Giả sử một file đã được mã hóa bằng DEK. Ứng dụng cần lưu file lâu dài nhưng không thể lưu DEK dạng thô cùng ciphertext:

~~~text
DEK được sinh ngẫu nhiên
     |                    +---------------------------+
     +--> AES-GCM(file) -> | dataCiphertext + tag      |
     |                    +---------------------------+
     |
     +--> AES-KW(KEK, DEK) --> wrappedDEK
                               |
                        lưu kèm keyId, phiên bản
                               |
                được cấp quyền --> unwrap bằng KEK --> DEK cũ
~~~

Đây là **envelope encryption**. `AESWrap` (AES Key Wrap, RFC 3394) bảo vệ **key bytes**; nó không có AAD cho metadata như tenant, record ID hoặc thời hạn. Trường hợp đầu vào dài không phù hợp AES-KW có thể cần AESWrapPad (AES-KWP) nếu provider hỗ trợ. Các field metadata phải được **ràng buộc/kiểm tra ở lớp record/giao thức**.

Trong Java, `Cipher.WRAP_MODE` và `UNWRAP_MODE` là **chế độ hoạt động**, chưa phải tên thuật toán:

~~~java
// Snippet với SecretKey kek và SecretKey dek có sẵn:
Cipher wrap = Cipher.getInstance("AESWrap");
wrap.init(Cipher.WRAP_MODE, kek);
byte[] wrappedDek = wrap.wrap(dek);

Cipher unwrap = Cipher.getInstance("AESWrap");
unwrap.init(Cipher.UNWRAP_MODE, kek);
Key originalDek = unwrap.unwrap(
        wrappedDek, "AES", Cipher.SECRET_KEY);
~~~

Ở lệnh `unwrap(...)`, `"AES"` là **thuật toán của khóa được khôi phục**, khác với thuật toán bọc `"AESWrap"`. Với software key, `getEncoded()` có thể trả raw bytes; với HSM/KMS, key có thể **non-extractable** và phải thao tác qua provider/key handle. Đừng cố export KEK chỉ để dùng đoạn demo.

**Key transport** chỉ trường hợp bên gửi **chọn một DEK trước** rồi chuyển nó cho người nhận đã xác thực, ví dụ mã hóa DEK bằng public key RSA của người nhận theo **RSA-OAEP**. Bên nhận dùng private key tương ứng để khôi phục. Đây cũng là một cách *bảo vệ/vận chuyển khóa đã có*, nhưng khác key agreement và KEM: sender chọn key trước và không cần một phép đóng góp DH tạm từ cả hai bên.

**RSA-OAEP và AESWrap bảo vệ khóa, không tự chứng minh người gửi là ai.** Người biết RSA public key đều có thể mã hóa một DEK cho người nhận. Với lưu trữ, phải phân quyền unwrap, quản lý KEK, rotation/rewrap và chống tráo key giữa object/tenant. Với truyền nhận, phải xác thực **đúng public key recipient**.

## 5. KEM: secret mới, thông điệp encapsulation công khai

KEM dùng public key người nhận để tạo **hai kết quả**:

~~~text
Recipient Bob: (pkR, skR)
                       |
Sender Alice: Encap(pkR)
             /          \
  sharedSecret_A      encapsulation = enc   ---> Bob
       (BÍ MẬT)               (CÔNG KHAI)       |
                                              Decap(skR, enc)
                                                    |
                                               sharedSecret_B

                    sharedSecret_A == sharedSecret_B
~~~

- **Secret:** không gửi, không log; cần đưa qua **KDF theo ngữ cảnh** để lấy key thực sự dùng cho AES-GCM/MAC.
- **Encapsulation (hay KEM ciphertext):** dữ liệu công khai cần gửi; với **DHKEM trên X25519**, nó thường là biểu diễn **ephemeral public key** theo định dạng KEM (32 byte), **không phải raw secret** hoặc ciphertext file.
- KEM không tự mã hóa nội dung lớn, không tự xác thực sender và không chống replay. Base-mode KEM cho **bất kỳ ai có pkR** tạo thông điệp gửi recipient.
- Java 21 mới có `javax.crypto.KEM`. Java 17 có `KeyAgreement` X25519 nhưng không tự có `KEM` hoặc quy tắc DHKEM của RFC 9180.

Snippet Java 21+:

~~~java
// Snippet: public key Bob phải được xác thực trước.
// recipientPublic: PublicKey, recipientPrivate: PrivateKey.
KEM kem = KEM.getInstance("DHKEM");
KEM.Encapsulated result =
        kem.newEncapsulator(recipientPublic).encapsulate();
SecretKey localSecret = result.key();        // giữ bí mật
byte[] message = result.encapsulation();     // gửi cho Bob

SecretKey recipientSecret =
        kem.newDecapsulator(recipientPrivate)
           .decapsulate(message);
~~~

Đừng dùng `message` làm key AES dù nó có thể có cùng độ dài với secret; đây là **public transport data**. Một message KEM đủ độ dài nhưng bị sửa có thể làm bên nhận sinh **secret khác**, không nhất thiết ném exception. Khi dùng KEM → KDF → AEAD, **tag AEAD** mới phải xác nhận payload và AAD; một KEM hợp lệ không đương nhiên có sender authentication.

## 6. Một chương trình Java 21 so sánh ba cơ chế trên cùng dữ liệu thử

Chương trình dưới đây chỉ thử **hình dạng đầu vào/đầu ra** của KeyAgreement, AES Key Wrap và DHKEM, giúp thấy một thao tác tạo secret, một thao tác bảo vệ key **đã có**, và một thao tác tạo secret cùng encapsulation. Chương trình không tạo giao thức mạng, không dẫn xuất traffic key, không xác minh danh tính và không dùng key để mã hóa payload. Trong sản phẩm thực, ưu tiên giao thức tiêu chuẩn, KDF và AEAD đúng thiết kế.

Tạo file **MechanismComparisonDemo.java**:

~~~java
import java.security.Key;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KEM;
import javax.crypto.KeyAgreement;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class MechanismComparisonDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator x = KeyPairGenerator.getInstance("X25519");
        KeyPair alice = x.generateKeyPair();
        KeyPair bob = x.generateKeyPair();

        // 1. Agreement: private của mình + public của đối tác.
        KeyAgreement a = KeyAgreement.getInstance("X25519");
        a.init(alice.getPrivate());
        a.doPhase(bob.getPublic(), true);
        byte[] za = a.generateSecret();

        KeyAgreement b = KeyAgreement.getInstance("X25519");
        b.init(bob.getPrivate());
        b.doPhase(alice.getPublic(), true);
        byte[] zb = b.generateSecret();
        System.out.println("Agreement secret equal: "
                + MessageDigest.isEqual(za, zb));

        // 2. Wrap: bảo vệ chính một DEK đã có bằng KEK.
        KeyGenerator aes = KeyGenerator.getInstance("AES");
        aes.init(128);
        SecretKey dek = aes.generateKey();
        SecretKey kek = aes.generateKey();
        Cipher wrapper = Cipher.getInstance("AESWrap");
        wrapper.init(Cipher.WRAP_MODE, kek);
        byte[] wrapped = wrapper.wrap(dek);

        Cipher unwrapper = Cipher.getInstance("AESWrap");
        unwrapper.init(Cipher.UNWRAP_MODE, kek);
        Key restored = unwrapper.unwrap(
                wrapped, "AES", Cipher.SECRET_KEY);
        System.out.println("Wrap restores old DEK: "
                + MessageDigest.isEqual(
                        dek.getEncoded(), restored.getEncoded()));

        // 3. KEM: tạo secret mới và encapsulation công khai.
        KeyPair recipient = x.generateKeyPair();
        KEM kem = KEM.getInstance("DHKEM");
        KEM.Encapsulated enc =
                kem.newEncapsulator(recipient.getPublic()).encapsulate();
        SecretKey received =
                kem.newDecapsulator(recipient.getPrivate())
                   .decapsulate(enc.encapsulation());
        System.out.println("KEM secret equal: "
                + MessageDigest.isEqual(
                        enc.key().getEncoded(), received.getEncoded()));
        System.out.println("KEM message present: "
                + (enc.encapsulation().length > 0));

        Arrays.fill(za, (byte) 0);
        Arrays.fill(zb, (byte) 0);
    }
}
~~~

Chạy bằng **JDK 21+** có provider hỗ trợ DHKEM/X25519 và AESWrap:

~~~bash
javac --release 21 -encoding UTF-8 MechanismComparisonDemo.java
java MechanismComparisonDemo
~~~

Stdout:

~~~text
Agreement secret equal: true
Wrap restores old DEK: true
KEM secret equal: true
KEM message present: true
~~~

Kết quả này chứng minh **ba contract API khác nhau** trong một tiến trình. `Arrays.fill` chỉ giảm thời gian tồn tại của các mảng tự sở hữu; không chứng minh xóa mọi secret bên trong provider/JVM. `getEncoded()` được dùng trong demo với khóa phần mềm xuất được; HSM/provider có thể trả `null`. Chưa có xác thực danh tính, key confirmation, nonce, chống replay hoặc policy, nên không coi đoạn mã là một secure channel.

## 7. Chọn cơ chế theo bài toán thực tế

| Yêu cầu | Cơ chế thường phù hợp | Điều phải làm thêm |
| --- | --- | --- |
| Hai service cần tự thiết lập bí mật phiên trên kết nối | Key agreement/KEM **bên trong giao thức chuẩn** như TLS 1.3 | Xác thực danh tính, transcript, KDF, traffic keys, nonce, policy |
| Một bên đã tạo AES-DEK và cần Bob có lại đúng key đó | Key transport, RSA-OAEP hoặc wrap qua KEK phù hợp | Xác thực đúng public key/key owner, metadata, quyền |
| Mã hóa file lớn và lưu key dài hạn | DEK + AEAD, bọc DEK dưới KEK trong KMS/HSM | Key ID, quyền unwrap, rotation/backup, tenant/object binding |
| Gửi file cho recipient có public key, tạo session secret mới | KEM + KDF + AEAD; cân nhắc HPKE | Xác thực recipient, sender auth khi yêu cầu, replay, wire format |
| Thay KEK mà vẫn giữ DEK | Unwrap/rewrap DEK | Quyền KMS, cập nhật phiên bản nguyên tử và rollback policy |
| Giao tiếp tương thích nhiều ngôn ngữ/provider | Một protocol/suite đã đặc tả và test vectors | Định dạng public key, OAEP parameters, HKDF info, AEAD AAD/nonce |

**Cần xác thực public key ở cả key agreement, KEM và public-key transport.** Nếu attacker tráo public key, bạn có thể chia sẻ secret hoặc bọc DEK **cho chính attacker** dù phép toán hoàn tất hợp lệ. Certificate, pin đáng tin, chữ ký trên transcript và các cơ chế được giao thức chuẩn hóa mới ràng buộc khóa với identity.

## 8. Những điều dễ nhầm và hậu quả

1. **“Key exchange = thuật toán DH duy nhất.”** Sai: đây là mục tiêu/giao thức, có thể kết hợp nhiều primitive.
2. **“Shared secret X25519 đủ dài nên dùng trực tiếp làm mọi AES/MAC key.”** Thiếu KDF và key-purpose/role separation.
3. **“Wrap và encapsulate đều mã hóa một DEK chọn trước.”** Không: wrap nhận key có sẵn, còn KEM mặc định sinh secret mới.
4. **“Encapsulation 32 byte là AES-256 key.”** Không: dù cùng kích thước, encapsulation là dữ liệu công khai.
5. **“AESWrap có AAD tenant giống AES-GCM.”** Không: AES-KW xác thực key material theo thuật toán riêng, metadata cần cơ chế khác.
6. **“Nhận public key là đã biết người gửi.”** Không: phải kiểm chứng nguồn/danh tính; base KEM không xác thực sender.
7. **“Bọc DEK thành công tức ciphertext file đã xác thực.”** Không: file cần tag/MAC theo thuật toán mã hóa payload.
8. **“Có secret chung là không thể bị MITM.”** Không: kẻ đứng giữa có thể lập hai phiên thỏa thuận với khóa của mình.
9. **“Java 17 có KEM vì đã có X25519.”** Không: API `javax.crypto.KEM` xuất hiện từ Java 21.
10. **“SecretKey.getEncoded() luôn cho bytes.”** Không: khóa trong HSM/KMS có thể non-extractable.
11. **“DHKEM + HKDF + AES-GCM tự viết = HPKE chuẩn.”** Không: HPKE còn định nghĩa key schedule, suite, mode, record context và serialization.
12. **“Wrapped key hợp lệ không thể bị tráo sang file khác.”** Không: cần authorization, policy, record binding và chống replay/rollback.

## 9. Bài tập tự kiểm tra

**1.** Một file đã có DEK AES-256. Cần bảo vệ DEK trong KMS để sau này mở đúng DEK cũ. Cơ chế nào phù hợp, và vì sao KEM không phải một lời gọi `encapsulate(existingDek)`?

**2.** Alice và Bob tạo cùng bí mật bằng X25519. Dữ liệu nào được gửi qua mạng, và bước nào còn thiếu để Alice biết đó thật sự là Bob?

**3.** Đối với một thông điệp KEM, phần nào được gửi công khai, phần nào giữ bí mật và phần nào là ciphertext của dữ liệu ứng dụng?

**4.** Tại sao `unwrap(bytes, "AES", SECRET_KEY)` yêu cầu chuỗi `"AES"` dù transformation đã là `"AESWrap"`?

**5.** Nếu recipient RSA private key dài hạn bị lộ, dữ liệu khóa được vận chuyển bằng RSA-OAEP trước đây có thuộc tính forward secrecy mặc nhiên không? Giải thích.

**6.** Một DEK được unwrap hợp lệ nhưng người dùng không thuộc tenant của bản ghi. Hệ thống có được phép giải mã và trả plaintext không? Lớp nào phải từ chối?

**7.** Một encapsulation DHKEM bị sửa nhưng có độ dài hợp lệ. Vì sao chỉ kiểm exception của `decapsulate()` chưa đủ để bảo vệ payload?

**8.** Khi nào nên dùng TLS/HPKE được kiểm chứng thay vì tự ghép `KeyAgreement`, `KEM`, `Cipher` và HKDF?

## 10. Checklist triển khai

- [ ] Xác định key **sinh mới** hay **đã có**; cần trao đổi secret, bảo vệ DEK hay mã hóa payload.
- [ ] Chọn đúng primitive và API, ghi rõ JDK version, provider, thuật toán và key types.
- [ ] Public key người nhận/peer phải được xác thực theo policy; raw shared secret phải qua KDF phù hợp.
- [ ] Bảo vệ payload bằng AEAD với nonce/tag/AAD đúng; bọc khóa không thay xác thực dữ liệu.
- [ ] Với DEK/KEK, quản lý key ID, quyền wrap/unwrap, HSM/KMS, rewrap, backup và rotation.
- [ ] Chống MITM, replay, downgrade và nhầm context bằng **giao thức đã đặc tả và được kiểm thử**, không chỉ một phép toán thành công.
- [ ] Không log private key, shared secret, traffic key, KEK/DEK; kiểm tra provider có key non-exportable hay không.
- [ ] Test lỗi sai key/suite, public key bị thay, tampered capsule/ciphertext, metadata tráo và phiên bản không được phép.

## Tài liệu chuẩn

- [Java SE 17 — KeyAgreement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyAgreement.html)
- [Java SE 17 — Cipher wrap/unwrap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html)
- [Java SE 21 — KEM API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html)
- [RFC 7748 — X25519/X448](https://www.rfc-editor.org/rfc/rfc7748)
- [RFC 3394 — AES Key Wrap](https://www.rfc-editor.org/rfc/rfc3394)
- [RFC 5869 — HKDF](https://www.rfc-editor.org/rfc/rfc5869)
- [RFC 9180 — HPKE KEM/KDF/AEAD](https://www.rfc-editor.org/rfc/rfc9180)
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446)
