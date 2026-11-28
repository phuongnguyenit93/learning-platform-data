# Private key: Khóa riêng trong hệ thống mật mã

Trong mật mã bất đối xứng (*asymmetric cryptography*), **private key** (khóa riêng) là thành phần bí mật của một **cặp khóa** gồm private key và public key (khóa công khai). Private key cho phép chủ thể thực hiện những thao tác mà người chỉ biết public key không thể tự thực hiện, chẳng hạn tạo chữ ký số, giải mã theo một sơ đồ mã hóa khóa công khai, hoặc tham gia thỏa thuận bí mật chung. Thao tác cụ thể phụ thuộc **thuật toán và mục đích sử dụng** của cặp khóa.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, private key phải được quản lý xuyên suốt vòng đời **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi/vô hiệu hóa → hủy**. Giữ kín giá trị khóa là điều kiện cần nhưng chưa đủ: một khóa nằm an toàn trong HSM vẫn có thể bị lạm dụng nếu kẻ tấn công chiếm được tài khoản có quyền yêu cầu ký hoặc giải mã.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt private key với public key, symmetric key, key ID và chứng thư số.
2. Giải thích private key được dùng để **ký số**, **giải mã** hoặc **thỏa thuận khóa** tùy theo thuật toán.
3. Nhận diện vật liệu khóa (*key material*), metadata và những định dạng lưu trữ private key phổ biến.
4. Mô tả cách KMS/HSM bảo vệ khóa, phân quyền sử dụng và ghi nhận kiểm toán.
5. Áp dụng các nguyên tắc vòng đời khóa, xoay vòng, thu hồi và hủy trong các hệ thống thực tế.

## 2. Private key và public key hoạt động cùng nhau thế nào?

Một thuật toán mật mã bất đối xứng tạo ra cặp khóa liên hệ với nhau về mặt toán học:

~~~text
                 Thuật toán tạo cặp khóa an toàn
                               |
                      +--------+--------+
                      |                 |
                  Private key        Public key
                  (giữ bí mật)       (có thể công bố)
                      |                 |
                Ký / giải mã /       Xác minh chữ ký /
                thỏa thuận khóa      mã hóa / thỏa thuận khóa
                     (tùy thuật toán được sử dụng)
~~~

Với thuật toán và kích thước khóa được lựa chọn đúng, việc biết public key **không khả thi về mặt tính toán để suy ra private key** theo các giả định bảo mật hiện hành. Điều này không bảo vệ khỏi lỗi tạo khóa, rò rỉ file, truy cập bộ nhớ trái phép hay tấn công kênh kề (*side channel*).

**Không phải cặp khóa nào cũng dùng cho mọi phép toán:**

| Thuật toán / mục đích | Private key làm gì? | Public key làm gì? | Ghi chú |
|---|---|---|---|
| **Ed25519 / EdDSA** | Tạo chữ ký | Kiểm tra chữ ký | Không dùng Ed25519 trực tiếp để giải mã |
| **ECDSA** (ví dụ P-256) | Tạo chữ ký | Kiểm tra chữ ký | Nếu nonce ký ECDSA được sinh sai hoặc tái sử dụng, private key có thể bị lộ |
| **RSA-OAEP** | Giải mã | Mã hóa | Không phù hợp để mã hóa trực tiếp lượng dữ liệu lớn |
| **RSA-PSS** | Tạo chữ ký | Kiểm tra chữ ký | Phải đồng bộ chính xác thuật toán băm và tham số PSS |
| **X25519/ECDH** | Kết hợp với public key đối tác để tính bí mật chung | Được chia sẻ để đối tác tính bí mật chung | Cần KDF để tạo khóa phiên từ kết quả thỏa thuận |

**Private key không phải là một mật khẩu tùy ý.** Nó là giá trị toán học, seed hoặc tập tham số hợp lệ được tạo theo quy trình của thuật toán. Mật khẩu có thể được dùng để mã hóa file chứa khóa riêng, nhưng không thay thế private key.

### 2.1. Khóa riêng, khóa công khai và khóa đối xứng

| Khái niệm | Key material? | Phải giữ bí mật? | Ví dụ |
|---|---|---|---|
| **Private key** | Có | **Có** | Khóa Ed25519 của dịch vụ phát hành JWT |
| **Public key** | Có | Thường không, nhưng phải xác thực nguồn và tính toàn vẹn | Khóa công khai để xác minh JWT |
| **Symmetric key / secret key** | Có | **Có** | Khóa AES-256 dùng mã hóa dữ liệu |
| **Key ID, version, alias** | Không; là thông tin định danh hoặc metadata | Thường không, nhưng cần chống sửa/tráo | **invoice-signing**, phiên bản **v3** |
| **Chứng thư số (certificate)** | Cấu trúc chứa public key và thông tin chứng thực | Thường công khai | Chứng thư X.509 của máy chủ |
| **Private key handle** | Không phải byte khóa; là tham chiếu đến khóa | Cần bảo vệ quyền dùng tham chiếu | ID đối tượng trong KMS/HSM |

Một **symmetric key** như khóa AES dùng chung cho mã hóa và giải mã; bản thân nó không thuộc cặp private/public. Một **public key** có thể được chia sẻ rộng rãi, nhưng bên nhận phải xác thực nó thực sự thuộc về chủ thể mong đợi: nếu kẻ tấn công tráo public key, quá trình kiểm tra chữ ký có thể đúng về mặt toán học nhưng đang kiểm tra chữ ký của **kẻ tấn công**.

## 3. Private key thực hiện những thao tác gì?

### 3.1. Ký số: khóa riêng ký, khóa công khai xác minh

Một dịch vụ phát hành hóa đơn tạo chữ ký bằng private key. Bên nhận dùng public key đáng tin cậy kiểm tra chữ ký trên **đúng chuỗi byte đã ký**:

~~~mermaid
sequenceDiagram
    participant S as Dịch vụ ký
    participant K as KMS/HSM
    participant R as Bên nhận
    S->>K: Sign(keyId, message/digest)
    Note over K: Dùng private key được bảo vệ
    K-->>S: Signature
    S->>R: Nội dung + chữ ký + keyId
    R->>R: Lấy public key từ nguồn tin cậy
    R->>R: Verify(public key, nội dung, chữ ký)
    R-->>S: Hợp lệ hoặc không hợp lệ
~~~

Chữ ký hợp lệ chứng minh dữ liệu không bị thay đổi theo phép kiểm tra chữ ký và chữ ký đã được tạo bằng khả năng sử dụng private key tương ứng. **Nó không tự chứng minh danh tính** nếu public key chưa được liên kết với danh tính đáng tin cậy. Chứng thư số, PKI, public-key pinning hoặc một cơ chế xác thực phân phối khóa thích hợp giúp thiết lập liên kết này. Chữ ký số không tự bảo đảm mọi yếu tố pháp lý về ý chí ký và chống chối bỏ khi khóa đã bị lạm dụng.

Ứng dụng chỉ **xác minh** không cần private key. Cấp private key cho bên xác minh làm tăng bề mặt rò rỉ và nguy cơ ký giả mạo.

### 3.2. Giải mã: public key mã hóa, private key giải mã

Với sơ đồ mã hóa khóa công khai **RSA-OAEP**:

~~~text
Người gửi:  plaintext -- Encrypt(public key) --> ciphertext
Người nhận: ciphertext -- Decrypt(private key) --> plaintext
~~~

Việc có public key không đủ để giải mã bản mã được tạo đúng theo RSA-OAEP. Nhưng câu “private key giải mã dữ liệu” **không áp dụng cho mọi loại khóa riêng**: private key Ed25519 là khóa ký, không phải khóa giải mã.

RSA-OAEP chỉ mã hóa trực tiếp được dữ liệu có kích thước giới hạn theo key size và thuật toán băm. Hệ thống thực tế thường dùng **hybrid/envelope encryption**: dùng khóa đối xứng DEK để mã hóa payload lớn bằng AES-GCM, còn một cơ chế khóa công khai được thiết kế phù hợp sẽ mã hóa hoặc bảo vệ DEK. Nhiều hệ thống KMS khác lại dùng **KEK đối xứng**, vì vậy không được đồng nhất mọi KEK với private key bất đối xứng.

### 3.3. Thỏa thuận khóa: private key tham gia tạo bí mật chung

Trong **X25519/ECDH**, mỗi phía có cặp khóa riêng và nhận public key của phía kia. Mỗi bên kết hợp **private key của mình** với **public key đối tác** để tính bí mật chung; sau đó dùng **KDF** với ngữ cảnh phù hợp tạo khóa phiên.

~~~mermaid
flowchart TD
    A["Bên A: private_A + public_B"] --> S["Bí mật chung X25519/ECDH"]
    B["Bên B: private_B + public_A"] --> S
    S --> KDF["KDF và thông tin ngữ cảnh"]
    KDF --> AES["Khóa phiên cho AEAD/AES-GCM"]
~~~

Đây là sơ đồ biểu diễn **hai phép tính độc lập cùng cho một kết quả**, không phải hai phía gửi private key vào một máy chủ trung tâm. ECDH thuần túy **không tự xác thực đối tác**: nếu public key của đối tác bị tráo, có nguy cơ *man-in-the-middle*.

Trong **TLS 1.3**, private key gắn với chứng thư máy chủ được dùng chủ yếu cho **xác thực bằng chữ ký**, còn khóa bảo vệ phiên được dẫn xuất từ quá trình trao đổi khóa tạm thời. Không nên nói máy chủ TLS 1.3 dùng private key chứng thư để trực tiếp giải mã toàn bộ lưu lượng HTTPS.

## 4. Key material, định dạng khóa và key metadata

### 4.1. Private key được lưu dưới dạng nào?

Private key có thể tồn tại dưới dạng chuỗi byte, cấu trúc số hoặc một đối tượng được giữ trong HSM/KMS. Khi lưu ra file, các định dạng thường gặp gồm:

- **PKCS#8:** cấu trúc chuẩn dùng biểu diễn thông tin khóa riêng cho nhiều thuật toán; có dạng không mã hóa hoặc mã hóa.
- **DER:** dạng mã hóa nhị phân của cấu trúc như ASN.1, không mặc nhiên bảo vệ bí mật.
- **PEM:** dạng văn bản có header/footer và nội dung Base64 của dữ liệu nhị phân. **Base64 không phải mã hóa bảo mật**.
- **Key handle / key reference:** định danh đại diện cho một đối tượng private key nằm trong thiết bị hoặc dịch vụ; ứng dụng có thể thao tác ký/giải mã mà không nhận byte khóa.

Ví dụ cấu trúc minh họa, **không chứa khóa thật**:

~~~text
-----BEGIN PRIVATE KEY-----
<BASE64_PKCS8_DER_PLACEHOLDER>
-----END PRIVATE KEY-----
~~~

Header **BEGIN PRIVATE KEY** thường mô tả container khóa riêng PKCS#8 chưa được mã hóa ở lớp container. Header **BEGIN ENCRYPTED PRIVATE KEY** biểu thị container có mã hóa, nhưng mức an toàn còn phụ thuộc thuật toán mã hóa, hàm dẫn xuất khóa và mật khẩu. Một file đuôi **.pem** hoặc **.key** không tự an toàn.

### 4.2. Key material khác metadata ở chỗ nào?

| Thành phần | Ví dụ | Phân loại | Biện pháp bảo vệ |
|---|---|---|---|
| Private key bytes/seed/scalar | Seed Ed25519, thành phần riêng RSA | Material bí mật | Giảm export; mã hóa khi lưu; bảo vệ bộ nhớ; cấm log |
| Public key | Thành phần công khai của cặp khóa | Material công khai | Xác thực nguồn và tính toàn vẹn |
| **keyId, keyVersion** | **billing-signing**, **v4** | Metadata | Chọn đúng khóa/phiên bản; chống sửa đổi trái phép |
| **algorithm, purpose** | **Ed25519**, **SIGN_VERIFY** | Metadata | Kiểm tra allowlist, đúng công dụng |
| **owner, tenant, policy** | **billing-service**, **tenant-a** | Metadata quản trị | IAM, phân vùng quyền, quản lý thay đổi |
| **state, createdAt, rotationDueAt** | ENABLED, mốc thời gian | Metadata vòng đời | Thực thi trạng thái, lịch xoay, audit |
| **KMS key reference / HSM handle** | ID đối tượng không xuất khóa | Tham chiếu | Kiểm tra quyền thao tác và gắn với đúng tenant |

Key ID không phải private key. Ngược lại, chuỗi Base64 chứa private key vẫn là **material bí mật**, dù trông giống text. Metadata cũng không được tự ý sửa: kẻ tấn công có thể thay version, alias, tenant hoặc policy để trỏ nhầm khóa và gây gián đoạn/xâm phạm.

### 4.3. Khóa nằm trong KMS/HSM có hoàn toàn an toàn?

**KMS (Key Management Service)** thường cung cấp API tạo, nhập, quản lý metadata, vòng đời, quyền sử dụng và audit theo khả năng dịch vụ. **HSM (Hardware Security Module)** là ranh giới phần cứng chuyên dụng bảo vệ khóa và thực thi mật mã theo thiết kế thiết bị. KMS có thể dựa trên HSM, nhưng hai khái niệm không đồng nghĩa.

Một private key **non-exportable** không cho ứng dụng lấy byte khóa ở dạng bản rõ. Tuy nhiên, nếu một principal bị chiếm có quyền **Sign**, kẻ tấn công vẫn có thể yêu cầu thiết bị tạo chữ ký hợp lệ. Vì vậy cần cùng lúc:

1. Bảo vệ vật liệu khóa khỏi bị xuất/đọc trái phép.
2. Giới hạn **ai** được thực hiện **Sign/Decrypt**, với **khóa nào**, tại **tenant/môi trường nào**.
3. Tách quyền quản trị key policy khỏi quyền sử dụng khóa khi có thể.
4. Audit người gọi, thao tác, key ID/version, thời điểm, kết quả; không ghi khóa hoặc plaintext nhạy cảm vào log.

Không nên mặc định mọi KMS đều hỗ trợ mọi loại khóa, API hoặc cơ chế cấm export: cần kiểm tra contract và chính sách của nhà cung cấp.

## 5. Ví dụ Java 17: sử dụng private key Ed25519 để ký số

Ví dụ sau chỉ dùng thư viện Java chuẩn: tạo một cặp khóa tạm thời trong bộ nhớ, ký tài liệu bằng **PrivateKey**, xác minh bằng **PublicKey**, rồi thử thay đổi tài liệu để kiểm tra rằng chữ ký không còn hợp lệ. Đây là demo học thuật, không phải hệ thống quản lý khóa production.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.util.Base64;

public final class PrivateKeyDemo {
    private static byte[] sign(byte[] message, PrivateKey privateKey)
            throws Exception {
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(privateKey);
        signer.update(message);
        return signer.sign();
    }

    private static boolean verify(byte[] message, byte[] signature,
                                  PublicKey trustedPublicKey)
            throws Exception {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(trustedPublicKey);
        verifier.update(message);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair pair = generator.generateKeyPair();

        byte[] document = "invoiceId=123;amount=250000"
                .getBytes(StandardCharsets.UTF_8);
        byte[] signature = sign(document, pair.getPrivate());

        System.out.println("Signature (Base64): "
                + Base64.getEncoder().encodeToString(signature));
        System.out.println("Valid: "
                + verify(document, signature, pair.getPublic())); // true

        byte[] tampered = "invoiceId=123;amount=250001"
                .getBytes(StandardCharsets.UTF_8);
        System.out.println("Tampered valid: "
                + verify(tampered, signature, pair.getPublic())); // false

        // Không xuất private key ra file hoặc ghi vào log.
    }
}
~~~

Với JDK 17+, lưu mã thành **PrivateKeyDemo.java** rồi thực hiện:

~~~bash
javac PrivateKeyDemo.java
java PrivateKeyDemo
~~~

Kết quả mong đợi có **Valid: true** và **Tampered valid: false**. Chữ ký biểu diễn Base64 sẽ thay đổi qua các lần chạy do mỗi lần tạo một cặp khóa mới. **Base64 của chữ ký có thể công bố; Base64 của private key thì không.**

**Bài học từ đoạn mã:**

1. **PrivateKey** chỉ được cấp cho thao tác ký. Bên xác minh chỉ nhận **PublicKey** đã được xác thực từ kênh tin cậy.
2. Cả hai bên phải sử dụng **đúng cùng chuỗi byte**. Với tài liệu JSON, phải thống nhất encoding và định dạng chuẩn hóa nếu cần, tránh khác nhau do khoảng trắng, thứ tự trường, cách biểu diễn số.
3. Một số provider phần mềm cho xuất byte private key; provider KMS/HSM có thể trả một đối tượng tham chiếu và không cho xuất. Không gọi phương thức xuất khóa và đưa kết quả vào log để kiểm thử.
4. Trong production, cần bảo vệ cả dữ liệu được ký, policy nhận dạng issuer và quyền sử dụng khóa; một chữ ký hợp lệ trên dữ liệu do kẻ gian tùy ý chọn vẫn có thể gây thiệt hại.
5. Ed25519 **không được dùng** trong ví dụ để giải mã; giải mã bất đối xứng cần thuật toán/sơ đồ khác như RSA-OAEP hoặc thiết kế mã hóa lai phù hợp.

### 5.1. Luồng ký khi private key nằm trong KMS/HSM

Khi sử dụng KMS/HSM, ứng dụng có thể truyền **key reference** và dữ liệu cần ký theo hợp đồng API mà không giữ private key:

~~~text
signInvoice(invoice, keyRef):
    1. Xác thực workload / tenant đang gọi.
    2. Kiểm tra keyRef, key version, purpose=SIGN và state được phép.
    3. Kiểm tra quyền Sign của caller; chuẩn hóa bytes cần ký.
    4. Gọi KMS/HSM Sign(keyRef, message hoặc digest).
    5. Trả lại signature và key reference cho bên kiểm tra.
    6. Ghi audit: caller, keyRef, action, timestamp, result.

verifyInvoice(invoice, signature, keyRef):
    1. Lấy public key tương ứng từ nguồn đáng tin cậy.
    2. Kiểm tra thuật toán, quyền tin cậy, ngữ cảnh xác minh.
    3. Verify(publicKey, bytes đã ký, signature).
~~~

Đây là **pseudocode**, không phải chữ ký hàm của bất kỳ dịch vụ KMS cụ thể nào. Một số API ký nhận message, API khác nhận digest đã băm; phải tuân thủ API để không băm hai lần hoặc ký sai dữ liệu.

## 6. Vòng đời private key

~~~mermaid
flowchart TD
    A["Tạo hoặc nhập key material"] --> B["Gắn key ID, version, owner, purpose"]
    B --> C["Lưu trữ trong kho được bảo vệ"]
    C --> D["Kích hoạt, phân quyền Sign/Decrypt"]
    D --> E["Sử dụng có kiểm toán"]
    E --> F["Tạo khóa/phiên bản mới khi xoay vòng"]
    F --> G["Ngừng dùng khóa cũ cho thao tác mới"]
    G --> H["Chờ hết phụ thuộc, hủy đúng quy trình"]
~~~

| Giai đoạn | Việc nên làm | Lỗi cần tránh |
|---|---|---|
| **Tạo** | Dùng CSPRNG và thư viện mật mã được kiểm chứng; chọn thuật toán, kích thước khóa theo policy | Sinh khóa từ timestamp hoặc **Random** không an toàn |
| **Đăng ký/cấp phát** | Gắn key ID, version, owner, tenant, purpose, quyền cụ thể | Sao chép một private key sang nhiều dịch vụ |
| **Lưu trữ** | Ưu tiên kho khóa được bảo vệ, hạn chế export; backup theo chính sách | Commit PEM vào Git, đưa khóa vào container image hoặc CI log |
| **Sử dụng** | Kiểm tra principal, state, key purpose; audit operation | Client chọn tùy ý key ID hoặc algorithm |
| **Xoay vòng** | Sinh cặp mới, phát hành public key mới, chuyển tác vụ mới sang phiên bản mới | Nghĩ đổi alias là tự cập nhật chữ ký/bản mã cũ |
| **Thu hồi/vô hiệu hóa** | Ngừng hoặc hạn chế thao tác, cập nhật hệ thống tin cậy public key nếu cần | Chỉ xóa alias mà không chặn thao tác ký |
| **Hủy** | Kiểm tra dữ liệu, chữ ký lịch sử, backup và yêu cầu khôi phục | Hủy private key giải mã khi còn ciphertext phụ thuộc |

### 6.1. Rotation của khóa ký khác rotation của khóa giải mã

**Khóa ký:** khi chuyển từ **sign-v2** sang **sign-v3**, các tài liệu cũ vẫn mang chữ ký của **v2** và có thể cần public key **v2** để xác minh. Việc hủy private key v2 không xóa public key v2. Tuy nhiên, nếu có nghi vấn private key v2 đã lộ, khả năng tiếp tục tin các chữ ký cũ phụ thuộc thời điểm ký, chính sách chứng thư, bằng chứng và quy trình ứng phó.

**Khóa giải mã:** khi chuyển người gửi sang public key **decrypt-v3**, ciphertext cũ vẫn cần private key **decrypt-v2** tương ứng. Trước khi hủy v2, phải giải mã/mã hóa lại dữ liệu hoặc thực hiện quá trình chuyển đổi lớp khóa phù hợp. Hủy sớm có thể dẫn tới **mất khả năng phục hồi dữ liệu**.

### 6.2. Disable private key khác thu hồi chứng thư

- **Disable key trong KMS/HSM:** chặn hoặc giới hạn khả năng gọi phép toán bằng private key tại hệ thống đó.
- **Certificate revocation:** thu hồi trạng thái tin cậy của chứng thư trong PKI, thường thông qua CRL/OCSP hoặc chính sách xác minh tương đương.
- **Ngừng công bố public key trong JWKS:** có thể ảnh hưởng đến JWT đang còn hiệu lực, nhưng không tự xóa các bản public key mà bên xác minh đã cache.

Nếu nghi private key bị lộ, cần **điều tra sự cố, dừng quyền sử dụng rủi ro, thay khóa, cập nhật hệ thống tin cậy và đánh giá dữ liệu/chữ ký đã bị ảnh hưởng**. Chỉ sinh một cặp khóa mới mà vẫn để khóa cũ hoạt động không thể loại bỏ hậu quả xâm phạm.

## 7. Mối đe dọa phổ biến và biện pháp bảo vệ

| Tình huống | Hậu quả | Biện pháp |
|---|---|---|
| File private key PEM/PKCS#8 bị đưa vào source code, ticket hoặc CI logs | Bất kỳ người có quyền xem đều có thể sao chép khóa | Secret scanning; không commit; thay khóa nếu đã lộ; xử lý history |
| Quyền **Sign** được cấp cho quá nhiều service account | Có thể ký giả mạo mà không cần lấy byte khóa | Least privilege, workload identity, tách tenant, audit, cảnh báo bất thường |
| File khóa mã hóa nhưng passphrase lưu cùng thư mục | Lấy được cả khóa và mật khẩu | Phân tách vị trí quản lý bí mật, cân nhắc KMS/HSM |
| Key material xuất hiện trong heap dump, trace, backup | Rò rỉ khóa qua hệ thống giám sát/lưu trữ | Hạn chế dump, bảo vệ backup, kiểm soát truy cập, không log secret |
| Nguồn ngẫu nhiên yếu hoặc triển khai ECDSA nonce sai | Có thể dự đoán/khôi phục khóa | Dùng CSPRNG và thư viện mật mã được kiểm chứng |
| JWT verifier tin thuật toán hoặc public key URL do token tự đưa | Kiểm tra chữ ký với khóa/thuật toán không đáng tin | Allowlist thuật toán, pin issuer/JWKS, kiểm tra iss/aud/exp |
| Nhiều tenant dùng chung private key và quyền quá rộng | Một sự cố ảnh hưởng nhiều tenant | Tách khóa/quyền theo tenant, ứng dụng và mục đích theo rủi ro |
| Hủy key trước khi xử lý ciphertext còn phụ thuộc | Không thể giải mã dữ liệu lịch sử | Kế hoạch restore, re-encrypt/re-wrap, thử nghiệm trước hủy |

Hai câu hỏi kiểm soát phải được trả lời riêng: **Ai có thể lấy được byte private key?** và **Ai có thể khiến private key thực hiện thao tác?** Một HSM có thể giảm nguy cơ của câu hỏi thứ nhất, nhưng không tự xử lý được tài khoản có quyền Sign bị chiếm ở câu hỏi thứ hai.

## 8. Tình huống thiết kế: JWT với private key trong KMS

Giả sử **Auth Service** phát hành JWT, **API Gateway** xác minh token và **KMS** giữ private key ký:

1. **Tạo khóa:** đăng ký cặp khóa ký bất đối xứng, gắn key ID **auth-signing**, version **v3**, owner **auth-service**; chỉ cấp quyền Sign cho workload phù hợp.
2. **Ký token:** Auth Service tạo header/payload theo chuẩn JWS, truyền chính xác dữ liệu cần ký vào KMS, nhận signature. Header **kid=v3** chỉ là tham chiếu giúp bên xác minh chọn public key.
3. **Xác minh:** Gateway lấy public key từ nguồn **đáng tin cậy** của issuer, kiểm tra chữ ký và các điều kiện **iss**, **aud**, **exp**, **nbf** theo chính sách. Không tin URL khóa/thuật toán do token tùy ý đề nghị.
4. **Xoay vòng:** xuất bản public key **v4** theo kênh tin cậy, chuyển token mới sang private key **v4**, giữ khả năng xác minh v3 theo tuổi thọ token, cache và chính sách.
5. **Ứng phó sự cố:** nếu private key v3 nghi bị lộ, dừng quyền ký v3, cấp khóa mới, quyết định cách chặn các token còn hiệu lực và kiểm tra nhật ký thao tác ký.

Gateway **không cần private key**. Ngược lại, Auth Service cũng không cần được cấp quyền quản trị/xóa key nếu chỉ có nhiệm vụ ký. Việc phân tách vai trò tạo ra các ranh giới kiểm soát dễ kiểm toán.

## 9. Tự kiểm tra và checklist

Trước khi đưa một private key vào sử dụng, hãy xác minh:

1. **Purpose:** khóa dùng ký, giải mã hay trao đổi khóa? Có cho phép dùng lẫn mục đích hay không?
2. **Algorithm:** thuật toán, kích thước khóa và các tham số có đáp ứng yêu cầu bảo mật hiện hành?
3. **Origin:** khóa được sinh/nhập bằng cách nào? Entropy và thư viện có đáng tin?
4. **Storage:** material ở đâu? Có xuất được không? Ai có quyền đọc file, dump và backup?
5. **Access:** ai được Sign/Decrypt? Có kiểm tra tenant, environment, key state và policy?
6. **Metadata:** ID/version/owner/algorithm/state được gắn đúng và chống sửa trái phép?
7. **Public-key trust:** bên xác minh có xác thực danh tính gắn với public key?
8. **Rotation:** dữ liệu/chữ ký cũ còn được xử lý đúng khi phiên bản thay đổi?
9. **Revocation/destruction:** có đánh giá sự cố, backup, thời hạn lưu trữ và phụ thuộc dữ liệu trước hủy?
10. **Audit:** có ghi được ai dùng khóa, khi nào, làm gì và kết quả, mà không ghi material bí mật?

### Câu hỏi tự đánh giá

**Câu 1.** Một dịch vụ chỉ kiểm tra chữ ký hóa đơn có cần private key không?

**Trả lời:** **Không.** Dịch vụ đó cần public key đáng tin cậy và quy tắc xác minh tương ứng.

**Câu 2.** Private key trong HSM không thể export. Có thể bỏ qua IAM và audit không?

**Trả lời:** **Không.** Người có quyền Sign/Decrypt vẫn có thể lạm dụng khóa mà không lấy được raw key.

**Câu 3.** Đã xoay khóa ký từ v2 sang v3. Có thể ngừng phân phối public key v2 ngay không?

**Trả lời:** **Tùy chính sách.** Nếu còn token hoặc tài liệu ký bằng v2 cần xác minh, phải giữ cách xác minh phù hợp. Nếu khóa v2 bị lộ, cần quyết định riêng về việc chấp nhận chữ ký/token cũ.

**Câu 4.** Private key RSA dùng giải mã ciphertext cũ bị hủy, nhưng public key vẫn còn. Có phục hồi ciphertext chỉ bằng public key được không?

**Trả lời:** **Không.** Public key RSA-OAEP dùng mã hóa; cần private key tương ứng để giải mã. Vì vậy phải lập kế hoạch xử lý dữ liệu phụ thuộc trước khi hủy.

**Điểm cốt lõi:** **Private key là key material bí mật tạo ra năng lực mật mã**; **key ID, version, purpose, policy, state và audit** là thông tin giúp kiểm soát năng lực đó. Muốn quản lý private key an toàn phải đồng thời bảo vệ bí mật khóa, xác thực public key, giới hạn quyền sử dụng và quản trị vòng đời.
