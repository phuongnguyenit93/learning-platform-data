# KeyAgreement

KeyAgreement là API trong Java Cryptography Architecture (JCA) dùng để hai hoặc nhiều bên phối hợp tính ra một bí mật chung qua kênh truyền không an toàn mà không gửi trực tiếp bí mật đó qua mạng. Cơ chế thường gặp là Diffie-Hellman (DH) và Elliptic Curve Diffie-Hellman (ECDH). Hai bên dùng private key của mình và public key của đối phương để tính cùng một shared secret.

Trong module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, KeyAgreement minh họa cách tạo vật liệu khóa dùng chung và vì sao phải quản lý khóa tạm thời, xác thực danh tính, dẫn xuất khóa và bảo vệ kết quả. Shared secret là đầu vào cho Key Derivation Function (KDF); ứng dụng thường dẫn xuất khóa mã hóa hoặc khóa xác thực từ đó theo giao thức đã thiết kế.

## 1. Key agreement giải quyết vấn đề gì?

Giả sử hai dịch vụ Alice và Bob cần một khóa đối xứng để mã hóa dữ liệu trao đổi. Nếu Alice tạo khóa rồi gửi trực tiếp cho Bob, kẻ nghe lén trên mạng có thể lấy được khóa. Nếu dùng KeyAgreement, mỗi bên tạo một key pair. Họ trao đổi public key, sau đó mỗi bên kết hợp private key của mình với public key của đối phương để tính ra cùng một shared secret.

~~~mermaid
sequenceDiagram
    participant A as Alice
    participant N as Kênh mạng
    participant B as Bob
    A->>A: Tạo key pair (private A, public A)
    B->>B: Tạo key pair (private B, public B)
    A->>N: Gửi public A
    N->>B: Chuyển public A
    B->>N: Gửi public B
    N->>A: Chuyển public B
    A->>A: ECDH(private A, public B)
    B->>B: ECDH(private B, public A)
    Note over A,B: Hai bên tính được cùng shared secret
~~~

Kẻ nghe lén chỉ nhìn thấy các public key và thông điệp trao đổi. Với thuật toán và tham số an toàn, họ không thể tính shared secret nếu không biết một private key tương ứng. Đây là cơ sở của nhiều giao thức thiết lập khóa như TLS.

Key agreement tạo ra bí mật chung; nó không tự mã hóa dữ liệu ứng dụng, không tự xác minh danh tính peer và không tự quyết định thời hạn sử dụng khóa. Các bước đó thuộc giao thức và chính sách quản lý khóa ở lớp cao hơn.

## 2. Diffie-Hellman và ECDH

### Diffie-Hellman (DH)

DH cổ điển dựa trên bài toán logarit rời rạc trong một nhóm hữu hạn. Hai bên sử dụng cùng tham số nhóm công khai, gồm modulus và generator, rồi mỗi bên chọn một số bí mật riêng. Họ trao đổi giá trị công khai được tính từ số bí mật và tham số nhóm. Mỗi bên dùng bí mật của mình cùng giá trị công khai nhận được để tính ra cùng một shared secret.

DH cần tham số nhóm đủ mạnh và được xác thực/kiểm tra phù hợp. Dùng nhóm yếu, tham số không hợp lệ hoặc tái sử dụng private key dài hạn trong thiết kế không phù hợp có thể làm giảm mức bảo vệ.

### Elliptic Curve Diffie-Hellman (ECDH)

ECDH thực hiện ý tưởng tương tự trên nhóm điểm của đường cong elliptic. Mỗi bên có một private scalar và public key là điểm tương ứng trên đường cong. Hai bên kết hợp private scalar của mình với public point của peer để tính ra cùng một điểm bí mật; phần biểu diễn bí mật được dùng làm đầu vào cho KDF.

ECDH thường đạt mức bảo vệ tương đương với DH cổ điển bằng kích thước khóa nhỏ hơn, nhưng cần chọn curve được chuẩn hóa và được nền tảng hỗ trợ. Ví dụ phổ biến là secp256r1 (P-256). Không nên tự định nghĩa curve hoặc tự triển khai phép toán elliptic curve.

### Các lựa chọn hiện đại

X25519 là cơ chế trao đổi khóa dựa trên đường cong Montgomery, thường được sử dụng trong các giao thức hiện đại. Trong JCA, XDH là tên dịch vụ KeyAgreement có thể dùng với NamedParameterSpec.X25519 hoặc NamedParameterSpec.X448 từ Java 11 trở lên, nếu provider hỗ trợ. Tên thuật toán và khả năng hỗ trợ cần được kiểm tra theo phiên bản Java và provider thực tế.

| Cơ chế | Nền tảng toán học | Tên dịch vụ JCA thường gặp | Lưu ý |
|---|---|---|---|
| DH | Logarit rời rạc trong nhóm hữu hạn | DiffieHellman | Cần tham số nhóm mạnh và tương thích ở cả hai bên |
| ECDH | Nhóm điểm elliptic curve | ECDH | Chọn curve chuẩn và kiểm tra public key |
| X25519/X448 | Elliptic curve Diffie-Hellman theo RFC 7748 | XDH | Cần JDK/provider hỗ trợ và cấu hình đúng named parameter |

Lựa chọn cuối cùng nên theo giao thức, tiêu chuẩn mật mã và yêu cầu tương thích. Không được tự thay thuật toán hoặc tham số giữa hai đầu kết nối nếu giao thức không cho phép.

## 3. Các bước của KeyAgreement trong JCA

Lớp javax.crypto.KeyAgreement cung cấp quy trình thiết lập bí mật chung. Với trao đổi hai bên, các bước cơ bản là:

1. Tạo hoặc nạp key pair phù hợp với thuật toán và tham số đã thỏa thuận.
2. Tạo đối tượng KeyAgreement bằng getInstance.
3. Khởi tạo đối tượng bằng private key của bên hiện tại qua init.
4. Đưa public key của peer vào doPhase với tham số lastPhase bằng true cho pha cuối trong trao đổi hai bên.
5. Gọi generateSecret để lấy shared secret.
6. Đưa shared secret qua KDF để tạo khóa sử dụng cho mục đích cụ thể.

~~~mermaid
flowchart TD
    A[KeyPairGenerator hoặc kho khóa] --> B[Key pair của bên hiện tại]
    C[Public key đã xác minh của peer] --> E[KeyAgreement.doPhase]
    B --> D[KeyAgreement.init với private key]
    D --> E
    E --> F[KeyAgreement.generateSecret]
    F --> G[Shared secret]
    G --> H[KDF với salt và context]
    H --> I[Khóa ứng dụng: AES/HMAC]
~~~

Các lỗi thường gặp được thể hiện qua exception:

- NoSuchAlgorithmException: provider không hỗ trợ tên thuật toán yêu cầu.
- InvalidKeyException: private key hoặc public key không hợp lệ, không tương thích hoặc không được provider chấp nhận.
- IllegalStateException: gọi sai thứ tự trạng thái, chẳng hạn generateSecret trước khi hoàn tất pha cần thiết.

Không nên bỏ qua exception rồi tiếp tục dùng một khóa rỗng hoặc khóa mặc định. Nếu không thiết lập được shared secret, phiên trao đổi phải thất bại an toàn.

## 4. Ví dụ ECDH với Java

Ví dụ sau tạo hai key pair EC dùng cùng curve secp256r1. Alice và Bob tính shared secret độc lập, rồi so sánh kết quả để minh họa rằng hai bên thu được cùng giá trị. Trong ứng dụng thật, public key của peer phải được xác thực bằng giao thức phù hợp trước khi dùng.

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.spec.ECGenParameterSpec;
import javax.crypto.KeyAgreement;

public class EcdhExample {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(new ECGenParameterSpec("secp256r1"));

        KeyPair alice = generator.generateKeyPair();
        KeyPair bob = generator.generateKeyPair();

        KeyAgreement aliceAgreement = KeyAgreement.getInstance("ECDH");
        aliceAgreement.init(alice.getPrivate());
        aliceAgreement.doPhase(bob.getPublic(), true);
        byte[] aliceSecret = aliceAgreement.generateSecret();

        KeyAgreement bobAgreement = KeyAgreement.getInstance("ECDH");
        bobAgreement.init(bob.getPrivate());
        bobAgreement.doPhase(alice.getPublic(), true);
        byte[] bobSecret = bobAgreement.generateSecret();

        if (!MessageDigest.isEqual(aliceSecret, bobSecret)) {
            throw new SecurityException("Key agreement failed");
        }

        System.out.println("Both parties derived the same secret.");
    }
}
~~~

Ví dụ chỉ minh họa phép toán. Nó không phải giao thức trao đổi khóa hoàn chỉnh vì public key được lấy trực tiếp từ đối tượng của bên kia trong cùng tiến trình, không được truyền và xác thực qua mạng. Không in shared secret ra log, console hoặc telemetry.

Trong triển khai thực tế, mỗi bên cần tạo key pair với nguồn ngẫu nhiên an toàn. Với ECDH, hai key pair phải sử dụng cùng curve và provider phải hỗ trợ các key tương ứng. Public key nhận từ mạng cần được xác minh định dạng, tham số và nguồn gốc theo giao thức.

## 5. Vì sao không dùng trực tiếp shared secret làm khóa AES?

generateSecret() trả về byte của bí mật chung theo cách biểu diễn do thuật toán/provider quy định. Không nên mặc định lấy trực tiếp mảng byte này làm khóa AES, HMAC hoặc nhiều mục đích khác. Cần dùng KDF để biến shared secret thành khóa có độ dài, phân tách mục đích và ngữ cảnh rõ ràng.

KDF thường nhận:

- **Input keying material (IKM):** shared secret từ KeyAgreement.
- **Salt:** giá trị bổ sung cho quá trình dẫn xuất; tùy KDF, salt có thể công khai và được trao đổi trong giao thức.
- **Info/context:** nhãn mô tả mục đích, giao thức, phiên, danh tính hoặc hướng truyền dữ liệu.
- **Output length:** số byte khóa cần dẫn xuất.

HKDF (HMAC-based Extract-and-Expand Key Derivation Function, RFC 5869) là một lựa chọn phổ biến khi giao thức yêu cầu KDF dựa trên HMAC. Trong Java, API KDF cụ thể phụ thuộc JDK/provider hoặc thư viện mật mã được chọn; không giả định mọi phiên bản JDK đều có sẵn HKDF chuẩn. Hãy dùng thư viện/provider được duy trì và tuân thủ chính xác đặc tả giao thức.

Ví dụ về ý tưởng dẫn xuất:

~~~text
sharedSecret = KeyAgreement(privateKey, peerPublicKey)
prk = HKDF-Extract(salt, sharedSecret)
clientToServerKey = HKDF-Expand(prk, "protocol-v1 client-to-server", 32)
serverToClientKey = HKDF-Expand(prk, "protocol-v1 server-to-client", 32)
~~~

Hai nhãn context khác nhau tạo hai khóa độc lập về mặt mục đích, dù chúng bắt nguồn từ cùng một shared secret. Cách phân tách này giúp tránh dùng một khóa cho cả hai chiều hoặc nhiều chức năng khác nhau. Salt và context phải được tạo/định nghĩa theo giao thức để cả hai bên dẫn xuất đúng cùng kết quả.

Không tự thiết kế KDF bằng cách nối chuỗi tùy tiện hoặc chỉ băm shared secret một lần. Cần dùng KDF chuẩn và tham số được giao thức quy định.

## 6. Key agreement không tự xác thực peer

Public key của DH/ECDH có thể được gửi công khai. Nếu không có cơ chế xác thực, kẻ tấn công đứng giữa có thể thay public key của Alice bằng public key của mình khi gửi cho Bob và làm điều tương tự theo chiều ngược lại. Khi đó, kẻ tấn công thiết lập một shared secret với Alice và một shared secret khác với Bob, rồi chuyển tiếp dữ liệu giữa hai bên.

Đây là tấn công man-in-the-middle (MITM). Cả Alice và Bob đều có thể tính ra một shared secret hợp lệ về mặt toán học nhưng không chia sẻ cùng một bí mật với đúng peer mà họ nghĩ đang giao tiếp.

Các cách xác thực thường dùng:

- **Chữ ký số và chứng chỉ:** ký thông tin trao đổi khóa tạm thời, xác minh chữ ký bằng public key đã được tin cậy và kiểm tra danh tính trong chứng chỉ.
- **Pre-shared key (PSK):** dùng bí mật đã chia sẻ từ trước để xác thực handshake theo giao thức.
- **Authenticated key exchange:** dùng giao thức đã được thiết kế để kết hợp trao đổi khóa và xác thực, chẳng hạn TLS 1.3.
- **Out-of-band verification:** xác minh fingerprint hoặc mã xác thực qua một kênh độc lập trong những hệ thống có mô hình phù hợp.

Không nên chỉ kiểm tra chữ ký của một public key bất kỳ. Chữ ký phải bao phủ đúng thông tin trao đổi, danh tính, tham số và ngữ cảnh phiên theo giao thức; nếu không, thông điệp có thể bị phát lại hoặc ghép nhầm phiên.

## 7. Ephemeral key và forward secrecy

Ephemeral key là key pair tạm thời được tạo cho một phiên hoặc một khoảng thời gian ngắn. Trong ECDHE, mỗi bên tạo cặp khóa EC tạm thời, trao đổi public key và tính shared secret. Sau khi handshake hoàn tất, private key tạm thời được loại bỏ theo khả năng của triển khai.

Nếu mỗi phiên dùng khóa tạm thời độc lập và private key tạm thời được hủy sau khi hoàn tất, việc lộ private key dài hạn dùng để xác thực trong tương lai không nhất thiết làm lộ các shared secret phiên đã ghi lại trước đó. Đây là cơ sở của forward secrecy (bí mật chuyển tiếp).

Forward secrecy phụ thuộc vào thiết kế giao thức và vòng đời khóa:

- Private key tạm thời phải được tạo mới theo chính sách phiên, không tái sử dụng kéo dài.
- Private key tạm thời cần được loại bỏ sau khi không còn cần thiết.
- Khóa dài hạn dùng để ký/xác thực không được thay thế vai trò của ephemeral key trong trao đổi khóa.
- Phiên phải được xác thực đúng cách để chống MITM.

Chỉ gọi KeyAgreement không tự tạo ra forward secrecy. Nếu ứng dụng tái sử dụng private key tĩnh trong mọi phiên hoặc lưu lại private key tạm thời quá lâu, lợi ích này có thể mất.

## 8. Quản lý và xác thực public key nhận được

Public key không cần giữ bí mật, nhưng cần bảo đảm tính xác thực và hợp lệ. Một public key nhận từ mạng có thể bị thay thế, sai tham số hoặc không thuộc danh tính mong muốn.

Tùy thuật toán và giao thức, cần kiểm tra:

- Public key có đúng loại và thuật toán được thỏa thuận không.
- Tham số curve hoặc nhóm DH có nằm trong danh sách được phép không.
- Key có hợp lệ theo quy tắc của thuật toán/provider không.
- Chứng chỉ hoặc chữ ký gắn public key với đúng danh tính không.
- Thông tin trao đổi có được ràng buộc với phiên, vai trò và thuật toán đã đàm phán không.

Với ECDH, không tự giải mã hoặc tái tạo public point bằng phép toán tùy tiện. Dùng KeyFactory, KeySpec và provider chuẩn để đọc/kiểm tra key encoding. Một số thuật toán như X25519 có quy tắc xử lý đầu ra đặc biệt, ví dụ cần loại bỏ shared secret toàn số 0 theo RFC 7748; hãy dùng provider và giao thức tuân thủ đặc tả, đồng thời kiểm tra lỗi thay vì tự bỏ qua.

## 9. Tích hợp KeyAgreement với TLS và ứng dụng

Trong TLS 1.3, các bộ mật mã thông dụng sử dụng ephemeral Diffie-Hellman (ECDHE) hoặc PSK kết hợp DH để thiết lập bí mật phiên. TLS handshake còn xác thực server/client theo chế độ cấu hình, ràng buộc các thông điệp vào transcript và dẫn xuất nhiều traffic key riêng cho từng hướng truyền.

Ứng dụng Java thường không cần tự viết handshake TLS bằng KeyAgreement. Hãy dùng JSSE (Java Secure Socket Extension), SSLContext và thư viện TLS được duy trì. KeyAgreement phù hợp khi xây dựng giao thức mật mã chuyên biệt có đặc tả và đánh giá bảo mật đầy đủ; nếu không, việc tự xây dựng handshake dễ bỏ sót xác thực, chống phát lại, key confirmation và phân tách khóa.

Trong một thiết kế ứng dụng, luồng tổng quát có thể là:

1. Xác thực danh tính peer qua chứng chỉ, PSK hoặc cơ chế đã chọn.
2. Thỏa thuận thuật toán và tham số key agreement theo allowlist.
3. Tạo khóa tạm thời và trao đổi public key đã được xác thực.
4. Tính shared secret bằng KeyAgreement.
5. Dẫn xuất các khóa độc lập bằng KDF theo context phiên.
6. Dùng khóa đã dẫn xuất với AEAD như AES-GCM hoặc ChaCha20-Poly1305 theo giao thức.
7. Quản lý nonce, sequence number, key confirmation, rekey và kết thúc phiên.
8. Loại bỏ private key tạm thời và shared secret khi không còn cần thiết.

## 10. Liên hệ với KMS/HSM và vòng đời khóa

KeyAgreement tạo ra vật liệu bí mật nên cần được đưa vào quy trình quản lý khóa:

- **Tạo khóa:** dùng KeyPairGenerator và SecureRandom của JCA/provider tin cậy; chọn thuật toán, curve hoặc nhóm theo chính sách.
- **Cấp phát và trao đổi:** chỉ công bố public key qua giao thức; xác thực public key peer trước khi đưa vào phép tính.
- **Sử dụng:** giới hạn shared secret trong phạm vi phiên; dẫn xuất khóa riêng cho từng mục đích và hướng truyền.
- **Lưu trữ:** tránh lưu private key ephemeral và shared secret lâu dài. Nếu dùng private key dài hạn để xác thực, lưu trong kho được bảo vệ hoặc HSM/KMS theo yêu cầu.
- **Xoay vòng:** tạo key pair mới theo phiên hoặc cryptoperiod; cập nhật khóa xác thực dài hạn theo chính sách.
- **Thu hồi:** khi khóa xác thực hoặc chứng chỉ bị lộ, thu hồi credential, thay key pair và xác minh lại peer.
- **Hủy:** loại bỏ dữ liệu bí mật trong bộ nhớ theo khả năng của runtime; không ghi shared secret vào log, dump hoặc telemetry.

Một số HSM/KMS hỗ trợ thao tác DH/ECDH hoặc provider PKCS#11 có thể cung cấp KeyAgreement. Khả năng cụ thể phụ thuộc thiết bị, firmware, provider và chính sách. Việc private key không thể xuất khỏi HSM không đồng nghĩa shared secret hoặc khóa dẫn xuất sẽ tự động không rời HSM; cần xác định rõ nơi thực hiện KDF và nơi sử dụng khóa.

Không phải mọi private key đều nên đặt trong HSM. Ephemeral key cho từng phiên có thể được tạo và sử dụng trong bộ nhớ của tiến trình theo mô hình TLS; khóa dài hạn có giá trị cao thường cần bảo vệ tập trung hơn. Quyết định phụ thuộc rủi ro, hiệu năng và yêu cầu vận hành.

## 11. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng KeyAgreement mà không xác thực public key peer | Có thể bị MITM | Dùng TLS hoặc giao thức authenticated key exchange đã được chuẩn hóa |
| Dùng curve/nhóm yếu hoặc không được phê duyệt | Shared secret có thể bị suy ra hoặc public key không an toàn | Chọn tham số được tiêu chuẩn và chính sách cho phép |
| Dùng shared secret trực tiếp làm AES key | Thiếu bước dẫn xuất và phân tách mục đích | Dùng KDF chuẩn như HKDF theo giao thức |
| Dùng cùng một khóa cho cả hai hướng truyền | Tăng nguy cơ nhầm lẫn vai trò và tái sử dụng khóa | Dẫn xuất khóa riêng với context khác nhau |
| Tái sử dụng ephemeral private key quá lâu | Giảm forward secrecy và tăng phạm vi ảnh hưởng khi lộ khóa | Tạo khóa mới theo phiên và hủy sau khi dùng |
| Chấp nhận public key sai định dạng hoặc tham số | Lỗi xử lý hoặc rủi ro tấn công vào phép toán | Kiểm tra key bằng provider và quy tắc giao thức |
| Log shared secret hoặc private key | Làm lộ bí mật phiên hoặc credential | Loại bỏ bí mật khỏi log, trace, dump và telemetry |
| Chia sẻ một KeyAgreement instance giữa các luồng | Trạng thái phiên có thể bị trộn | Tạo instance riêng cho mỗi phép thỏa thuận |

## 12. Checklist triển khai

- [ ] Chọn DH, ECDH hoặc XDH theo giao thức và chính sách mật mã được phê duyệt.
- [ ] Dùng KeyPairGenerator, KeyAgreement và SecureRandom từ JCA/provider tin cậy.
- [ ] Bảo đảm hai bên dùng thuật toán và tham số tương thích.
- [ ] Xác thực public key peer bằng chứng chỉ, chữ ký, PSK hoặc giao thức chuẩn.
- [ ] Kiểm tra public key và tham số trước khi gọi doPhase.
- [ ] Dùng KDF chuẩn để dẫn xuất khóa; không dùng trực tiếp shared secret làm khóa ứng dụng.
- [ ] Phân tách khóa theo mục đích, phiên và hướng truyền bằng context phù hợp.
- [ ] Tạo và hủy ephemeral key theo chính sách để đạt forward secrecy khi giao thức hỗ trợ.
- [ ] Không ghi private key hoặc shared secret vào log, file tạm hay telemetry.
- [ ] Kiểm thử xử lý lỗi, public key không hợp lệ, MITM, replay và xoay vòng khóa.
- [ ] Xác minh khả năng hỗ trợ thực tế của KMS/HSM/provider nếu dùng key agreement trong phần cứng.

KeyAgreement giúp các bên tạo cùng một bí mật mà không truyền bí mật đó qua mạng. Để dùng an toàn, cần xác thực public key peer, chọn tham số mạnh, dẫn xuất khóa bằng KDF, phân tách mục đích và quản lý private key tạm thời theo vòng đời của phiên.
