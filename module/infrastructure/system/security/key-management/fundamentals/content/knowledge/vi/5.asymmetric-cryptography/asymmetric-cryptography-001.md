# Asymmetric cryptography: Mật mã bất đối xứng và quản lý cặp khóa

Khi một dịch vụ gửi dữ liệu cho đối tác chưa từng chia sẻ khóa bí mật, hoặc khi bên nhận cần xác minh một tài liệu thực sự được ký bởi hệ thống phát hành, mật mã đối xứng đơn thuần chưa giải quyết trọn vẹn vấn đề phân phối khóa và xác thực nguồn. **Asymmetric cryptography (mật mã bất đối xứng)** dùng hai thành phần liên hệ về toán học, thường gọi là **public key (khóa công khai)** và **private key (khóa riêng)**. Tùy thuật toán, cặp khóa phục vụ **mã hóa khóa công khai**, **chữ ký số** hoặc **thỏa thuận khóa**.

Trong phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, học mật mã bất đối xứng không chỉ là nhớ tên RSA, ECC hay Ed25519. Hệ thống còn cần biết **khóa nào được phép dùng cho thao tác nào**, cách phân phối public key đáng tin cậy, cách giữ private key an toàn trong KMS/HSM, cách ghi audit và xử lý vòng đời khóa từ **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng đến thu hồi và hủy**. Sai lầm ở bất kỳ bước nào cũng có thể dẫn đến giả mạo chữ ký, giải mã trái phép hoặc mất khả năng khôi phục dữ liệu.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích cặp public/private key và phân biệt cơ chế bất đối xứng với mã hóa đối xứng.
2. Phân biệt chính xác **public-key encryption**, **digital signature** và **key agreement**; chọn thuật toán phù hợp với mục tiêu.
3. Thiết kế mã hóa lai (*hybrid encryption*) bằng cơ chế bảo vệ DEK và mã hóa dữ liệu bằng AES-GCM.
4. Hiểu ý nghĩa của xác thực public key, chứng thư X.509, PKI, JWKS và các rủi ro khi khóa công khai bị tráo.
5. Minh họa ký số Ed25519 và bảo vệ khóa AES bằng RSA-OAEP với Java 17.
6. Lập kế hoạch quản lý khóa trên KMS/HSM, phân quyền, xoay vòng, thu hồi và hủy an toàn.

## 2. Nguyên lý của mật mã bất đối xứng

Một thuật toán bất đối xứng tạo ra hoặc sử dụng một **cặp khóa** có quan hệ toán học:

~~~text
                 Sinh cặp khóa an toàn
                         |
                +--------+--------+
                |                 |
           Private key        Public key
          giữ bí mật          có thể chia sẻ
                |                 |
        Ký / giải mã /      Xác minh chữ ký /
        thỏa thuận khóa     mã hóa / thỏa thuận khóa
                 (tùy thuật toán và mục đích)
~~~

Public key được thiết kế để có thể công bố. Với thuật toán, tham số và triển khai an toàn, việc có public key **không đủ để tính ra private key trong khả năng tính toán của mô hình tấn công được xét**. Tuy vậy, tính chất này không bảo vệ trước việc private key bị lộ từ Git, log, backup, heap dump, quyền API quá rộng hoặc thiết bị bị tấn công.

**Cặp khóa không có nghĩa mọi private key đều có thể giải mã và ký.** Ed25519 dùng ký/xác minh; X25519 dùng thỏa thuận khóa; RSA có các sơ đồ mã hóa và ký riêng. Thiết kế phải gắn mỗi khóa với thuật toán và **purpose** cụ thể.

### 2.1. So sánh với mật mã đối xứng

| Tiêu chí | Mật mã đối xứng | Mật mã bất đối xứng |
|---|---|---|
| Vật liệu khóa | Một khóa bí mật chung cho các bên được phép | Một cặp public key và private key |
| Tác vụ điển hình | Mã hóa dữ liệu khối lượng lớn, AEAD, MAC, key wrapping | Mã hóa/bảo vệ khóa nhỏ, chữ ký số, thỏa thuận khóa |
| Ví dụ | AES-GCM, AES-KW, HMAC-SHA-256 | RSA-OAEP, RSA-PSS, ECDSA, Ed25519, X25519 |
| Tốc độ | Thường nhanh hơn cho dữ liệu lớn | Thường tốn tài nguyên hơn trên mỗi phép toán |
| Phân phối khóa | Cần cấp phát bí mật chung an toàn | Public key có thể công bố nhưng phải được **xác thực** |
| Tác động khi khóa lộ | Người biết khóa đối xứng có thể thao tác theo khả năng của nó | Private key lộ có thể cho phép ký giả hoặc giải mã/thỏa thuận khóa theo mục đích |
| Sai lầm thường gặp | Tái sử dụng nonce AES-GCM, để lộ DEK, quyền giải mã quá rộng | Tin public key giả, chọn sai thuật toán, lộ hoặc lạm dụng private key |

Trong thực tế hai loại mật mã thường **phối hợp**: bất đối xứng để xác thực hoặc thiết lập/bảo vệ khóa, đối xứng để mã hóa dữ liệu lớn với hiệu năng tốt.

## 3. Ba nhóm thao tác bất đối xứng cần phân biệt

### 3.1. Public-key encryption: mã hóa cho bên nhận

Ở một sơ đồ **public-key encryption** như **RSA-OAEP**, người gửi dùng **public key đã xác thực của bên nhận** để mã hóa một giá trị nhỏ; bên nhận dùng **private key tương ứng** để giải mã.

~~~mermaid
sequenceDiagram
    participant A as Người gửi
    participant B as Người nhận
    A->>A: Lấy và xác thực public key của B
    A->>A: Encrypt(public_B, secret nhỏ)
    A->>B: Encrypted secret + metadata thuật toán
    B->>B: Decrypt(private_B, encrypted secret)
    Note over B: Chỉ cung cấp plaintext khi quyền và thuật toán hợp lệ
~~~

**Điểm quan trọng:** mã hóa bằng public key **không tự xác thực người gửi**, vì bất kỳ ai biết public key của B đều có thể mã hóa cho B. Nếu cần biết “ai gửi?”, phải dùng chữ ký số hoặc giao thức xác thực thích hợp. Đồng thời RSA-OAEP có giới hạn kích thước plaintext theo RSA modulus và tham số OAEP; không nên dùng nó để mã hóa trực tiếp file lớn.

Trong hệ thống lớn, public-key encryption thường dùng để bảo vệ một **DEK** ngắn, còn nội dung lớn được mã hóa đối xứng bằng **AES-GCM**.

### 3.2. Digital signature: ký bằng private key, xác minh bằng public key

**Chữ ký số** tạo ra bằng **private key của bên ký** trên một thông điệp/biểu diễn thông điệp đã xác định. Bên kiểm tra dùng **public key đáng tin cậy** kiểm tra chữ ký.

~~~mermaid
sequenceDiagram
    participant S as Dịch vụ phát hành
    participant K as KMS/HSM giữ private key
    participant V as Bên xác minh
    S->>K: Sign(keyRef, bytes cần ký)
    K-->>S: Signature
    S->>V: Message + signature + key identifier
    V->>V: Resolve trusted public key và thuật toán
    V->>V: Verify(public key, message, signature)
    V-->>S: Kết quả hợp lệ / không hợp lệ
~~~

Ví dụ, **Ed25519** là thuật toán ký số dựa trên đường cong elliptic. Nó không được dùng như một cơ chế giải mã ciphertext AES hoặc RSA. **RSA-PSS** cũng là sơ đồ chữ ký số, còn **RSA-OAEP** là sơ đồ mã hóa: hai tên này không nên hoán đổi.

Chữ ký hợp lệ cho biết chữ ký khớp với thông điệp và public key theo thuật toán. Nó **không tự chứng minh danh tính** nếu chưa có cách tin cậy rằng public key thuộc về người/dịch vụ được nhận dạng. Khi private key bị lạm dụng, chữ ký vẫn có thể hợp lệ về mật mã; cần kiểm soát quyền **Sign**, giám sát và phản ứng sự cố.

**Không giải thích chữ ký số là “mã hóa thông điệp bằng private key”.** Mô tả đó sai với Ed25519, ECDSA và bỏ qua các chi tiết bắt buộc trong RSA-PSS. Hãy dùng đúng API **Sign/Verify**.

### 3.3. Key agreement: các bên cùng tạo bí mật chung

Với **ECDH/X25519**, mỗi bên có private key riêng và public key tương ứng. Hai bên trao đổi **public key**, sau đó mỗi bên dùng private key của mình kết hợp với public key của phía kia để tạo **shared secret**. Một **KDF** theo giao thức sẽ dẫn xuất keying material hoặc khóa phiên từ shared secret.

~~~mermaid
flowchart LR
    A["A: private_A + public_B"] --> S1["Tính shared secret phía A"]
    B["B: private_B + public_A"] --> S2["Tính shared secret phía B"]
    S1 --> K["Hai kết quả toán học tương đương"]
    S2 --> K
    K --> D["KDF + transcript/context"]
    D --> E["Khóa phiên cho AES-GCM / AEAD"]
~~~

Hai phía tính toán **độc lập**, không gửi private key hay shared secret qua mạng. **ECDH/X25519 thuần túy không xác thực public key đối tác**: nếu kẻ tấn công tráo public key, có thể thực hiện tấn công *man-in-the-middle*. Một giao thức đầy đủ phải xác thực các bên, liên kết transcript và kiểm tra những điều kiện cần thiết của public-key input.

Khi dùng **ephemeral ECDH** và xóa đúng các bí mật tạm thời, một giao thức được xác thực có thể cung cấp **forward secrecy**: việc private key xác thực dài hạn bị lộ về sau không đủ để giải mã những phiên cũ đã được thiết lập an toàn. Điều này phụ thuộc toàn bộ giao thức, không chỉ việc chọn tên thuật toán ECDH.

### 3.4. Key transport, KEM và key agreement

Các thuật ngữ hay bị nhầm:

| Cơ chế | Cách tạo bí mật dùng chung | Ví dụ |
|---|---|---|
| **Key transport** | Một bên chọn/tạo khóa rồi vận chuyển an toàn cho bên kia | Wrap DEK bằng KEK; mã hóa DEK bằng RSA-OAEP |
| **Key agreement** | Các bên đóng góp để tính cùng bí mật | ECDH/X25519 theo giao thức |
| **KEM (Key Encapsulation Mechanism)** | Bên encapsulate tạo ciphertext đóng gói và shared secret; bên decapsulate dùng private key khôi phục shared secret | KEM được hỗ trợ bởi giao thức và thư viện phù hợp |

Một **KEM không nhất thiết cho phép người gửi tự chọn bất kỳ DEK rồi encrypt trực tiếp DEK đó**. Thay vào đó, hai phía có chung một bí mật sau encapsulation/decapsulation và có thể dùng KDF để dẫn xuất khóa phù hợp. Luôn đọc ngữ nghĩa API và giao thức cụ thể.

## 4. Các thuật toán và tham số thường gặp

| Thuật toán/sơ đồ | Mục đích | Ví dụ lựa chọn triển khai | Ràng buộc cần nhớ |
|---|---|---|---|
| **RSA-OAEP** | Mã hóa hoặc bảo vệ khóa nhỏ | RSA 3072 bit, OAEP với SHA-256 và MGF1 phù hợp | Hạn chế kích thước plaintext; tham số OAEP phải khớp hai phía |
| **RSA-PSS** | Chữ ký số | RSA với SHA-256, MGF1 và salt theo chính sách | Không thay bằng mã hóa RSA raw |
| **ECDSA** | Chữ ký số trên đường cong EC | NIST P-256 với SHA-256 | Nonce ký sai hoặc trùng có thể làm lộ private key; dùng thư viện chuẩn |
| **Ed25519** | Chữ ký số EdDSA | JCA Ed25519 trên JDK hỗ trợ | Không dùng cho encrypt/decrypt |
| **X25519** | Thỏa thuận khóa dựa trên đường cong Montgomery | Dùng với KDF và xác thực peer | Không phải chữ ký số, không tự tạo niềm tin vào đối tác |
| **AES-GCM** | Mã hóa dữ liệu sau khi có DEK | AES-256-GCM, nonce 96 bit, tag 128 bit | Là **mật mã đối xứng**, được phối hợp trong mã hóa lai |

Độ dài khóa, đường cong và thuật toán phải tuân theo chính sách an ninh, khả năng tương thích, vòng đời dữ liệu và yêu cầu pháp lý của hệ thống. Không so sánh trực tiếp “256 bit EC = 256 bit RSA” vì cấu trúc toán học và mức độ an toàn không tương đương chỉ qua độ dài biểu diễn. Cũng không thể coi một sơ đồ cổ điển là **kháng lượng tử** chỉ vì khóa dài hơn; việc chuyển sang mật mã hậu lượng tử cần lựa chọn chuẩn/giao thức riêng.

### 4.1. Hash, padding và encoding không thể bỏ qua

- Với **RSA-OAEP**, cần biết digest, MGF và tham số label của OAEP. Hai đầu cấu hình không nhất quán có thể không giải mã được, hoặc khiến triển khai dùng mặc định khác dự kiến.
- Với **RSA-PSS**, cần thống nhất digest, MGF, salt length và cách biểu diễn thông điệp/digest theo API.
- Với **ECDSA**, chữ ký có nhiều dạng mã hóa (chẳng hạn ASN.1 DER hoặc định dạng raw r||s trong một số giao thức). Dùng đúng encoding của hợp đồng API.
- Với **Ed25519**, dùng đúng biến thể được giao thức quy định và byte thông điệp chính xác; không tự thêm một lần băm theo giả định “mọi API ký đều nhận hash”.
- Với **JSON/JWS**, các bên phải ký và xác minh đúng bytes theo chuẩn của định dạng, bao gồm encoding và canonicalization khi quy trình cần. Không tái tạo tùy ý một JSON “có nghĩa giống nhau” rồi hy vọng signature vẫn đúng.

## 5. Xác thực public key quan trọng ngang với giữ kín private key

Public key **không cần bí mật**, nhưng phải được liên kết tin cậy với danh tính, ứng dụng hoặc miền bảo mật đúng. Nếu kẻ tấn công thay public key khi một dịch vụ tải khóa đối tác, dịch vụ có thể mã hóa bí mật cho kẻ tấn công hoặc xác minh nhầm chữ ký của kẻ tấn công.

### 5.1. PKI và chứng thư X.509

**Public Key Infrastructure (PKI)** cung cấp mô hình phát hành, phân phối, kiểm tra và thu hồi chứng thư. Một **chứng thư X.509** thường chứa public key, thông tin chủ thể, bên phát hành, thời hạn hiệu lực, mục đích sử dụng cùng chữ ký của CA. Chứng thư **không chứa private key** tương ứng.

Khi một client xác minh chứng thư TLS, nó cần xét đường tin cậy đến trust anchor đã cấu hình, tên máy chủ, thời hạn, mục đích sử dụng, thuật toán phù hợp và chính sách thu hồi nếu được yêu cầu. Chỉ nhìn thấy public key hoặc một chứng thư có chữ ký số **chưa đủ để tin** nếu chưa kiểm tra chain và các điều kiện sử dụng.

### 5.2. JWKS và trường kid

Một dịch vụ phát hành JWT có thể công bố tập public key qua **JWKS (JSON Web Key Set)**. Header **kid** của JWS/JWT chỉ là **gợi ý chọn khóa** trong danh sách khóa **đã được tin cậy**. Bên xác minh không được coi kid, một URL hoặc tên thuật toán do token tùy ý cung cấp là nguồn cấp public key đáng tin cậy.

Ví dụ quy trình kiểm tra token:

1. Xác định **issuer** và điểm lấy JWKS từ cấu hình đáng tin cậy.
2. Chỉ cho phép những thuật toán ký được hệ thống hỗ trợ theo chính sách; kiểm tra thuật toán tương thích với khóa.
3. Dùng **kid** chọn khóa trong tập public key được chấp thuận.
4. Kiểm tra chữ ký và các claim quan trọng như **iss**, **aud**, **exp**, **nbf** theo ngữ cảnh.
5. Quản lý cache và thời gian chồng lấn khóa khi rotation; xử lý khẩn cấp nếu khóa ký lộ.

Chữ ký trên token không mã hóa payload JWT. Nếu cần **giữ bí mật**, cần dùng JWE hoặc mã hóa nội dung bằng một giải pháp thích hợp; không gọi một token chỉ có JWS là “đã được mã hóa”.

## 6. Mã hóa lai và envelope encryption

Mật mã bất đối xứng không nên gánh toàn bộ thao tác mã hóa file hoặc database lớn. Thiết kế phổ biến:

1. Tạo một **DEK (Data Encryption Key)** đối xứng ngẫu nhiên.
2. Mã hóa payload bằng **AES-GCM** cùng nonce không trùng theo DEK và AAD được xác định.
3. Bảo vệ DEK bằng **RSA-OAEP với public key đúng của bên nhận**, một KEM và KDF phù hợp hoặc KEK trong KMS/HSM.
4. Lưu/gửi **ciphertext + tag + nonce + encrypted/wrapped DEK + metadata** cần thiết để giải mã.
5. Bên nhận dùng private key hoặc quyền unwrap của KMS/HSM để khôi phục DEK, rồi xác minh tag GCM và giải mã dữ liệu.

~~~mermaid
flowchart TD
    P["Payload cần bảo vệ"] --> G["AES-GCM Encrypt với DEK + nonce + AAD"]
    D["DEK bí mật ngẫu nhiên"] --> G
    D --> W["Bảo vệ DEK bằng RSA-OAEP / KEK / KEM+KDF"]
    PK["Public key người nhận hoặc wrapping KEK"] --> W
    G --> C["Ciphertext + authentication tag"]
    W --> ED["Encrypted/wrapped DEK"]
    C --> O["Gói bản mã hoàn chỉnh"]
    ED --> O
    N["Nonce, key reference, algorithm, AAD context"] --> O
    O --> R["Bên nhận xác thực nguồn và quyền, lấy DEK, verify tag, decrypt"]
~~~

**Một biến thể:** hệ thống KMS có thể dùng **KEK đối xứng** và API **GenerateDataKey/Decrypt/ReEncrypt** để wrap DEK, không sử dụng khóa RSA. KEK đối xứng **không phải** private key bất đối xứng. Điểm chung của các mô hình là bảo vệ DEK và giới hạn việc sử dụng khóa theo quyền.

### 6.1. Material và metadata trong gói mã hóa

| Thành phần | Phân loại | Quy tắc bảo vệ |
|---|---|---|
| **Private key bên nhận** | Key material bí mật | Giữ trong kho được bảo vệ, không xuất plaintext khi không cần thiết |
| **Public key bên nhận** | Key material công khai | Xác thực đúng chủ thể và nguồn phát hành |
| **DEK bản rõ** | Key material bí mật | Tồn tại ngắn hạn trong nơi xử lý được tin cậy |
| **Encrypted/wrapped DEK** | Key material đã mã hóa | Bảo vệ quyền truy cập, tính toàn vẹn và khả năng unwrap |
| **Ciphertext + GCM tag** | Dữ liệu mã hóa và bằng chứng xác thực AEAD | Không được bỏ qua tag hoặc dùng dữ liệu trước khi verify |
| **Nonce/IV** | Tham số mỗi lần mã hóa | Không bí mật; phải không trùng trong phạm vi cùng DEK |
| **keyId, keyVersion, algorithm, formatVersion** | Key/ciphertext metadata | Phải được kiểm tra, ràng buộc với dữ liệu và đúng context |
| **Tenant ID, record ID, AAD** | Context nghiệp vụ và metadata được xác thực | Không dùng AAD để chứa secret; kiểm tra quyền tenant độc lập |

**Mã hóa cho public key B không tự bảo đảm người gửi là A.** Nếu cần nguồn gốc có thể xác minh độc lập, hệ thống nên dùng một chữ ký số của A hoặc giao thức đã xác thực, với ngữ nghĩa chính xác về dữ liệu nào được ký và kiểm tra.

## 7. Ví dụ Java 17: ký và xác minh bằng Ed25519

Java Cryptography Architecture (JCA) hỗ trợ sử dụng private/public key qua các interface chuẩn. Ví dụ tạo cặp khóa tạm trong bộ nhớ, ký một chuỗi byte rồi thử thay đổi thông điệp:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;

public final class Ed25519SignatureDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair pair = generator.generateKeyPair();

        byte[] invoice = "invoice=123;total=250000"
                .getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(pair.getPrivate());  // Chỉ phía ký có private key
        signer.update(invoice);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(pair.getPublic()); // Phía nhận dùng public key
        verifier.update(invoice);
        System.out.println("Original valid: " + verifier.verify(signature));

        byte[] changed = "invoice=123;total=250001"
                .getBytes(StandardCharsets.UTF_8);
        verifier.initVerify(pair.getPublic());
        verifier.update(changed);
        System.out.println("Changed valid: " + verifier.verify(signature));

        // Không ghi private key, raw seed hoặc thông tin bí mật vào log.
    }
}
~~~

Lưu vào **Ed25519SignatureDemo.java**, sau đó chạy với JDK 17+:

~~~bash
javac Ed25519SignatureDemo.java
java Ed25519SignatureDemo
~~~

Kết quả mong đợi là **Original valid: true** và **Changed valid: false**. Trong demo, public key được lấy từ cặp khóa vừa sinh nên việc xác minh diễn ra trong cùng chương trình. Ở môi trường thật, bên kiểm tra cần **lấy public key từ nguồn được xác thực** và kiểm tra đúng issuer/purpose/version, không chỉ nhận một public key tùy ý trong request.

**Lưu ý:** chương trình không xuất private key ra file. Việc gọi phương thức xuất khóa như **getEncoded()** có thể trả về material với provider phần mềm; với khóa trong KMS/HSM, private key có thể chỉ được đại diện bằng handle và không xuất được. Việc khóa không xuất được không thay thế kiểm soát quyền **Sign**.

## 8. Ví dụ Java 17: RSA-OAEP bảo vệ DEK, AES-GCM mã hóa payload

Ví dụ thứ hai cho thấy rõ sự phân công: **RSA public key bảo vệ DEK**, **RSA private key khôi phục DEK**, còn **AES-GCM dùng DEK mã hóa/giải mã nội dung**. Mã minh họa chạy trong một tiến trình để đơn giản hóa việc kiểm tra; hệ thống phân tán cần cơ chế phân phối public key và phân quyền private key tương ứng.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.spec.MGF1ParameterSpec;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;

public final class HybridEncryptionDemo {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final OAEPParameterSpec OAEP_SHA256 =
            new OAEPParameterSpec("SHA-256", "MGF1",
                    MGF1ParameterSpec.SHA256, PSource.PSpecified.DEFAULT);

    public record Envelope(byte[] wrappedDek, byte[] nonce,
                           byte[] ciphertextWithTag) {}

    public static Envelope encrypt(
            byte[] plaintext, byte[] aad, java.security.PublicKey recipient)
            throws Exception {
        KeyGenerator keyGenerator = KeyGenerator.getInstance("AES");
        keyGenerator.init(256);
        SecretKey dek = keyGenerator.generateKey();

        // RSA-OAEP được cấu hình rõ cả digest và MGF1 digest.
        Cipher wrap = Cipher.getInstance("RSA/ECB/OAEPPadding");
        wrap.init(Cipher.WRAP_MODE, recipient, OAEP_SHA256);
        byte[] wrappedDek = wrap.wrap(dek);

        byte[] nonce = new byte[12];
        RANDOM.nextBytes(nonce);
        Cipher aes = Cipher.getInstance("AES/GCM/NoPadding");
        aes.init(Cipher.ENCRYPT_MODE, dek, new GCMParameterSpec(128, nonce));
        aes.updateAAD(aad);
        byte[] ciphertextWithTag = aes.doFinal(plaintext);
        return new Envelope(wrappedDek, nonce, ciphertextWithTag);
    }

    public static byte[] decrypt(
            Envelope envelope, byte[] aad,
            java.security.PrivateKey recipientPrivateKey) throws Exception {
        if (envelope.nonce().length != 12) {
            throw new IllegalArgumentException("Invalid nonce size");
        }

        Cipher unwrap = Cipher.getInstance("RSA/ECB/OAEPPadding");
        unwrap.init(Cipher.UNWRAP_MODE, recipientPrivateKey, OAEP_SHA256);
        SecretKey dek = (SecretKey) unwrap.unwrap(
                envelope.wrappedDek(), "AES", Cipher.SECRET_KEY);

        Cipher aes = Cipher.getInstance("AES/GCM/NoPadding");
        aes.init(Cipher.DECRYPT_MODE, dek,
                new GCMParameterSpec(128, envelope.nonce()));
        aes.updateAAD(aad);
        return aes.doFinal(envelope.ciphertextWithTag()); // Xác minh tag
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator rsaGenerator = KeyPairGenerator.getInstance("RSA");
        rsaGenerator.initialize(3072);
        KeyPair recipient = rsaGenerator.generateKeyPair();

        byte[] aad = "tenant=tenant-42;format=v1"
                .getBytes(StandardCharsets.UTF_8);
        Envelope envelope = encrypt(
                "Dữ liệu cần bảo vệ".getBytes(StandardCharsets.UTF_8),
                aad, recipient.getPublic());

        byte[] plaintext = decrypt(envelope, aad, recipient.getPrivate());
        System.out.println(new String(plaintext, StandardCharsets.UTF_8));

        try {
            decrypt(envelope, "tenant=tenant-other;format=v1"
                    .getBytes(StandardCharsets.UTF_8), recipient.getPrivate());
            throw new IllegalStateException("Expected authentication failure");
        } catch (AEADBadTagException expected) {
            System.out.println("Wrong AAD rejected");
        }

        // Trong ứng dụng thực tế: không ghi DEK hoặc plaintext nhạy cảm ra log.
    }
}
~~~

Lưu thành **HybridEncryptionDemo.java**, rồi chạy với JDK 17+:

~~~bash
javac HybridEncryptionDemo.java
java HybridEncryptionDemo
~~~

Kết quả mong đợi là dữ liệu được khôi phục đúng và dòng **Wrong AAD rejected**. Ví dụ dùng **nonce ngẫu nhiên 96 bit** cho một lần mã hóa; nếu dùng cùng DEK cho nhiều lần, phải bảo đảm nonce **không trùng trong phạm vi DEK đó**, kể cả retry, nhiều instance hoặc khôi phục sau sự cố. Ví dụ sinh DEK mới mỗi lần nhằm thu nhỏ phạm vi sử dụng khóa.

### 8.1. Những giới hạn của đoạn mã demo

1. **Không có hệ thống PKI:** public key được lấy trực tiếp từ cặp vừa sinh; production phải xác thực public key của recipient qua chứng thư hoặc trust store phù hợp.
2. **DEK nằm trong bộ nhớ Java:** với KMS/HSM, API wrap/unwrap có thể thực thi trong ranh giới phần cứng hoặc dịch vụ, phụ thuộc loại khóa và khả năng nhà cung cấp. Không dùng demo để kết luận mọi KMS đều cho phép xuất DEK.
3. **Chưa có quản lý metadata:** phải lưu đúng wrapping key ID/version, thuật toán OAEP, nonce, ciphertext/tag, định dạng AAD và quyền tenant để khôi phục dữ liệu lịch sử.
4. **AAD ví dụ là chuỗi đơn giản:** khi có nhiều trường do người dùng nhập, cần định dạng byte **có cấu trúc, không nhập nhằng và có version**. Không tự tin tenant do request khai báo; tenant phải được xác thực bằng quyền truy cập.
5. **Không có xác thực người gửi:** RSA-OAEP mã hóa cho bên nhận; để kiểm tra tác giả/gói tin cần thêm chữ ký số, MAC thích hợp hoặc giao thức truyền thông đã xác thực.
6. **AES-GCM phải xác minh tag:** không chấp nhận plaintext khi giải mã thất bại, không bỏ qua lỗi và không tự động fallback sang chế độ không xác thực.
7. **Đây là demo trong một JVM:** production cần quản lý bộ nhớ, xử lý khóa hủy, retry, giới hạn request, kiểm toán, backup và truy vết theo chính sách.

## 9. KMS/HSM trong quản lý khóa bất đối xứng

**KMS (Key Management Service)** cung cấp các chức năng quản lý vòng đời, metadata, quyền và thao tác mật mã theo API. **HSM (Hardware Security Module)** là môi trường phần cứng chuyên dụng để bảo vệ key material và thực hiện thao tác mật mã theo thiết kế thiết bị. Một KMS có thể sử dụng HSM làm tầng bảo vệ, nhưng hai khái niệm không đồng nghĩa.

~~~mermaid
flowchart LR
    App["Workload đã được xác thực"] -->|"Sign / Decrypt theo quyền"| K["KMS API + policy"]
    K -->|"Thực thi với private key"| H["HSM hoặc kho khóa được bảo vệ"]
    H -->|"Chữ ký / kết quả được phép"| K
    K --> App
    K -->|"Actor, keyId, operation, result"| L[("Audit logs")]
    Pub["Kho public key đáng tin"] -->|"Public key để Verify/Encrypt"| App
~~~

Trong một mô hình **private key non-exportable**, ứng dụng chỉ có **key reference/handle**. Nó gửi yêu cầu ký hoặc giải mã đã được cấp quyền rồi nhận kết quả mà không cần lấy byte private key. Nhưng kẻ tấn công chiếm một workload có quyền **Sign** có thể tạo chữ ký ngay trong HSM. Vì vậy bảo mật phải xét **hai bề mặt tấn công riêng**: ai có thể **đọc material**, và ai có thể **khiến khóa thực hiện thao tác**.

### 9.1. Key material, metadata và phân quyền

| Thành phần | Ví dụ | Đòi hỏi an ninh |
|---|---|---|
| **Private key material** | RSA private exponent, EC private scalar, Ed25519 seed | Giữ bí mật, hạn chế export, bảo vệ bộ nhớ/backup |
| **Public key material** | SPKI public key, public JWK | Xác thực chủ thể và tính toàn vẹn |
| **Key reference** | Key ID, version, alias, HSM handle | Được kiểm tra theo tenant/purpose; alias có thể thay đổi đích |
| **Key policy** | Chỉ workload A có quyền Sign | Phân quyền tối thiểu, không cho sửa trái phép |
| **Lifecycle metadata** | Created, Active, Disabled, PendingDeletion | Thực thi trạng thái và xử lý dữ liệu cũ |
| **Audit metadata** | Principal, operation, key version, thời điểm, kết quả | Không ghi raw key, passphrase hoặc plaintext nhạy cảm |

**Không phải mọi khóa KMS/HSM đều non-exportable**. Khả năng export, import, wrap và thuật toán phụ thuộc loại khóa và dịch vụ. Không nên cấp quyền quản trị policy đồng thời với quyền Sign/Decrypt nếu không cần thiết; phân tách nhiệm vụ giúp giảm nguy cơ lạm dụng.

## 10. Vòng đời cặp khóa bất đối xứng

~~~mermaid
flowchart TD
    A["Tạo cặp khóa bằng thư viện/CSPRNG an toàn"] --> B["Gắn keyId, version, algorithm, purpose và owner"]
    B --> C["Giữ private key an toàn; phân phối public key đã xác thực"]
    C --> D["Kích hoạt quyền Sign/Decrypt/Agreement"]
    D --> E["Sử dụng theo policy và ghi audit"]
    E --> F["Xoay vòng: sinh cặp mới, công bố public key mới"]
    F --> G["Ngừng thao tác mới bằng private key cũ"]
    G --> H["Duy trì verify/decrypt dữ liệu lịch sử khi được phép"]
    H --> I["Thu hồi/vô hiệu hóa, hủy khi hết phụ thuộc"]
~~~

| Giai đoạn | Quyết định cần thực hiện | Sai sót thường gặp |
|---|---|---|
| **Tạo khóa** | Dùng CSPRNG, thuật toán/curve/key size đúng chính sách | Tự tạo khóa từ timestamp hoặc số ngẫu nhiên không đủ mạnh |
| **Cấp phát/đăng ký** | Gắn ID, version, purpose, owner, tenant và môi trường | Dùng một cặp khóa ký/giải mã cho nhiều mục đích không liên quan |
| **Lưu trữ** | Private key trong KMS/HSM hoặc kho được bảo vệ; backup kiểm soát | Commit PEM vào Git, đặt private key trong image hoặc log |
| **Sử dụng** | Kiểm tra quyền, key state, thuật toán, ngữ cảnh và audit | API nhận tùy ý key ID, algorithm hay tenant từ client |
| **Xoay vòng** | Tạo cặp mới, chuyển request mới, xử lý public key cũ | Nghĩ đổi alias sẽ tự mã hóa lại ciphertext/chữ ký |
| **Vô hiệu hóa/thu hồi** | Chặn các thao tác rủi ro, cập nhật hệ thống tin cậy | Chỉ xóa alias, không chặn quyền dùng private key đã lộ |
| **Hủy** | Kiểm tra bản mã, chữ ký lịch sử, backup và khả năng khôi phục | Hủy private key giải mã khi dữ liệu cũ vẫn phụ thuộc |

### 10.1. Rotation của khóa ký khác khóa giải mã

- **Khóa ký:** chuyển **sign-v2 → sign-v3** nghĩa là chữ ký mới được tạo bởi private key v3. Tài liệu cũ vẫn có thể cần **public key v2** để xác minh; giữ public key v2 không có nghĩa phải giữ quyền ký bằng private key v2. Nếu v2 bị lộ, chính sách xác minh lịch sử còn phụ thuộc thời điểm ký, chứng thư và bằng chứng tin cậy.
- **Khóa giải mã:** chuyển người gửi sang public key **decrypt-v3** chỉ ảnh hưởng dữ liệu mới. Ciphertext được mã hóa bằng public key v2 vẫn cần private key v2 tương ứng (hoặc đã được chuyển đổi bằng một quy trình an toàn). Hủy private key v2 quá sớm có thể làm mất dữ liệu.
- **Khóa thỏa thuận tạm thời:** sử dụng và xóa ephemeral private key theo giao thức; không giữ bản sao bí mật tạm thời lâu hơn nhu cầu. Khả năng khôi phục phiên và forward secrecy có những yêu cầu riêng, không giống backup khóa giải mã dữ liệu lưu trữ.

### 10.2. Disable key, revoke certificate và remove public key khác nhau

**Disable key tại KMS/HSM** hạn chế thao tác qua hệ thống đó. **Certificate revocation** thay đổi trạng thái tin cậy của chứng thư theo PKI, qua CRL/OCSP hoặc chính sách tương ứng. **Loại public key khỏi JWKS** có thể làm verifier không còn tìm được khóa, nhưng public key đã cache có thể vẫn được sử dụng đến khi hết hạn cache. Chúng là các thao tác khác nhau và phải được phối hợp khi ứng phó private key bị lộ.

### 10.3. Các định dạng và phần cần bảo vệ

- **PKCS#8** biểu diễn thông tin private key; có thể ở dạng không mã hóa hoặc container đã mã hóa.
- **SubjectPublicKeyInfo (SPKI)** là cấu trúc thường dùng cho public key.
- **DER** là biểu diễn nhị phân; **PEM** là biểu diễn text có header/footer và nội dung Base64. **PEM/Base64 không tự mã hóa để bảo mật**.
- **X.509 certificate** chứa public key và thuộc tính xác thực; private key không nằm trong chứng thư.
- **JWK/JWKS** thường chứa thông tin public key phục vụ web token; phải kiểm tra key type, algorithm, use, issuer và nguồn tin cậy. Không công bố các trường private key của JWK.

Ví dụ một header PEM chỉ minh họa định dạng, **không phải khóa thật**:

~~~text
-----BEGIN PRIVATE KEY-----
<BASE64_PKCS8_DER_PLACEHOLDER>
-----END PRIVATE KEY-----
~~~

Nếu file có **BEGIN PRIVATE KEY**, thông thường container private key không được mã hóa ở lớp PKCS#8. Dạng **BEGIN ENCRYPTED PRIVATE KEY** chứa private key trong container có mã hóa, nhưng an toàn còn phụ thuộc thuật toán, KDF, mật khẩu và quyền truy cập. Đừng kết luận “file .pem an toàn” chỉ vì nó được Base64.

## 11. Tình huống triển khai: ký JWT và giải mã hồ sơ giữa hai dịch vụ

Một hệ thống gồm **Auth Service**, **API Gateway**, **Document Service** và **KMS**:

1. **Auth Service** được cấp quyền **Sign** với private key phiên bản **auth-sign-v4** trong KMS. API Gateway nhận public key từ một JWKS/nguồn tin cậy và xác minh chữ ký, issuer, audience, thời hạn token.
2. **Document Service** nhận public key **doc-encrypt-v2** của đối tác từ kênh đã xác thực, tạo DEK AES-256 ngẫu nhiên, mã hóa file bằng **AES-GCM**, rồi bảo vệ DEK theo cơ chế public-key encryption phù hợp.
3. Đối tác giữ private key **doc-encrypt-v2** trong KMS/HSM và chỉ cấp quyền giải mã/unwrap cho workload xử lý tài liệu đúng tenant.
4. Bản ghi lưu **key ID/version, thuật toán, encrypted DEK, nonce, ciphertext, tag và ngữ cảnh AAD**. Metadata an ninh phải được xác thực/ràng buộc theo định dạng, không được tin một request tùy ý.
5. Khi rotate **auth-sign-v4 → v5**, Gateway cần khoảng chồng lấn public key theo chính sách để xác minh token còn hiệu lực. Khi rotate **doc-encrypt-v2 → v3**, dữ liệu cũ phải được khôi phục bằng private key v2 hoặc được chuyển đổi trước khi hủy.
6. KMS ghi audit **actor, action, resource ID/version, timestamp, result**. Không ghi private key, plaintext DEK hoặc nội dung tài liệu vào log.

Ví dụ cho thấy cùng là mật mã bất đối xứng nhưng **khóa ký** và **khóa giải mã** có quyền, vòng đời và tác động khi hủy hoàn toàn khác nhau. Không đặt một policy duy nhất cho mọi private key chỉ vì chúng có cùng định dạng PKCS#8.

## 12. Các nguy cơ thường gặp và cách phòng vệ

| Nguy cơ | Hậu quả có thể xảy ra | Biện pháp |
|---|---|---|
| Private key trong source code, cấu hình, CI log hoặc backup mở | Có thể tạo chữ ký giả hoặc giải mã dữ liệu tùy mục đích | KMS/HSM hoặc kho bảo vệ phù hợp; secret scanning; rotate khi lộ |
| Workload có quyền Sign/Decrypt quá rộng | Kẻ chiếm workload dùng khóa mà không cần xuất material | IAM tối thiểu; phân tách tenant/purpose; audit và giám sát bất thường |
| Public key bị tráo, JWKS lấy từ URL không tin cậy | Mã hóa cho kẻ tấn công hoặc chấp nhận chữ ký giả | PKI/trust store, pin issuer và endpoint, kiểm tra metadata |
| Cho request tự chọn alg/kid mà không kiểm tra | Algorithm confusion hoặc chọn nhầm khóa | Allowlist thuật toán, kiểm tra loại khóa và mục đích, nguồn key cố định |
| Dùng RSA raw/PKCS#1 v1.5 sai ngữ cảnh | Rủi ro padding oracle/triển khai không an toàn | Dùng cơ chế hiện đại theo giao thức, như RSA-OAEP cho mã hóa mới khi phù hợp |
| ECDSA nonce lỗi hoặc CSPRNG yếu | Có thể làm lộ private key | Thư viện mật mã đáng tin, kiểm tra nguồn ngẫu nhiên |
| ECDH không xác thực đối tác | Man-in-the-middle | Xác thực public key/peer và ràng buộc transcript trong giao thức |
| Chỉ RSA mã hóa DEK nhưng bỏ xác thực nội dung | Ciphertext/metadata bị sửa hoặc thiếu xác thực | AEAD cho payload; xác thực metadata và người gửi theo nhu cầu |
| Xóa khóa giải mã cũ ngay sau rotation | Không thể đọc bản mã/backup cũ | Re-encrypt/re-wrap theo thiết kế, thử khôi phục trước khi hủy |
| Nghĩ chữ ký số bảo vệ tính bí mật | Payload vẫn bị đọc được | Dùng mã hóa nếu dữ liệu cần bí mật; signature giải quyết bài toán khác |
| Tin rằng khóa nằm trong HSM là đủ | Có thể bị lạm dụng API ký/giải mã | IAM, phân tách quyền, hạn mức và theo dõi |

## 13. Checklist trước khi đưa mật mã bất đối xứng vào production

1. **Xác định mục tiêu:** cần bảo mật dữ liệu, xác thực người ký hay thỏa thuận khóa? Chọn đúng primitive.
2. **Chọn tham số:** thuật toán, curve/kích thước khóa, hash, OAEP/PSS, encoding và định dạng theo policy.
3. **Tin cậy public key:** có xác thực issuer/recipient, chứng thư hoặc nguồn phân phối đáng tin không?
4. **Bảo vệ private key:** khóa được tạo thế nào, giữ ở đâu, có export không, ai có quyền đọc material?
5. **Giới hạn thao tác:** ai được Sign/Decrypt/DeriveKey? Có tách policy theo purpose, tenant và môi trường không?
6. **Bảo vệ dữ liệu:** nếu mã hóa payload, dùng hybrid/envelope encryption và AEAD phù hợp; bảo đảm nonce, tag, AAD đúng.
7. **Lưu metadata:** key ID/version, thuật toán, format, public-key trust, wrapped DEK và thông tin cần cho recovery có đầy đủ?
8. **Xoay vòng:** tài liệu, JWT và ciphertext cũ có tiếp tục verify/decrypt đúng sau khi khóa mới hoạt động không?
9. **Thu hồi và hủy:** đã đánh giá certificate revocation, cache, quyền API, backup và khả năng khôi phục chưa?
10. **Kiểm toán và ứng phó:** có theo dõi ai dùng khóa, hành động và kết quả mà không tiết lộ dữ liệu nhạy cảm?

### Câu hỏi tự kiểm tra

**Câu 1.** Bên nhận chỉ cần kiểm tra một chữ ký Ed25519. Có cần nhận private key không?

**Trả lời:** **Không.** Cần public key đáng tin cậy và đúng bytes thông điệp/chữ ký theo giao thức.

**Câu 2.** Vì sao public key của đối tác phải được xác thực dù nó được gọi là “khóa công khai”?

**Trả lời:** Vì public key giả có thể khiến dữ liệu được mã hóa cho kẻ tấn công hoặc khiến một chữ ký của kẻ tấn công bị hiểu nhầm là chữ ký của đối tác.

**Câu 3.** RSA-OAEP có thích hợp để mã hóa trực tiếp một file 500 MB không?

**Trả lời:** **Không.** RSA-OAEP chỉ xử lý plaintext nhỏ; thiết kế đúng thường mã hóa file bằng DEK/AES-GCM rồi bảo vệ DEK bằng RSA-OAEP hoặc cơ chế KMS phù hợp.

**Câu 4.** Nếu các bên trao đổi public key X25519 và tính ra shared secret, danh tính của đối tác đã được xác thực chưa?

**Trả lời:** **Chưa chắc.** ECDH/X25519 bản thân không xác thực peer; cần giao thức xác thực và cơ chế ràng buộc key exchange.

**Câu 5.** Sau khi tạo khóa ký v2, có thể xóa ngay public key v1 mà không ảnh hưởng dữ liệu cũ?

**Trả lời:** **Không thể mặc định.** Chữ ký/tokens v1 có thể vẫn cần xác minh. Khoảng chuyển tiếp phải dựa trên thời hạn dữ liệu, chính sách tin cậy và đánh giá sự cố nếu khóa cũ bị lộ.

**Câu 6.** HSM không cho xuất private key. Vậy một tài khoản có quyền Sign bị chiếm có tạo được chữ ký giả không?

**Trả lời:** **Có thể.** HSM bảo vệ material nhưng tài khoản có quyền thao tác vẫn có thể lạm dụng. Cần IAM, phân tách quyền, kiểm toán và cảnh báo.

**Điểm cốt lõi:** Mật mã bất đối xứng cung cấp **mã hóa khóa công khai, chữ ký số và thỏa thuận khóa** thông qua những cơ chế khác nhau. Hệ thống an toàn phải **xác thực public key, giữ kín private key, dùng đúng thuật toán và mục đích**, rồi kết hợp mã hóa đối xứng, KMS/HSM, phân quyền, audit và vòng đời khóa cho từng nhu cầu thực tế.
