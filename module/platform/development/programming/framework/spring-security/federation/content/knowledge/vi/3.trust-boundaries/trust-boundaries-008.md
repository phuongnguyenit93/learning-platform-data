# Ranh giới của HTTPS, chữ ký số và mã hóa thông điệp trong Spring Security Federation

## 1. Vì sao SSO cần nhiều lớp bảo vệ?

Trong Single Sign-On (SSO), một ứng dụng (Relying Party – RP trong OpenID Connect, hoặc Service Provider – SP trong SAML) nhận kết quả xác thực do một bên khác (OpenID Provider – OP, hoặc Identity Provider – IdP) phát hành. Thông điệp có thể đi qua trình duyệt, reverse proxy, gateway, mạng công cộng hoặc những dịch vụ backend khác trước khi đến thành phần kiểm tra danh tính.

Bài toán không chỉ là “đường truyền có HTTPS không?”, mà còn là:

1. **Kết nối nào đang được bảo vệ, và ai có thể nhìn thấy dữ liệu khi kết nối kết thúc?**
2. **Ai đã phát hành thông điệp, nội dung nào thực sự được người đó ký, và bên nhận có tin đúng khóa ký không?**
3. **Ai có thể đọc dữ liệu định danh hoặc thuộc tính nhạy cảm bên trong thông điệp?**
4. **Thông điệp hợp lệ về mật mã có được dùng đúng ứng dụng, đúng thời điểm, đúng phiên đăng nhập hay không?**

Ba cơ chế thường bị đánh đồng là **HTTPS/TLS**, **chữ ký số ở mức thông điệp**, và **mã hóa thông điệp**. Chúng bảo vệ các ranh giới khác nhau. Một hệ thống federation an toàn cần sử dụng và kiểm tra chúng theo đúng vai trò, đồng thời ràng buộc kết quả vào ngữ cảnh giao thức.

**Mục tiêu:** giải thích chính xác từng ranh giới tin cậy, so sánh OIDC và SAML 2.0, nhận biết giới hạn ở TLS termination, phân biệt signed/encrypted token, áp dụng trong Spring Security và xử lý được các lỗi cấu hình thực tế.

## 2. Ba ranh giới: đường truyền, nguồn phát hành và người đọc

### 2.1. HTTPS/TLS: bảo vệ *mỗi kết nối truyền tải*

TLS thường cung cấp:

- **Bí mật khi truyền:** người nghe lén trên đường truyền khó đọc được bản rõ của dữ liệu ứng dụng.
- **Toàn vẹn khi truyền:** kẻ ở giữa không thể tùy ý sửa bản ghi TLS mà không bị phát hiện.
- **Xác thực đầu bên kia của kết nối:** trong HTTPS thông thường, client xác minh chứng chỉ/danh tính máy chủ theo hostname và chuỗi tin cậy. TLS hai chiều (*mTLS*) có thể xác thực thêm client.

Giới hạn quan trọng: TLS bảo vệ **kết nối giữa hai TLS endpoint**; khi một endpoint giải mã, endpoint đó thấy bản rõ. Nếu kết nối bị kết thúc tại CDN, API gateway, load balancer hoặc ingress, phía sau nó bắt đầu một **ranh giới tin cậy mới**.

```text
Browser ── HTTPS #1 ──> Reverse proxy ── HTTPS #2 ──> Spring Boot RP
                               │
                         TLS kết thúc;
                         proxy thấy HTTP plaintext
```

Nếu chặng giữa reverse proxy và ứng dụng là HTTP thường, chỉ chặng đầu có bảo vệ TLS. Ngay cả khi cả hai chặng đều dùng HTTPS, proxy trung gian vẫn có thể xem dữ liệu sau khi giải mã chặng thứ nhất. Đây có thể là một thiết kế hợp lệ khi proxy đáng tin cậy, nhưng không tương đương “mã hóa xuyên suốt đến tận RP”.

**Đừng đồng nhất chứng chỉ HTTPS với nguồn phát hành danh tính.** Chứng chỉ TLS của `login.example.org` xác thực máy chủ đang cung cấp kết nối, không tự chứng minh mọi SAML assertion hoặc JWT được trình qua kết nối đó do IdP/OP mà RP tin tưởng ký, càng không chứng minh assertion dành cho RP hiện tại.

### 2.2. Chữ ký số: bảo vệ *nội dung đã ký* và gắn với khóa ký

Với chữ ký bất đối xứng, bên phát hành dùng **private signing key** để ký dữ liệu; bên nhận dùng **public verification key** đã gắn với nhà phát hành tin cậy để kiểm tra chữ ký.

Nếu thuật toán, khóa và quy trình kiểm tra được sử dụng an toàn, chữ ký cho phép phát hiện dữ liệu **nằm trong phạm vi đã ký** bị sửa và chứng minh thông điệp được ký bởi chủ thể kiểm soát khóa tương ứng. Chữ ký **không làm nội dung thành bí mật**: một JWT ký bằng JWS vẫn thường chứa phần payload có thể Base64URL-decode; SAML assertion có chữ ký XML vẫn có thể đọc được.

```text
IdP ký thông điệp bằng private signing key
               │
               ▼
      [payload + signature]
               │
      đi qua browser / proxy
               │
               ▼
RP xác minh bằng public key của IdP được cấu hình tin cậy
  ├─ Nội dung đã ký bị sửa → signature invalid → từ chối
  └─ Signature hợp lệ → tiếp tục kiểm tra issuer, audience,
                         thời gian, response binding, phiên, replay...
```

Chữ ký hợp lệ mới trả lời câu hỏi về **toàn vẹn và khóa ký**, chưa trả lời “ứng dụng này có quyền chấp nhận thông điệp không?”. Không có kiểm tra `aud`/`iss`/`exp` hoặc `InResponseTo`, một chữ ký thật vẫn có thể đi kèm token gửi nhầm bên nhận, token cũ hoặc thông điệp bị phát lại.

**Ranh giới tin cậy của khóa:** nếu RP lấy public key từ một URL do chính token hoặc request chưa tin cậy chỉ định, kẻ tấn công có thể đưa khóa của mình rồi tự ký token. Khóa/metadata phải đến từ issuer hoặc IdP được cấu hình tin cậy, có cơ chế thay khóa và chính sách thuật toán rõ ràng. Giá trị `kid` chỉ giúp chọn khóa trong bộ khóa đã tin cậy, không tự tạo ra sự tin cậy.

### 2.3. Mã hóa thông điệp: giới hạn *ai được đọc payload*

Mã hóa mức thông điệp bảo vệ nội dung ngay cả khi payload đi qua nhiều trung gian. Trong federation thường gặp:

- **SAML XML Encryption:** IdP có thể mã hóa `Assertion` hoặc phần tử nhạy cảm bằng khóa cho SP; SP dùng **private decryption key** của mình để giải mã.
- **JWE (JSON Web Encryption):** đóng gói payload đã mã hóa để chỉ bên nắm khóa giải mã phù hợp có thể đọc. Một ID Token OIDC *có thể* được mã hóa theo thỏa thuận client/OP; không mặc định mọi ID Token đều là JWE.
- **Mã hóa đối xứng có xác thực (AEAD), như AES-GCM:** bảo vệ bí mật và phát hiện sửa đổi đối với ciphertext/dữ liệu liên kết (*AAD*) nếu triển khai đúng, quản lý nonce/IV an toàn.

**Mã hóa để SP đọc không tự chứng minh IdP là người phát hành.** Với mã hóa bất đối xứng dùng public key của SP, nhiều chủ thể có thể mã hóa dữ liệu cho SP nếu có public key này. Vì vậy vẫn cần chữ ký hoặc cơ chế xác thực nguồn phát hành thích hợp. Cũng không được giả định mọi thuật toán “encryption” tự bảo vệ toàn vẹn: phải dùng primitive và cấu hình được xác thực, chống sửa đổi.

## 3. Bảng so sánh để lựa chọn đúng cơ chế

| Câu hỏi bảo mật | HTTPS/TLS | Chữ ký số thông điệp | Mã hóa thông điệp |
| --- | --- | --- | --- |
| Đơn vị được bảo vệ | Một kết nối, một chặng TLS | Chính xác bytes/cấu trúc thuộc phạm vi ký | Nội dung được mã hóa cho một tập bên nhận |
| Người trung gian đọc được bản rõ? | Tại TLS endpoint: có | Thường có, vì ký không che payload | Không, nếu không có khóa giải mã và cấu hình đủ mạnh |
| Phát hiện sửa đổi? | Có trong chặng TLS đó | Có với phần **đã ký** | Có nếu cơ chế mã hóa được xác thực/kiểm tra toàn vẹn |
| Chứng minh ai gửi? | Xác thực peer của TLS, thường là server; tùy mTLS | Xác minh quyền kiểm soát khóa ký gắn với issuer tin cậy | Không tự chứng minh tác giả của bản rõ |
| Sau TLS termination? | Chặng cũ kết thúc, cần chính sách chặng mới | Signature vẫn có thể được kiểm tra cuối hành trình | Ciphertext có thể tiếp tục giữ bí mật đến bên nhận |
| Tự chống replay? | Không bảo vệ logic đăng nhập xuyên phiên | Không | Không |
| Có thay cho kiểm tra audience/issuer/time? | Không | Không | Không |
| Trường hợp điển hình | Browser ↔ IdP, RP ↔ OP Token Endpoint | OIDC signed ID Token, SAML signed Response/Assertion | SAML EncryptedAssertion, OIDC encrypted ID Token nếu yêu cầu |

**Ví dụ dễ nhớ:** HTTP response được truyền qua HTTPS, chứa một SAML assertion đã ký và đã mã hóa. HTTPS bảo vệ từng kết nối, chữ ký giúp SP xác thực nguồn phát hành/phần nội dung được ký, mã hóa giúp che thuộc tính trước trình duyệt và proxy. Không lớp nào tự thay thế `AudienceRestriction`, `Recipient`, thời hạn hoặc chống replay.

## 4. Ranh giới trust khi thông điệp đi qua trình duyệt

Trình duyệt là thành phần điều hướng người dùng, nhưng RP/SP không xem dữ liệu gửi đến từ browser là một bằng chứng xác thực tự thân.

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant RP as RP / SP
    participant IdP as OP / IdP
    B->>RP: Truy cập tài nguyên cần đăng nhập
    RP-->>B: Redirect yêu cầu xác thực (HTTPS)
    B->>IdP: Đến trang đăng nhập (HTTPS)
    IdP-->>B: Kết quả xác thực qua redirect/form POST (HTTPS)
    B->>RP: Chuyển code hoặc SAMLResponse (HTTPS)
    RP->>RP: Kiểm tra state/correlation và chính sách giao thức
    Note over RP,IdP: OIDC code flow có thêm POST /token qua back-channel HTTPS
    RP->>IdP: POST /token (OIDC code flow)
    IdP-->>RP: Token response
    RP->>RP: Xác minh token/chữ ký/claims; tạo phiên RP
```

Sơ đồ gộp hai cơ chế để thấy đường đi; **SAML Web Browser SSO thông thường không có bước POST /token**. Còn OIDC Authorization Code Flow gửi **authorization code** ngắn hạn một lần qua front-channel, không bắt buộc đưa ID Token vào browser trong mô hình ứng dụng có backend.

### Với OIDC

Một ID Token được ký thường là JWS dạng ba phần `BASE64URL(header).BASE64URL(payload).BASE64URL(signature)`. Hai phần đầu có thể được giải mã để xem, **không đồng nghĩa đã xác minh**. RP phải kiểm tra chữ ký đúng key từ OP tin cậy và các claims được yêu cầu, tối thiểu theo luồng: `iss`, `aud`, `exp`, `iat` và `nonce` nếu đã gửi; thêm `azp`, giới hạn thời gian xác thực, v.v. khi điều kiện giao thức đòi hỏi.

Back-channel HTTPS ở Token Endpoint bảo vệ token khi vận chuyển và xác thực endpoint; **nó không thay thế việc xác thực ID Token theo OIDC**. RP không được suy luận “token lấy qua HTTPS là đáng tin” nếu token sai issuer, audience, signature hoặc loại token.

`state` gắn kết response qua browser với request đã tạo; PKCE dùng `code_challenge` và `code_verifier` để ràng buộc việc đổi authorization code; `nonce` (nếu dùng) ràng buộc ID Token với authorization request. Đây là **bảo vệ giao thức**, không phải kiểu khác của chữ ký số hoặc TLS.

### Với SAML 2.0

Web Browser SSO thường dùng Redirect binding để gửi `AuthnRequest` và HTTP-POST binding để trình duyệt chuyển `SAMLResponse` đến **Assertion Consumer Service (ACS)**. Payload HTTP-POST thường được Base64-encode. **Base64 không phải mã hóa bảo mật.**

SP có thể chấp nhận một Response có chữ ký hoặc một Assertion có chữ ký **theo profile và chính sách đã thiết kế**; phải xác minh rằng **chính assertion được dùng để tạo danh tính** nằm trong nội dung có chữ ký hợp lệ. Kiểm tra đủ `Issuer`, `Destination`, `Recipient`, `AudienceRestriction`, `NotBefore`/`NotOnOrAfter`, `InResponseTo` với flow do SP khởi tạo, chính sách signature và replay. Đặc biệt tránh **XML Signature Wrapping**: kiểm tra chữ ký trên một node XML rồi đọc thông tin đăng nhập từ node khác chưa được ký.

Nếu chứa `EncryptedAssertion`, SP cần có khóa giải mã của mình và tiếp tục xác minh chữ ký/điều kiện SAML sau xử lý theo đúng thư viện. Cấu hình khóa giải mã **khác mục đích** với chứng chỉ công khai của IdP được dùng xác minh chữ ký.

## 5. Reverse proxy: HTTPS đúng chặng vẫn có khoảng trống tin cậy

Giả sử deployment:

```text
Internet                 Vùng proxy                   Vùng ứng dụng
Browser ─HTTPS─> Ingress ─HTTP─> Spring Boot RP ─HTTPS─> Identity Provider
                     │                     │
            Giải mã TLS ở ingress    Gọi Token Endpoint
```

- Browser nhìn thấy chứng chỉ HTTPS của ingress, không nhất thiết chứng chỉ của JVM. Ingress có thể thấy cookie, SAMLResponse hoặc code ở dạng bản rõ khi chuyển tiếp.
- Chặng `Ingress → RP` dùng HTTP cần được đánh giá theo bảo vệ mạng và threat model; nếu đi qua mạng không tin cậy, nên tái mã hóa bằng HTTPS, và cân nhắc xác thực service-to-service/mTLS phù hợp.
- Chặng `RP → IdP` là TLS **riêng**, với trust store, DNS, hostname và kiểm tra chứng chỉ riêng; việc browser đăng nhập IdP thành công không chứng minh RP kết nối được Token Endpoint.
- Với SAML/JWS được ký, sự toàn vẹn của nội dung đã ký có thể được xác minh ở RP dù proxy đã giải mã HTTPS. Nhưng proxy có thể **chặn, sao chép, phát lại hoặc thay thế bằng một thông điệp khác có chữ ký hợp lệ**; phải kiểm tra correlation, thời gian, audience và replay.
- Nếu assertion được mã hóa đến SP, proxy không thể tự đọc thuộc tính bên trong khi chỉ nắm TLS key. Tuy vậy proxy vẫn có thể thấy metadata ngoài ciphertext (URL, kích thước, thời điểm, headers, cookies) và có thể chặn/đổi ciphertext.

**Ranh giới quan trọng của forwarded headers:** cấu hình Spring Boot sau ingress có thể phải hiểu `Forwarded` hoặc `X-Forwarded-Proto` để sinh callback HTTPS đúng. Chỉ tin headers do **proxy tin cậy** đặt; không để client Internet tự tạo chúng nhằm thay đổi URL/callback được tính toán. Các giá trị `redirect_uri`, ACS URL, issuer và entity ID phải nhất quán với cấu hình tại OP/IdP.

## 6. Khóa nào dùng vào việc nào?

Trong một liên kết federation, có thể tồn tại nhiều loại chứng chỉ/khóa, dù chúng đều mang tên “certificate” trong dashboard:

| Thành phần | Khóa/chứng chỉ | Bên sở hữu private key | Mục đích |
| --- | --- | --- | --- |
| HTTPS IdP/OP | Chứng chỉ máy chủ TLS | TLS endpoint IdP/OP hoặc proxy của họ | Xác thực hostname và thiết lập kết nối TLS |
| HTTPS RP/SP | Chứng chỉ máy chủ TLS | TLS endpoint của RP/ingress | Bảo vệ kết nối từ browser đến RP |
| OIDC signing | Signing key do OP phát hành qua metadata/JWKS tin cậy | OP | RP xác minh JWS/ID Token của OP |
| SAML signing | Chứng chỉ verify của IdP được RP tin cậy | IdP | SP xác minh XML Signature của Response/Assertion |
| SAML decryption | Chứng chỉ public encryption của SP và private key tương ứng | SP | IdP mã hóa assertion cho SP; SP giải mã |
| SAML AuthnRequest signing (nếu bật) | Khóa ký của SP và certificate public tương ứng | SP | IdP xác minh AuthnRequest đến từ SP |
| mTLS client | Chứng chỉ client và private key | Client của kết nối TLS | Máy chủ peer có thể xác thực client trên kết nối |

Không tráo đổi khóa chỉ vì chúng cùng là `RSA` hay `X.509`. Khóa ký và khóa mã hóa có thể liên quan nhau ở một số triển khai, nhưng **tách khóa theo mục đích** giúp kiểm soát quyền, giảm tác động lộ khóa và đơn giản hóa thay khóa. Kế hoạch rotate JWKS/certificate cần hỗ trợ một giai đoạn có khóa cũ và mới hợp lệ, rồi rút khóa cũ sau khi nội dung/phiên liên quan hết hiệu lực theo chính sách.

**Hệ quả khi lộ khóa:** lộ private key của HTTPS endpoint ảnh hưởng phiên/kết nối tương ứng trong phạm vi threat model; lộ private signing key IdP có thể cho phép giả mạo assertion/token do IdP “ký”; lộ private decryption key SP có thể khiến dữ liệu được mã hóa cho SP bị đọc (nếu ciphertext bị thu thập). Không xử lý ba tình huống như một sự cố giống nhau.

## 7. Ví dụ Java 17: thấy rõ chữ ký và mã hóa có vai trò khác nhau

Đây là chương trình Java SE 17 độc lập minh họa **ECDSA** (ký, xác minh) và **AES-GCM** (mã hóa có xác thực). Mã tạo key mới ngẫu nhiên mỗi lần chạy, không giả lập OP hoặc SP và **không thay thế** thư viện OIDC/SAML của Spring Security.

Lưu thành tệp `MessageBoundaryDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;
import java.util.Arrays;

import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class MessageBoundaryDemo {

    private static byte[] bytes(String value) {
        return value.getBytes(StandardCharsets.UTF_8);
    }

    private static boolean verify(
            PublicKey publicKey, byte[] data, byte[] signature)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance("SHA256withECDSA");
        verifier.initVerify(publicKey);
        verifier.update(data);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        byte[] message = bytes("sub=alice;aud=service-a");

        // 1. Ký bằng private key; xác minh bằng public key.
        KeyPairGenerator keyGenerator = KeyPairGenerator.getInstance("EC");
        keyGenerator.initialize(new ECGenParameterSpec("secp256r1"));
        KeyPair pair = keyGenerator.generateKeyPair();

        Signature signer = Signature.getInstance("SHA256withECDSA");
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        byte[] changed = message.clone();
        changed[0] ^= 1; // Thử sửa nội dung sau khi đã ký.

        System.out.println("signatureValid="
                + verify(pair.getPublic(), message, signature));
        System.out.println("signatureValidAfterChange="
                + verify(pair.getPublic(), changed, signature));

        // 2. Mã hóa có xác thực với AES-GCM.
        KeyGenerator aesGenerator = KeyGenerator.getInstance("AES");
        aesGenerator.init(128);
        SecretKey aesKey = aesGenerator.generateKey();

        byte[] iv = new byte[12]; // 96-bit nonce GCM, phải mới với cùng khóa.
        new SecureRandom().nextBytes(iv);
        byte[] aad = bytes("recipient=service-a");

        Cipher encryptor = Cipher.getInstance("AES/GCM/NoPadding");
        encryptor.init(Cipher.ENCRYPT_MODE, aesKey,
                new GCMParameterSpec(128, iv));
        encryptor.updateAAD(aad);
        byte[] ciphertext = encryptor.doFinal(message);

        Cipher decryptor = Cipher.getInstance("AES/GCM/NoPadding");
        decryptor.init(Cipher.DECRYPT_MODE, aesKey,
                new GCMParameterSpec(128, iv));
        decryptor.updateAAD(aad);
        byte[] restored = decryptor.doFinal(ciphertext);
        System.out.println("plaintextRestored="
                + Arrays.equals(message, restored));

        // 3. Thử sửa ciphertext: GCM kiểm tra authentication tag.
        byte[] tampered = ciphertext.clone();
        tampered[tampered.length - 1] ^= 1;
        Cipher rejector = Cipher.getInstance("AES/GCM/NoPadding");
        rejector.init(Cipher.DECRYPT_MODE, aesKey,
                new GCMParameterSpec(128, iv));
        rejector.updateAAD(aad);
        boolean tamperRejected = false;
        try {
            rejector.doFinal(tampered);
        } catch (AEADBadTagException expected) {
            tamperRejected = true;
        }
        System.out.println("ciphertextTamperRejected=" + tamperRejected);
    }
}
```

Chạy bằng Java 17+:

```bash
javac MessageBoundaryDemo.java
java MessageBoundaryDemo
```

Kết quả standard output (không phụ thuộc vào khóa ngẫu nhiên, vì chỉ in `boolean`):

```text
signatureValid=true
signatureValidAfterChange=false
plaintextRestored=true
ciphertextTamperRejected=true
```

**Đọc kết quả đúng phạm vi:** thay byte trong thông điệp khiến chữ ký không còn hợp lệ; thay ciphertext khiến AES-GCM từ chối giải mã. Nhưng demo không có issuer/audience/expiration/nonce từ một giao thức thực, cũng không thiết lập HTTPS hay phân phối khóa. Trong hệ thống thật, quản lý khóa, IV duy nhất cho **mỗi lần mã hóa với cùng khóa GCM**, xác thực peer và ràng buộc token vào đúng audience vẫn bắt buộc. Không dùng AES-GCM với nonce tái sử dụng cùng key.

## 8. Áp dụng vào Spring Security

### 8.1. OIDC: tin issuer, xác minh ID Token và bảo vệ back-channel

Với Spring Security 6.x / Spring Boot 3.x, backend RP dùng `spring-boot-starter-oauth2-client` và `oauth2Login`. Ví dụ phần khai báo cho OIDC issuer tin cậy:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: YOUR_CLIENT_ID
            client-secret: YOUR_CLIENT_SECRET_FROM_SECRET_STORE
            authorization-grant-type: authorization_code
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
```

Ví dụ là **mẫu cấu hình cần thay giá trị**, chỉ dùng với OP thực có hỗ trợ OIDC discovery tại issuer đã đăng ký. Không commit client secret thật vào YAML. Spring Security sẽ dùng thông tin provider tin cậy để thực hiện các bước OIDC login và xác minh token theo cơ chế của framework; ứng dụng còn phải cấu hình đúng registered redirect URI, phiên, quyền truy cập và proxy.

Một `SecurityFilterChain` tối giản (đoạn mã thuộc ứng dụng Spring Boot đã có cấu hình provider/dependency) minh họa nơi bật cơ chế:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/").permitAll()
                    .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
}
```

Cần import `org.springframework.context.annotation.Bean`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.security.config.Customizer` và `org.springframework.security.web.SecurityFilterChain`. Đây là **một phương thức bean minh họa**, không phải chương trình Java độc lập. Spring OAuth2 Login có sẵn nhiều kiểm tra giao thức và được ưu tiên hơn tự parse JWT. Với ứng dụng có backend, token exchange `POST /token` diễn ra server-to-server; browser thường chỉ thấy redirect qua Authorization Endpoint và callback chứa code.

Khi debug, phân biệt:
- **TLS Token Endpoint lỗi:** lỗi chứng chỉ/hostname, proxy, DNS hoặc timeout xảy ra trước hoặc khi gọi endpoint; chưa có token để xác minh.
- **ID Token signature/claims lỗi:** TLS có thể thành công nhưng issuer/audience/chữ ký/nonce sai; không được “bỏ verify” để qua lỗi.
- **Authentication thành công nhưng quyền không đủ:** phiên/identity hợp lệ chưa đồng nghĩa user có quyền truy cập mọi resource.

Không dùng ID Token để gọi API thay cho Access Token; Access Token dành cho Resource Server phải được kiểm tra theo contract riêng (JWT hoặc opaque token/introspection).

### 8.2. SAML: tách verification credential và decryption credential

Spring Security cung cấp `saml2Login` và `RelyingPartyRegistration`. Tối thiểu, SP cần thông tin IdP/metadata và **verification certificate tin cậy** để xác minh SAMLResponse/Assertion. Khi IdP gửi `EncryptedAssertion`, SP còn cần **decryption credential** (private key và certificate tương ứng).

Khác biệt trong API được minh họa bằng hai phương thức tạo credential; đoạn này thuộc phần cấu hình của Spring, không phải Java SE độc lập:

```java
Saml2X509Credential verifyIdpSignature =
        Saml2X509Credential.verification(idpSigningCertificate);

Saml2X509Credential decryptForSp =
        Saml2X509Credential.decryption(
                spDecryptionPrivateKey,
                spDecryptionCertificate);
```

Ở đây `idpSigningCertificate` là `X509Certificate` tin cậy nhận qua kênh cấu hình IdP, `spDecryptionPrivateKey` là `RSAPrivateKey` được quản lý như secret và `spDecryptionCertificate` là chứng chỉ của SP. Cần nhập `org.springframework.security.saml2.core.Saml2X509Credential`; ví dụ giả định ba đối tượng khóa đã được tải từ kho quản lý khóa bằng cách an toàn.

Trong `RelyingPartyRegistration`, verification credential thuộc cấu hình **asserting party**; decryption credential thuộc **relying party**. Spring Security/OpenSAML chịu trách nhiệm giải mã, kiểm tra chữ ký và điều kiện SAML với cấu hình đúng. Tự “lấy XML node đầu tiên có NameID” hoặc chỉ so chữ ký mà không kiểm tra phần tử được ký mở đường cho XML Signature Wrapping.

**Không dùng certificate TLS của IdP như verification certificate SAML** nếu đối tác không chỉ rõ chúng trùng khóa và được phân phối tin cậy; các khóa có trách nhiệm khác nhau. Tương tự, certificate mã hóa dành cho SP không được coi là certificate ký của IdP.

## 9. Trường hợp thường gặp: có bảo vệ mật mã vẫn không an toàn

### Trường hợp A – HTTPS hợp lệ nhưng nhận sai người dùng

RP nhận một ID Token qua kết nối HTTPS đúng chuẩn. Token có thể do OP thật ký nhưng có `aud` hướng tới một client khác. Nếu RP chỉ thấy chữ ký hợp lệ rồi tạo session, nó đã vượt qua ranh giới đối tượng nhận.

**Cách xử lý:** kiểm tra issuer, audience, client correlation, token type, expiration và nonce theo OIDC; chỉ tin provider/JWKS đã cấu hình. HTTPS không quyết định audience.

### Trường hợp B – SAML ký hợp lệ nhưng assertion được chọn không được bảo vệ

Trong một XML độc hại, có một assertion có chữ ký hợp lệ bên cạnh assertion khác chưa ký. Nếu chương trình kiểm tra chữ ký ở node hợp lệ nhưng dùng identity từ node khác, vẫn có nguy cơ giả mạo.

**Cách xử lý:** dùng OpenSAML/Spring Security kiểm tra phần tử thực sự được sử dụng, áp dụng chính sách signature, validation schema/hardened XML parser và ngăn signature wrapping. Không viết XML signature validator thủ công chỉ để rút ngắn implementation.

### Trường hợp C – Có ký nhưng không mã hóa thuộc tính người dùng

Một `SAMLResponse` được ký được truyền trong HTML form POST qua HTTPS. Browser vẫn có thể thấy payload của chính form sau khi nội dung đã đến browser; Base64 giải mã được thuộc tính.

**Cách xử lý:** khi threat model yêu cầu không tiết lộ assertion cho browser/trung gian, thương lượng `EncryptedAssertion` cho SP và bảo vệ decryption key. Chữ ký không thay thế bảo mật nội dung.

### Trường hợp D – Có mã hóa nhưng không xác minh nguồn phát hành

SP giải mã thành công một payload được mã hóa bằng public key của SP. Vì public key không bí mật, việc giải mã thành công không tự chứng minh IdP phát hành dữ liệu.

**Cách xử lý:** sau giải mã cần xác minh chữ ký từ issuer tin cậy và các điều kiện federation. Nếu dùng AEAD giữa hai bên chia sẻ secret, tag xác thực chứng minh bên tạo biết secret, nhưng vẫn không tự xác định danh tính người dùng hoặc quyền của token.

### Trường hợp E – Signed token thật nhưng bị replay

Attacker sao chép một thông điệp còn hợp lệ và gửi lại vào một callback khác. Signature vẫn hợp lệ; mã hóa vẫn giải mã được.

**Cách xử lý:** liên hệ response với request/phiên ban đầu, `state`, `nonce`, `InResponseTo`, kiểm tra thời hạn, và duy trì replay cache/ID theo yêu cầu giao thức. Cần chống replay cả ở tầng ứng dụng.

### Trường hợp F – Thay khóa theo cách thiếu tin cậy

Một JWT mang `kid` lạ hoặc header chứa đường dẫn khóa. Nếu RP tự tải khóa từ URL nằm trong token chưa xác minh, kẻ tấn công có thể phát hành token tự ký và khiến RP chấp nhận.

**Cách xử lý:** giới hạn bộ khóa và thuật toán từ issuer đã tin cậy; chỉ refresh JWKS tại endpoint cấu hình/discovery đã kiểm soát, quản lý thay khóa và chặn SSRF.

## 10. Quy trình kiểm tra một luồng federation

Khi thiết kế hoặc đánh giá một tích hợp, lần lượt xác định:

1. **Bản đồ các hop:** browser → OP/IdP, browser → RP/SP, proxy → app, app → token/metadata/JWKS endpoint. Với từng hop, ai là TLS endpoint, ai đọc được plaintext, có yêu cầu mTLS hay không?
2. **Chữ ký:** thông điệp nào phải ký; `Response` hay `Assertion` với SAML; JWS của ID Token với OIDC; key nào được tin, thuật toán nào được chấp nhận, phần dữ liệu nào thực sự được kiểm tra?
3. **Mã hóa:** có thông tin nhạy cảm nào cần giữ bí mật khỏi browser, proxy hoặc các service trung gian? Bên nhận nào có private decryption key? JWE/EncryptedAssertion có được hai bên hỗ trợ?
4. **Ngữ nghĩa giao thức:** `iss`/`aud`/`exp`/`nonce`/`state`/PKCE hoặc `Issuer`/`AudienceRestriction`/`Recipient`/`InResponseTo`; chống replay và độ lệch đồng hồ.
5. **Key lifecycle:** cấp phát qua kênh tin cậy, lưu secret an toàn, phân quyền truy cập, rotation, thu hồi, bảo đảm cấu hình không chấp nhận key/algorithm ngoài chính sách.
6. **Vận hành:** cookie RP, redirect URI/ACS, headers từ proxy, HTTPS thực tế ở chặng backend, log đã che token/secret, timeout kết nối, khả năng quan sát lỗi mà không làm lộ dữ liệu.

Đối với lỗi thực tế, **chia theo lớp**: TLS handshake/hostname lỗi là vấn đề kết nối; signature verification thất bại là vấn đề nội dung đã ký/trust key; decrypt thất bại là vấn đề encryption key/algorithm; token đã xác minh nhưng bị từ chối vì audience, nonce hoặc replay là vấn đề **ngữ cảnh federation**. Không hạ mức xác thực để “sửa” lỗi ở lớp khác.

## 11. Tự kiểm tra

**Câu 1.** Browser truy cập IdP qua HTTPS và chuyển một SAMLResponse đã ký đến SP. Proxy ở phía SP chấm dứt TLS. Proxy có thể thấy assertion không?  
**Đáp án:** có thể, nếu assertion chỉ ký và không mã hóa mức thông điệp; sau TLS termination proxy có plaintext HTTP. Muốn che thuộc tính khỏi proxy, cần mã hóa assertion cho SP theo thiết kế.

**Câu 2.** Chữ ký ID Token hợp lệ có đủ tạo phiên cho mọi ứng dụng không?  
**Đáp án:** không; ứng dụng còn phải kiểm tra issuer, audience, expiration, nonce khi yêu cầu, đúng giao dịch và các điều kiện OIDC khác.

**Câu 3.** Khi SP giải mã thành công EncryptedAssertion thì đã biết ai phát hành assertion chưa?  
**Đáp án:** chưa; cần xác thực chữ ký và điều kiện SAML bằng IdP signing key đã tin cậy.

**Câu 4.** Lệnh gọi backend đến Token Endpoint dùng HTTPS có đồng nghĩa token response không cần xác minh claims?  
**Đáp án:** không; TLS bảo vệ giao vận, còn việc chấp nhận ID Token phải theo OIDC.

**Câu 5.** Có thể sử dụng `kid` trong JWS để tải bất kỳ public key nào từ URL nằm trong token?  
**Đáp án:** không; `kid` chỉ được dùng để chọn từ bộ khóa đã ràng buộc với issuer được tin cậy.

## 12. Tài liệu tham khảo

- [OWASP – SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet): TLS, chữ ký, mã hóa, XML Signature Wrapping và replay.
- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): authentication flow, verification và decryption credentials.
- [Spring Security – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): bước xác minh và giải mã SAML.
- [Spring Security – OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): tích hợp OIDC/OAuth2 ở Servlet.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): xác minh ID Token, claims và quy trình Authorization Code.
- [RFC 7515 – JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515.html) và [RFC 7516 – JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516.html): định dạng bảo vệ toàn vẹn và bí mật ở mức thông điệp.
- [RFC 9700 – OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html): security considerations cho authorization code, PKCE, redirect và token.
